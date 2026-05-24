#include "vmm.hpp"
#include "virtual_parameter_device.hpp"
#include "virtual_quantum_device.hpp"
#include <iostream>
#include <vector>
#include <fstream>

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <payload_bin>" << std::endl;
        return 1;
    }

    // ... (payload loading)
    std::ifstream file(argv[1], std::ios::binary | std::ios::ate);
    if (!file.is_open()) {
        std::cerr << "Failed to open payload: " << argv[1] << std::endl;
        return 1;
    }

    std::streamsize size = file.tellg();
    file.seekg(0, std::ios::beg);

    std::vector<uint8_t> payload(size);
    if (!file.read(reinterpret_cast<char*>(payload.data()), size)) {
        std::cerr << "Failed to read payload" << std::endl;
        return 1;
    }

    synthesus::kernel::vmm::VMM vmm;
    
    // Register AIOS Devices
    auto vpd = std::make_shared<synthesus::kernel::vmm::VirtualParameterDevice>();
    auto vqd = std::make_shared<synthesus::kernel::vmm::VirtualQuantumDevice>();
    vmm.register_mmio_device(vpd);
    vmm.register_mmio_device(vqd);

    std::cout << "Initializing VMM..." << std::endl;
    if (!vmm.initialize()) {
        std::cerr << "VMM initialization failed. (Check permissions for /dev/kvm)" << std::endl;
        return 1;
    }

    std::cout << "Allocating memory..." << std::endl;
    if (!vmm.allocate_memory(0x1000)) {
        std::cerr << "Memory allocation failed" << std::endl;
        return 1;
    }

    std::cout << "Setting up vCPU..." << std::endl;
    if (!vmm.setup_vcpu()) {
        std::cerr << "vCPU setup failed" << std::endl;
        return 1;
    }

    std::cout << "Loading payload..." << std::endl;
    if (!vmm.load_payload(payload)) {
        std::cerr << "Payload loading failed" << std::endl;
        return 1;
    }

    std::cout << "Running VMM..." << std::endl;
    if (!vmm.run()) {
        std::cerr << "VMM execution failed" << std::endl;
        return 1;
    }

    const auto console_output = vmm.serial_console()->read_output();
    if (!console_output.empty()) {
        std::cout << "Guest console output: " << console_output;
    }

    std::cout << "VMM test completed successfully." << std::endl;
    return 0;
}
