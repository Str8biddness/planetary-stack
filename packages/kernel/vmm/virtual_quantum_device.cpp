#include "virtual_quantum_device.hpp"
#include <algorithm>
#include <cstring>
#include <exception>
#include <utility>

namespace synthesus::kernel::vmm {

VirtualQuantumDevice::VirtualQuantumDevice(uint64_t base, uint64_t size)
    : base_(base), size_(std::max<uint64_t>(size, kDefaultSize)) {}

bool VirtualQuantumDevice::read(uint64_t offset, uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    return write_scalar(data, len, read_register(offset));
}

bool VirtualQuantumDevice::write(uint64_t offset, const uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    const auto value = read_scalar(data, len);
    if (offset == kRegCommand && value == 1) {
        compute_quantum_gate();
        return true;
    }

    std::lock_guard<std::mutex> lock(mutex_);
    return write_register(offset, value);
}

void VirtualQuantumDevice::set_executor(QuantumExecutor executor) {
    std::lock_guard<std::mutex> lock(mutex_);
    executor_ = std::move(executor);
}

void VirtualQuantumDevice::clear_executor() {
    std::lock_guard<std::mutex> lock(mutex_);
    executor_ = nullptr;
}

QuantumGateResult VirtualQuantumDevice::compute_quantum_gate() {
    QuantumExecutor executor;
    QuantumGateRequest request;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        request = request_locked();
        status_ = kStatusBusy;
        error_code_ = kErrorNone;
        if (!validate_request_locked(request)) {
            status_ = kStatusError;
            last_result_ = 0;
            return {status_, last_result_, error_code_};
        }
        executor = executor_;
    }

    QuantumGateResult result;
    if (executor) {
        try {
            result = executor(request);
        } catch (const std::exception&) {
            result = {kStatusError, 0, kErrorExecutorFailure};
        } catch (...) {
            result = {kStatusError, 0, kErrorExecutorFailure};
        }
    } else {
        std::lock_guard<std::mutex> lock(mutex_);
        result = compute_local_locked(request);
    }

    std::lock_guard<std::mutex> lock(mutex_);
    status_ = result.status == kStatusIdle ? kStatusDone : result.status;
    last_result_ = result.result;
    error_code_ = result.error_code;
    if (error_code_ != kErrorNone || status_ == kStatusError) {
        status_ = kStatusError;
    }
    return {status_, last_result_, error_code_};
}

uint64_t VirtualQuantumDevice::read_register(uint64_t offset) const {
    switch (offset) {
        case kRegMagic:
            return kMagic;
        case kRegVersion:
            return 1;
        case kRegStatus:
            return status_;
        case kRegQubitCount:
            return qubit_count_;
        case kRegGateOpcode:
            return gate_opcode_;
        case kRegTargetQubit:
            return target_qubit_;
        case kRegControlQubit:
            return control_qubit_;
        case kRegThetaFixed:
            return theta_fixed_;
        case kRegShots:
            return shots_;
        case kRegCommand:
            return 0;
        case kRegLastResult:
            return last_result_;
        case kRegErrorCode:
            return error_code_;
        default:
            return 0;
    }
}

bool VirtualQuantumDevice::write_register(uint64_t offset, uint64_t value) {
    switch (offset) {
        case kRegQubitCount:
            qubit_count_ = std::max<uint64_t>(1, std::min<uint64_t>(value, 32));
            status_ = kStatusReady;
            error_code_ = kErrorNone;
            return true;
        case kRegGateOpcode:
            gate_opcode_ = value;
            status_ = kStatusReady;
            error_code_ = kErrorNone;
            return true;
        case kRegTargetQubit:
            target_qubit_ = value;
            status_ = kStatusReady;
            error_code_ = kErrorNone;
            return true;
        case kRegControlQubit:
            control_qubit_ = value;
            status_ = kStatusReady;
            error_code_ = kErrorNone;
            return true;
        case kRegThetaFixed:
            theta_fixed_ = value;
            status_ = kStatusReady;
            error_code_ = kErrorNone;
            return true;
        case kRegShots:
            shots_ = std::max<uint64_t>(1, value);
            status_ = kStatusReady;
            error_code_ = kErrorNone;
            return true;
        case kRegCommand:
            if (value == 2) {
                status_ = kStatusReady;
                last_result_ = 0;
                error_code_ = kErrorNone;
            }
            return true;
        default:
            error_code_ = kErrorInvalidRegister;
            status_ = kStatusError;
            return true;
    }
}

