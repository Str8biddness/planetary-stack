#pragma once

#include <linux/kvm.h>
#include "serial_console.hpp"
#include <memory>
#include <string>
#include <vector>
#include <cstdint>

namespace synthesus::kernel::vmm {

class MMIODevice {
public:
    virtual ~MMIODevice() = default;
    virtual uint64_t base_address() const = 0;
    virtual uint64_t size() const = 0;
    virtual bool read(uint64_t offset, uint8_t* data, size_t len) = 0;
    virtual bool write(uint64_t offset, const uint8_t* data, size_t len) = 0;

    bool contains(uint64_t phys_addr, size_t len) const {
        return phys_addr >= base_address() && phys_addr + len <= base_address() + size();
    }
};

class VMM {
public:
    VMM();
    ~VMM();

    bool initialize();
    bool allocate_memory(size_t size);
    bool setup_vcpu();
    void set_required_xcr0(uint64_t xcr0);
    void register_mmio_device(std::shared_ptr<MMIODevice> device);
    void clear_mmio_devices();
    std::shared_ptr<SerialConsole> serial_console() const { return serial_console_; }
    void set_serial_console(std::shared_ptr<SerialConsole> console);
    bool load_payload(const std::vector<uint8_t>& payload);
    bool run();

    // Getters for testing/debugging
    int get_vm_fd() const { return vm_fd_; }
    int get_vcpu_fd() const { return vcpu_fd_; }

private:
    int kvm_fd_ = -1;
    int vm_fd_ = -1;
    int vcpu_fd_ = -1;
    struct kvm_run* run_ptr_ = nullptr;
    size_t mmap_size_ = 0;
    uint8_t* guest_mem_ = nullptr;
    size_t guest_mem_size_ = 0;
    uint64_t required_xcr0_ = 0x1;
    std::vector<std::shared_ptr<MMIODevice>> mmio_devices_;
    std::shared_ptr<SerialConsole> serial_console_;

    bool set_regs();
    bool set_sregs();
    bool set_xcrs();
    bool handle_mmio();
    bool handle_io();
};

} // namespace synthesus::kernel::vmm
