/*
 * Synthesus 4.0 — Unified pybind11 Module Definition
 * AIVM LLC - Production Implementation
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include <string>
#include <vector>
#include <map>
#include <memory>
#include <iomanip>
#include <sstream>

#include "thread_pool.hpp"
#include "message_bus.hpp"
#include "memory_allocator.hpp"
#include "../reasoning/ppbrs.hpp"
#include "../memory/working_memory.hpp"
#include "../automation/watchdog.hpp"
#include "emul_engineering/emul_engine.hpp"
#include "vmm/virtual_parameter_device.hpp"
#include "vmm/virtual_quantum_device.hpp"
#include "vmm/virtual_gpu_device.hpp"
#include "vmm/virtual_network_device.hpp"
#include "vmm/virtual_mirror_device.hpp"
#include "vmm/virtual_vpu_device.hpp"
#include "vmm/virtual_sllm_device.hpp"

namespace py = pybind11;
namespace emul = synthesus::kernel::emul_engineering;
namespace vmm = synthesus::kernel::vmm;

namespace {

using PyFunctionPtr = std::shared_ptr<py::function>;

PyFunctionPtr keep_python_function(py::function fn) {
    return PyFunctionPtr(new py::function(std::move(fn)), [](py::function* callback) {
        if (Py_IsInitialized()) { py::gil_scoped_acquire gil; delete callback; }
        else { callback->release(); delete callback; }
    });
}

std::string hex_u64(uint64_t value) {
    std::ostringstream oss;
    oss << "0x" << std::uppercase << std::hex << std::setw(16) << std::setfill('0') << value;
    return oss.str();
}

py::list bytes_to_list(const std::vector<uint8_t>& bytes) {
    py::list out;
    for (const auto byte : bytes) out.append(static_cast<unsigned int>(byte));
    return out;
}

std::vector<uint8_t> py_bytes_like_to_vector(const py::handle& value) {
    if (py::isinstance<py::bytes>(value)) {
        const std::string bytes = py::cast<std::string>(value);
        return {bytes.begin(), bytes.end()};
    }
    if (py::isinstance<py::bytearray>(value)) {
        py::bytearray bytearray = py::reinterpret_borrow<py::bytearray>(value);
        char* buffer = PyByteArray_AsString(bytearray.ptr());
        const auto size = static_cast<std::size_t>(PyByteArray_Size(bytearray.ptr()));
        return {buffer, buffer + size};
    }
    return py::cast<std::vector<uint8_t>>(value);
}

py::dict vpd_dump_to_dict(const vmm::VpdDump& dump) {
    py::list registers;
    for (const auto& reg : dump.registers) {
        py::dict item;
        item["name"] = reg.name; item["offset"] = reg.offset;
        item["absolute_address_hex"] = hex_u64(reg.absolute_address);
        item["value"] = reg.value; item["value_hex"] = hex_u64(reg.value);
        item["access"] = reg.access; registers.append(item);
    }
    py::dict out;
    out["device"] = "VirtualParameterDevice";
    out["base_address_hex"] = hex_u64(dump.base_address);
    out["registers"] = registers;
    out["selected_parameter"] = py::dict();
    out["selected_parameter"]["key"] = dump.selected_parameter.key;
    out["selected_parameter"]["bytes"] = bytes_to_list(dump.selected_parameter.bytes);
    return out;
}

py::dict vqd_dump_to_dict(const vmm::VqdDump& dump) {
    py::list registers;
    for (const auto& reg : dump.registers) {
        py::dict item;
        item["name"] = reg.name; item["value"] = reg.value;
        item["value_hex"] = hex_u64(reg.value); registers.append(item);
    }
    py::dict out;
    out["device"] = "VirtualQuantumDevice";
    out["registers"] = registers;
    return out;
}

py::dict vgd_dump_to_dict(const vmm::VgdDump& dump) {
    py::list registers;
    for (const auto& reg : dump.registers) {
        py::dict item;
        item["name"] = reg.name; item["value"] = reg.value;
        item["value_hex"] = hex_u64(reg.value); registers.append(item);
    }
    py::dict out;
    out["device"] = "VirtualGPUDevice";
    out["gpu_model"] = dump.gpu_model;
    out["vram_mb"] = dump.vram_total_mb;
    out["registers"] = registers;
    return out;
}

py::dict vnd_dump_to_dict(const vmm::VndDump& dump) {
    py::list registers;
    for (const auto& reg : dump.registers) {
        py::dict item;
        item["name"] = reg.name; item["value"] = reg.value;
        item["value_hex"] = hex_u64(reg.value); registers.append(item);
    }
    py::dict out;
    out["device"] = "VirtualNetworkDevice";
    out["status"] = dump.status;
    out["last_query"] = dump.last_query;
    out["registers"] = registers;
    return out;
}

py::dict vmd_dump_to_dict(const vmm::VmdDump& dump) {
    py::list registers;
    for (const auto& reg : dump.registers) {
        py::dict item;
        item["name"] = reg.name; item["value"] = reg.value;
        item["value_hex"] = hex_u64(reg.value); registers.append(item);
    }
    py::dict out;
    out["device"] = "VirtualMirrorDevice";
    out["status"] = dump.status;
    out["last_sync_ts"] = dump.last_sync_ts;
    out["registers"] = registers;
    return out;
}

py::dict vvpu_dump_to_dict(const vmm::VvpuDump& dump) {
    py::list registers;
    for (const auto& reg : dump.registers) {
        py::dict item;
        item["name"] = reg.name; item["value"] = reg.value;
        item["value_hex"] = hex_u64(reg.value); registers.append(item);
    }
    py::dict out;
    out["device"] = "VirtualVpuDevice";
    out["status"] = dump.status;
    out["active_nodes"] = dump.active_nodes;
    out["last_routed_node_hash"] = dump.last_routed_node_hash;
    out["registers"] = registers;
    return out;
}

py::dict sllm_dump_to_dict(const vmm::SllmDump& dump) {
    py::list registers;
    for (const auto& reg : dump.registers) {
        py::dict item;
        item["name"] = reg.name; item["value"] = reg.value;
        item["value_hex"] = hex_u64(reg.value); registers.append(item);
    }
    py::dict out;
    out["device"] = "VirtualSllmDevice";
    out["status"] = dump.status;
    out["vocab_size"] = dump.vocab_size;
    out["pattern_count"] = dump.pattern_count;
    out["registers"] = registers;
    return out;
}

} // namespace

PYBIND11_MODULE(_synthesus_kernel, m) {
    m.doc() = "Synthesus 4.0 C++ Kernel - AIOS Interface";

    py::class_<emul::CPUInfo>(m, "CpuProfile")
        .def_readwrite("model", &emul::CPUInfo::model)
        .def_readwrite("cores", &emul::CPUInfo::cores)
        .def_readwrite("features", &emul::CPUInfo::features);

    py::class_<emul::MemoryInfo>(m, "MemoryProfile")
        .def_readwrite("total_ram_mb", &emul::MemoryInfo::total_ram_mb);

    py::class_<emul::HostHardwareMap>(m, "HostHardwareMap")
        .def_readwrite("cpu", &emul::HostHardwareMap::cpu)
        .def_readwrite("memory", &emul::HostHardwareMap::memory)
        .def_readwrite("accelerators", &emul::HostHardwareMap::accelerators);

    py::class_<emul::EmulEngine>(m, "EmulEngine", py::dynamic_attr())
        .def(py::init<>())
        .def("initialize", &emul::EmulEngine::initialize)
        .def("generate_abstraction", &emul::EmulEngine::generate_abstraction)
        .def("run_abstraction", [](emul::EmulEngine& e) { py::gil_scoped_release r; return e.run_abstraction(); })
        .def("get_host_map", &emul::EmulEngine::get_host_map)
        .def("dump_vpd", [](const emul::EmulEngine& e) { return vpd_dump_to_dict(e.dump_vpd()); })
        .def("dump_vqd", [](const emul::EmulEngine& e) { return vqd_dump_to_dict(e.dump_vqd()); })
        .def("dump_vgd", [](const emul::EmulEngine& e) { return vgd_dump_to_dict(e.dump_vgd()); })
        .def("dump_vnd", [](const emul::EmulEngine& e) { return vnd_dump_to_dict(e.dump_vnd()); })
        .def("dump_vmd", [](const emul::EmulEngine& e) { return vmd_dump_to_dict(e.dump_vmd()); })
        .def("dump_vvpu", [](const emul::EmulEngine& e) { return vvpu_dump_to_dict(e.dump_vvpu()); })
        .def("dump_sllm", [](const emul::EmulEngine& e) { return sllm_dump_to_dict(e.dump_sllm()); })
        .def("read_console_output", &emul::EmulEngine::read_console_output)
        .def("write_console_input", &emul::EmulEngine::write_console_input)
        .def("set_blueprint_lookup", [](emul::EmulEngine& e, py::function l) {
            auto cb = keep_python_function(std::move(l));
            e.set_blueprint_lookup([cb](const std::string& h, std::size_t k) {
                py::gil_scoped_acquire gil; return py::str((*cb)(h, k)).cast<std::string>();
            });
        })
        .def("clear_blueprint_lookup", &emul::EmulEngine::clear_blueprint_lookup)
        .def("set_blueprint_top_k", &emul::EmulEngine::set_blueprint_top_k)
        .def("get_blueprint_top_k", &emul::EmulEngine::get_blueprint_top_k)
        .def("query_blueprints", &emul::EmulEngine::query_blueprints)
        .def("set_parameter_lookup", [](emul::EmulEngine& e, py::function l) {
            auto cb = keep_python_function(std::move(l));
            e.set_parameter_lookup([cb](const std::string& p) {
                py::gil_scoped_acquire gil; return py_bytes_like_to_vector((*cb)(p));
            });
        })
        .def("clear_parameter_lookup", &emul::EmulEngine::clear_parameter_lookup)
        .def("map_parameter", &emul::EmulEngine::map_parameter)
        .def("mapped_parameter_count", &emul::EmulEngine::mapped_parameter_count)
        .def("set_network_handler", [](emul::EmulEngine& e, py::function l) {
            auto cb = keep_python_function(std::move(l));
            e.set_network_handler([cb](const std::string& q) {
                py::gil_scoped_acquire gil; (*cb)(q);
            });
        })
        .def("set_network_status", &emul::EmulEngine::set_network_status)
        .def("set_sync_handler", [](emul::EmulEngine& e, py::function l) {
            auto cb = keep_python_function(std::move(l));
            e.set_sync_handler([cb]() {
                py::gil_scoped_acquire gil; (*cb)();
            });
        })
        .def("update_sync_state", &emul::EmulEngine::update_sync_state)
        .def("register_vpu_node", &emul::EmulEngine::register_vpu_node)
        .def("update_vpu_metrics", &emul::EmulEngine::update_vpu_metrics)
        .def("set_vpu_dispatcher", [](emul::EmulEngine& e, py::function l) {
            auto cb = keep_python_function(std::move(l));
            e.set_vpu_dispatcher([cb](uint32_t n, uint32_t r) {
                py::gil_scoped_acquire gil; (*cb)(n, r);
            });
        })
        .def("set_vpu_result", [](emul::EmulEngine& e, py::bytes c) {
            std::string s = c; e.set_vpu_result({s.begin(), s.end()});
        })
        .def("set_sllm_handler", [](emul::EmulEngine& e, py::function l) {
            auto cb = keep_python_function(std::move(l));
            e.set_sllm_handler([cb](const std::string& c) {
                py::gil_scoped_acquire gil; return py::str((*cb)(c)).cast<std::string>();
            });
        })
        .def("update_sllm_stats", &emul::EmulEngine::update_sllm_stats)
        .def("set_secure_key", [](emul::EmulEngine& e, py::bytes k) { 
             std::string s = k; return e.set_secure_key({s.begin(), s.end()}); 
        })
        .def("decrypt_ipc", [](emul::EmulEngine& e, py::bytes c) -> py::bytes {
             std::string s = c; auto p = e.decrypt_ipc({s.begin(), s.end()});
             return py::bytes((char*)p.data(), p.size());
        });

    py::class_<vmm::VirtualQuantumDevice, std::shared_ptr<vmm::VirtualQuantumDevice>>(m, "VirtualQuantumDevice")
        .def(py::init<uint64_t, uint64_t>())
        .def("write64", [](vmm::VirtualQuantumDevice& d, uint64_t o, uint64_t v) { d.write(o, (uint8_t*)&v, 8); })
        .def("read64", [](vmm::VirtualQuantumDevice& d, uint64_t o) { uint64_t v; d.read(o, (uint8_t*)&v, 8); return v; })
        .def("dump", [](const vmm::VirtualQuantumDevice& d) { return vqd_dump_to_dict(d.dump()); })
        .def("set_executor", [](vmm::VirtualQuantumDevice& d, py::object e) {
            d.set_executor([e = std::move(e)](const vmm::QuantumGateRequest& r) -> vmm::QuantumGateResult {
                py::gil_scoped_acquire gil;
                py::dict res = e(r.gate_opcode);
                return { res["status"].cast<uint64_t>(), res["result"].cast<uint64_t>(), 0 };
            });
        });

    m.attr("__version__") = "4.0.0";
}
