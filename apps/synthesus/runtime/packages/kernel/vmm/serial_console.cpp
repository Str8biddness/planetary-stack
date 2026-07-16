#include "serial_console.hpp"

#include <linux/kvm.h>

namespace synthesus::kernel::vmm {

namespace {

constexpr uint8_t kDlab = 0x80;
constexpr uint8_t kLineStatusDataReady = 0x01;
constexpr uint8_t kLineStatusThrEmpty = 0x20;
constexpr uint8_t kLineStatusTransmitterEmpty = 0x40;

} // namespace

SerialConsole::SerialConsole(uint16_t base_port)
    : base_port_(base_port) {}

bool SerialConsole::contains(uint16_t port) const {
    return port >= base_port_ && port < base_port_ + kCom1Size;
}

bool SerialConsole::handle_io(kvm_run* run) {
    if (!run || !contains(run->io.port) || run->io.size != 1) {
        return false;
    }

    auto* data = reinterpret_cast<uint8_t*>(run) + run->io.data_offset;
    for (uint32_t i = 0; i < run->io.count; ++i) {
        if (run->io.direction == KVM_EXIT_IO_OUT) {
            if (!write_port(run->io.port, data[i])) {
                return false;
            }
        } else if (run->io.direction == KVM_EXIT_IO_IN) {
            if (!read_port(run->io.port, &data[i])) {
                return false;
            }
        } else {
            return false;
        }
    }
    return true;
}

std::string SerialConsole::read_output() {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string out;
    out.swap(output_buffer_);
    return out;
}

void SerialConsole::write_input(const std::string& input) {
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto ch : input) {
        input_buffer_.push_back(static_cast<uint8_t>(ch));
    }
}

bool SerialConsole::read_port(uint16_t port, uint8_t* value) {
    if (!value || !contains(port)) {
        return false;
    }

    const uint16_t offset = port - base_port_;
    std::lock_guard<std::mutex> lock(mutex_);
    switch (offset) {
        case 0:
            if (line_control_ & kDlab) {
                *value = static_cast<uint8_t>(divisor_latch_ & 0xFF);
                return true;
            }
            if (input_buffer_.empty()) {
                *value = 0;
                return true;
            }
            *value = input_buffer_.front();
            input_buffer_.pop_front();
            return true;
        case 1:
            *value = (line_control_ & kDlab)
                         ? static_cast<uint8_t>((divisor_latch_ >> 8) & 0xFF)
                         : interrupt_enable_;
            return true;
        case 2:
            *value = 0x01; // Interrupt identification: no interrupt pending.
            return true;
        case 3:
            *value = line_control_;
            return true;
        case 4:
            *value = modem_control_;
            return true;
        case 5:
            *value = line_status_locked();
            return true;
        case 6:
            *value = 0xB0; // Carrier detect, ring, data set ready, clear to send.
            return true;
        case 7:
            *value = scratch_;
            return true;
        default:
            return false;
    }
}

bool SerialConsole::write_port(uint16_t port, uint8_t value) {
    if (!contains(port)) {
        return false;
    }

    const uint16_t offset = port - base_port_;
    std::lock_guard<std::mutex> lock(mutex_);
    switch (offset) {
        case 0:
            if (line_control_ & kDlab) {
                divisor_latch_ = static_cast<uint16_t>((divisor_latch_ & 0xFF00) | value);
            } else {
                output_buffer_.push_back(static_cast<char>(value));
            }
            return true;
        case 1:
            if (line_control_ & kDlab) {
                divisor_latch_ = static_cast<uint16_t>((divisor_latch_ & 0x00FF) |
                                                       (static_cast<uint16_t>(value) << 8));
            } else {
                interrupt_enable_ = value;
            }
            return true;
        case 2:
            fifo_control_ = value;
            if (value & 0x02) {
                input_buffer_.clear();
            }
            if (value & 0x04) {
                output_buffer_.clear();
            }
            return true;
        case 3:
            line_control_ = value;
            return true;
        case 4:
            modem_control_ = value;
            return true;
        case 7:
            scratch_ = value;
            return true;
        case 5:
        case 6:
            return true;
        default:
            return false;
    }
}

uint8_t SerialConsole::line_status_locked() const {
    uint8_t status = kLineStatusThrEmpty | kLineStatusTransmitterEmpty;
    if (!input_buffer_.empty()) {
        status |= kLineStatusDataReady;
    }
    return status;
}

} // namespace synthesus::kernel::vmm
