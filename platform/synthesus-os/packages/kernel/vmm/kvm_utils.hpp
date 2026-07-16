#pragma once

#include <iostream>
#include <system_error>
#include <sys/ioctl.h>
#include <unistd.h>

namespace synthesus::kernel::vmm {

inline int kvm_ioctl(int fd, unsigned long request, void* arg = nullptr) {
    int ret = ioctl(fd, request, arg);
    if (ret == -1) {
        // Log the error but return -1 so the caller can decide what to do
        std::cerr << "KVM IOCTL failed: " << std::generic_category().message(errno) << " (request: 0x" << std::hex << request << std::dec << ")" << std::endl;
    }
    return ret;
}

} // namespace synthesus::kernel::vmm
