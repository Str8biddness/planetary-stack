#pragma once

#include <cstddef>
#include <cstdint>
#include <deque>
#include <mutex>
#include <string>

struct kvm_run;

namespace synthesus::kernel::vmm {

class SerialConsole {
public:
    static constexpr uint16_t kCom1Base = 0x3F8;
    static constexpr uint16_t kCom1Size = 8;

    explicit SerialConsole(uint16_t base_port = kCom1Base);

    uint16_t base_port() const { return base_port_; }
    bool contains(uint16_t port) const;
    bool handle_io(kvm_run* run);

    std::string read_output();
    void write_input(const std::string& input);

private:
    bool read_port(uint16_t port, uint8_t* value);
    bool write_port(uint16_t port, uint8_t value);
    uint8_t line_status_locked() const;

    uint16_t base_port_;
    mutable std::mutex mutex_;
    std::string output_buffer_;
    std::deque<uint8_t> input_buffer_;
    uint8_t interrupt_enable_{0};
    uint8_t fifo_control_{0};
    uint8_t line_control_{0};
    uint8_t modem_control_{0};
    uint8_t scratch_{0};
    uint16_t divisor_latch_{1};
};

} // namespace synthesus::kernel::vmm
