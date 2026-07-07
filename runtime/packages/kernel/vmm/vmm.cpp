#include "vmm.hpp"
#include "kvm_utils.hpp"
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <cstring>
#include <iostream>

namespace synthesus::kernel::vmm {

namespace {

constexpr uint64_t kCr0Mp = 1ull << 1;
constexpr uint64_t kCr0Em = 1ull << 2;
constexpr uint64_t kCr4Osfxsr = 1ull << 9;
constexpr uint64_t kCr4Osxmmexcpt = 1ull << 10;
constexpr uint64_t kCr4Osxsave = 1ull << 18;
constexpr uint64_t kXcr0X87 = 1ull << 0;
constexpr uint64_t kXcr0Sse = 1ull << 1;
constexpr uint64_t kXcr0Ymm = 1ull << 2;

} // namespace

VMM::VMM()
    : serial_console_(std::make_shared<SerialConsole>()) {}

VMM::~VMM() {
    if (run_ptr_ && mmap_size_ > 0) {
        munmap(run_ptr_, mmap_size_);
    }
    if (guest_mem_ && guest_mem_size_ > 0) {
        munmap(guest_mem_, guest_mem_size_);
    }
    if (vcpu_fd_ != -1) close(vcpu_fd_);
    if (vm_fd_ != -1) close(vm_fd_);
    if (kvm_fd_ != -1) close(kvm_fd_);
}

bool VMM::initialize() {
    kvm_fd_ = open("/dev/kvm", O_RDWR | O_CLOEXEC);
    if (kvm_fd_ == -1) return false;

    int api_ver = kvm_ioctl(kvm_fd_, KVM_GET_API_VERSION);
    if (api_ver != 12) return false;

    vm_fd_ = kvm_ioctl(kvm_fd_, KVM_CREATE_VM, 0);
    return vm_fd_ != -1;
}

bool VMM::allocate_memory(size_t size) {
    guest_mem_size_ = size;
    guest_mem_ = static_cast<uint8_t*>(mmap(NULL, guest_mem_size_, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0));
    if (guest_mem_ == MAP_FAILED) return false;

    struct kvm_userspace_memory_region region = {
        .slot = 0,
        .flags = 0,
        .guest_phys_addr = 0x1000, // Load at 4KB offset
        .memory_size = guest_mem_size_,
        .userspace_addr = reinterpret_cast<uint64_t>(guest_mem_),
    };

    return kvm_ioctl(vm_fd_, KVM_SET_USER_MEMORY_REGION, &region) != -1;
}

bool VMM::setup_vcpu() {
    vcpu_fd_ = kvm_ioctl(vm_fd_, KVM_CREATE_VCPU, (void*)0);
    if (vcpu_fd_ == -1) return false;

    int mmap_size = kvm_ioctl(kvm_fd_, KVM_GET_VCPU_MMAP_SIZE);
    if (mmap_size <= 0) return false;
    mmap_size_ = static_cast<size_t>(mmap_size);

    run_ptr_ = static_cast<struct kvm_run*>(mmap(NULL, mmap_size_, PROT_READ | PROT_WRITE, MAP_SHARED, vcpu_fd_, 0));
    if (run_ptr_ == MAP_FAILED) return false;

    return set_sregs() && set_xcrs() && set_regs();
}

bool VMM::set_sregs() {
    struct kvm_sregs sregs;
    if (kvm_ioctl(vcpu_fd_, KVM_GET_SREGS, &sregs) == -1) return false;
    sregs.cs.base = 0;
    sregs.cs.selector = 0;
    sregs.cr0 |= kCr0Mp;
    sregs.cr0 &= ~kCr0Em;
    if (required_xcr0_ & (kXcr0Sse | kXcr0Ymm)) {
        sregs.cr4 |= kCr4Osfxsr | kCr4Osxmmexcpt;
    }
    if (required_xcr0_ & kXcr0Ymm) {
        sregs.cr4 |= kCr4Osxsave;
    }
    return kvm_ioctl(vcpu_fd_, KVM_SET_SREGS, &sregs) != -1;
}

bool VMM::set_xcrs() {
    if ((required_xcr0_ & kXcr0Ymm) == 0) {
        return true;
    }

    if (::ioctl(kvm_fd_, KVM_CHECK_EXTENSION, KVM_CAP_XCRS) <= 0) {
        std::cerr << "KVM: XCRS support is required for AVX guest payloads" << std::endl;
        return false;
    }

    struct kvm_xcrs xcrs;
    std::memset(&xcrs, 0, sizeof(xcrs));
    xcrs.nr_xcrs = 1;
    xcrs.xcrs[0].xcr = 0;
    xcrs.xcrs[0].value = required_xcr0_ | kXcr0X87;
    return kvm_ioctl(vcpu_fd_, KVM_SET_XCRS, &xcrs) != -1;
}

bool VMM::set_regs() {
    struct kvm_regs regs;
    if (kvm_ioctl(vcpu_fd_, KVM_GET_REGS, &regs) == -1) return false;
    regs.rip = 0x1000;
    regs.rflags = 0x2; // Bit 1 is reserved and must be 1
    return kvm_ioctl(vcpu_fd_, KVM_SET_REGS, &regs) != -1;
}

bool VMM::load_payload(const std::vector<uint8_t>& payload) {
    if (!guest_mem_ || payload.size() > guest_mem_size_) return false;
    std::memcpy(guest_mem_, payload.data(), payload.size());
    return true;
}

void VMM::set_required_xcr0(uint64_t xcr0) {
    required_xcr0_ = xcr0 | kXcr0X87;
}

void VMM::register_mmio_device(std::shared_ptr<MMIODevice> device) {
    if (device) {
        mmio_devices_.push_back(std::move(device));
    }
}

void VMM::clear_mmio_devices() {
    mmio_devices_.clear();
}

void VMM::set_serial_console(std::shared_ptr<SerialConsole> console) {
    serial_console_ = std::move(console);
}

bool VMM::handle_mmio() {
    const auto phys_addr = run_ptr_->mmio.phys_addr;
    const auto len = static_cast<size_t>(run_ptr_->mmio.len);
    for (const auto& device : mmio_devices_) {
        if (!device || !device->contains(phys_addr, len)) continue;

        const auto offset = phys_addr - device->base_address();
        if (run_ptr_->mmio.is_write) {
            return device->write(offset, run_ptr_->mmio.data, len);
        }
        return device->read(offset, run_ptr_->mmio.data, len);
    }
    return false;
}

bool VMM::handle_io() {
    if (serial_console_ && serial_console_->contains(run_ptr_->io.port)) {
        return serial_console_->handle_io(run_ptr_);
    }

    std::cout << "KVM: Guest IO: direction=" << (int)run_ptr_->io.direction
              << " port=0x" << std::hex << run_ptr_->io.port << std::dec
              << " size=" << (int)run_ptr_->io.size << std::endl;
    return true;
}

bool VMM::run() {
    while (true) {
        if (kvm_ioctl(vcpu_fd_, KVM_RUN) == -1) return false;

        switch (run_ptr_->exit_reason) {
            case KVM_EXIT_HLT:
                std::cout << "KVM: Guest HLTed" << std::endl;
                return true;
            case KVM_EXIT_IO:
                if (!handle_io()) {
                    std::cerr << "KVM: Unhandled IO port 0x" << std::hex
                              << run_ptr_->io.port << std::dec
                              << " size=" << static_cast<int>(run_ptr_->io.size)
                              << " count=" << run_ptr_->io.count << std::endl;
                    return false;
                }
                break;
            case KVM_EXIT_MMIO:
                std::cout << "KVM: Guest MMIO: phys_addr=0x" << std::hex << run_ptr_->mmio.phys_addr << std::dec 
                          << " len=" << run_ptr_->mmio.len << " is_write=" << (int)run_ptr_->mmio.is_write << std::endl;
                if (!handle_mmio()) {
                    std::cerr << "KVM: Unhandled MMIO address 0x" << std::hex
                              << run_ptr_->mmio.phys_addr << std::dec << std::endl;
                    return false;
                }
                break;
            case KVM_EXIT_FAIL_ENTRY:
                std::cerr << "KVM: Entry failed: hardware_entry_failure_reason=0x" << std::hex << run_ptr_->fail_entry.hardware_entry_failure_reason << std::dec << std::endl;
                return false;
            case KVM_EXIT_INTERNAL_ERROR:
                std::cerr << "KVM: Internal error: suberror=0x" << std::hex << run_ptr_->internal.suberror << std::dec << std::endl;
                return false;
            default:
                std::cerr << "KVM: Unhandled exit reason: " << run_ptr_->exit_reason << std::endl;
                return false;
        }
    }
}

} // namespace synthesus::kernel::vmm