QuantumGateRequest VirtualQuantumDevice::request_locked() const {
    return {
        gate_opcode_,
        qubit_count_,
        target_qubit_,
        control_qubit_,
        theta_fixed_,
        shots_,
    };
}

bool VirtualQuantumDevice::validate_request_locked(const QuantumGateRequest& request) {
    if (request.qubit_count == 0 || request.qubit_count > 32 ||
        request.target_qubit >= request.qubit_count ||
        request.control_qubit >= request.qubit_count) {
        error_code_ = kErrorInvalidQubit;
        return false;
    }

    switch (static_cast<QuantumGateOpcode>(request.gate_opcode)) {
        case QuantumGateOpcode::Hadamard:
        case QuantumGateOpcode::PauliX:
        case QuantumGateOpcode::PauliY:
        case QuantumGateOpcode::PauliZ:
        case QuantumGateOpcode::Phase:
        case QuantumGateOpcode::T:
        case QuantumGateOpcode::Cnot:
        case QuantumGateOpcode::Measure:
        case QuantumGateOpcode::Reset:
            return true;
        case QuantumGateOpcode::None:
        default:
            error_code_ = kErrorInvalidGate;
            return false;
    }
}

QuantumGateResult VirtualQuantumDevice::compute_local_locked(const QuantumGateRequest& request) const {
    switch (static_cast<QuantumGateOpcode>(request.gate_opcode)) {
        case QuantumGateOpcode::PauliX:
            return {kStatusDone, 1ull << request.target_qubit, kErrorNone};
        case QuantumGateOpcode::Hadamard:
            return {kStatusDone, request.target_qubit & 1ull, kErrorNone};
        case QuantumGateOpcode::Cnot:
            return {kStatusDone, (1ull << request.control_qubit) | (1ull << request.target_qubit), kErrorNone};
        case QuantumGateOpcode::Measure:
            return {kStatusDone, 0, kErrorNone};
        case QuantumGateOpcode::Reset:
            return {kStatusDone, 0, kErrorNone};
        case QuantumGateOpcode::PauliY:
        case QuantumGateOpcode::PauliZ:
        case QuantumGateOpcode::Phase:
        case QuantumGateOpcode::T:
            return {kStatusDone, request.target_qubit, kErrorNone};
        case QuantumGateOpcode::None:
        default:
            return {kStatusError, 0, kErrorInvalidGate};
    }
}

VqdDump VirtualQuantumDevice::dump() const {
    std::lock_guard<std::mutex> lock(mutex_);
    VqdDump snapshot;
    snapshot.base_address = base_;
    snapshot.size = size_;

    const struct {
        const char* name;
        uint64_t offset;
        const char* access;
    } register_specs[] = {
        {"MAGIC", kRegMagic, "ro"},
        {"VERSION", kRegVersion, "ro"},
        {"STATUS", kRegStatus, "ro"},
        {"QUBIT_COUNT", kRegQubitCount, "rw"},
        {"GATE_OPCODE", kRegGateOpcode, "rw"},
        {"TARGET_QUBIT", kRegTargetQubit, "rw"},
        {"CONTROL_QUBIT", kRegControlQubit, "rw"},
        {"THETA_FIXED", kRegThetaFixed, "rw"},
        {"SHOTS", kRegShots, "rw"},
        {"COMMAND", kRegCommand, "wo"},
        {"LAST_RESULT", kRegLastResult, "ro"},
        {"ERROR_CODE", kRegErrorCode, "ro"},
    };

    snapshot.registers.reserve(sizeof(register_specs) / sizeof(register_specs[0]));
    for (const auto& spec : register_specs) {
        snapshot.registers.push_back({
            spec.name,
            spec.offset,
            base_ + spec.offset,
            read_register(spec.offset),
            spec.access
        });
    }
    return snapshot;
}

bool VirtualQuantumDevice::write_scalar(uint8_t* data, std::size_t len, uint64_t value) const {
    const auto copy_len = std::min<std::size_t>(len, sizeof(value));
    std::memcpy(data, &value, copy_len);
    if (len > copy_len) {
        std::memset(data + copy_len, 0, len - copy_len);
    }
    return true;
}

uint64_t VirtualQuantumDevice::read_scalar(const uint8_t* data, std::size_t len) const {
    uint64_t value = 0;
    std::memcpy(&value, data, std::min<std::size_t>(len, sizeof(value)));
    return value;
}

} // namespace synthesus::kernel::vmm
