#pragma once

#include "vmm.hpp"
#include <cstddef>
#include <cstdint>
#include <functional>
#include <mutex>
#include <string>
#include <vector>

namespace synthesus::kernel::vmm {

enum class QuantumGateOpcode : uint64_t {
    None = 0,
    Hadamard = 1,
    PauliX = 2,
    PauliY = 3,
    PauliZ = 4,
    Phase = 5,
    T = 6,
    Cnot = 7,
    Measure = 8,
    Reset = 9,
};

struct QuantumGateRequest {
    uint64_t gate_opcode{0};
    uint64_t qubit_count{1};
    uint64_t target_qubit{0};
    uint64_t control_qubit{0};
    uint64_t theta_fixed{0};
    uint64_t shots{1};
};

struct QuantumGateResult {
    uint64_t status{0};
    uint64_t result{0};
    uint64_t error_code{0};
};

struct VqdRegisterDump {
    std::string name;
    uint64_t offset{0};
    uint64_t absolute_address{0};
    uint64_t value{0};
    std::string access;
};

struct VqdDump {
    uint64_t base_address{0};
    uint64_t size{0};
    std::vector<VqdRegisterDump> registers;
};

class VirtualQuantumDevice final : public MMIODevice {
public:
    using QuantumExecutor = std::function<QuantumGateResult(const QuantumGateRequest&)>;

    static constexpr uint64_t kDefaultBase = 0xF1000000ull;
    static constexpr uint64_t kDefaultSize = 0x1000ull;
    static constexpr uint64_t kMagic = 0x56514431ull; // "VQD1"

    explicit VirtualQuantumDevice(uint64_t base = kDefaultBase, uint64_t size = kDefaultSize);

    uint64_t base_address() const override { return base_; }
    uint64_t size() const override { return size_; }
    bool read(uint64_t offset, uint8_t* data, std::size_t len) override;
    bool write(uint64_t offset, const uint8_t* data, std::size_t len) override;

    QuantumGateResult compute_quantum_gate();
    void set_executor(QuantumExecutor executor);
    void clear_executor();
    VqdDump dump() const;

private:
    enum Register : uint64_t {
        kRegMagic = 0x00,
        kRegVersion = 0x08,
        kRegStatus = 0x10,
        kRegQubitCount = 0x18,
        kRegGateOpcode = 0x20,
        kRegTargetQubit = 0x28,
        kRegControlQubit = 0x30,
        kRegThetaFixed = 0x38,
        kRegShots = 0x40,
        kRegCommand = 0x48,
        kRegLastResult = 0x50,
        kRegErrorCode = 0x58,
    };

    enum Status : uint64_t {
        kStatusIdle = 0,
        kStatusReady = 1,
        kStatusBusy = 2,
        kStatusDone = 3,
        kStatusError = 4,
    };

    enum ErrorCode : uint64_t {
        kErrorNone = 0,
        kErrorInvalidRegister = 1,
        kErrorInvalidQubit = 2,
        kErrorInvalidGate = 3,
        kErrorExecutorFailure = 4,
    };

    uint64_t read_register(uint64_t offset) const;
    bool write_register(uint64_t offset, uint64_t value);
    bool write_scalar(uint8_t* data, std::size_t len, uint64_t value) const;
    uint64_t read_scalar(const uint8_t* data, std::size_t len) const;
    QuantumGateRequest request_locked() const;
    QuantumGateResult compute_local_locked(const QuantumGateRequest& request) const;
    bool validate_request_locked(const QuantumGateRequest& request);

    uint64_t base_;
    uint64_t size_;
    uint64_t status_{kStatusReady};
    uint64_t qubit_count_{1};
    uint64_t gate_opcode_{0};
    uint64_t target_qubit_{0};
    uint64_t control_qubit_{0};
    uint64_t theta_fixed_{0};
    uint64_t shots_{1};
    uint64_t last_result_{0};
    uint64_t error_code_{kErrorNone};
    QuantumExecutor executor_;
    mutable std::mutex mutex_;
};

} // namespace synthesus::kernel::vmm
