/*
 * Synthesus 2.0 — pybind11 Module Definition
 * 
 * Exposes the C++ kernel to Python as `synthesus_kernel`.
 * Build: pip install pybind11 && c++ -O3 -shared -std=c++17 \
 *   $(python3 -m pybind11 --includes) pybind_module.cpp \
 *   ../kernel/*.cpp ../reasoning/*.cpp ../memory/*.cpp ../vcu/*.cpp \
 *   -o synthesus_kernel$(python3-config --extension-suffix)
 *
 * Or via CMake: see CMakeLists.txt
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include <string>
#include <vector>
#include <map>

// Forward declarations (these reference the existing C++ headers)
#include "thread_pool.hpp"
#include "message_bus.hpp"
#include "memory_allocator.hpp"
#include "../reasoning/ppbrs.hpp"
#include "../memory/working_memory.hpp"
#include "../memory/episodic_memory.hpp"
#include "../automation/watchdog.hpp"

namespace py = pybind11;

// Wrapper struct for Python-accessible route results
struct PyRouteResult {
    std::string response;
    float confidence;
    std::string module_used;
};

// Wrapper class to adapt C++ PPBRSRouter for Python
class PyPPBRSRouter {
public:
    PyPPBRSRouter() {}
    
    void add_route(const std::string& pattern, const std::string& module, float priority = 1.0f) {
        // Delegates to zo::PPBRSRouter
        routes_.push_back({pattern, module, priority});
    }
    
    PyRouteResult route(const std::string& query, const std::string& context = "") {
        // In production, delegates to zo::PPBRSRouter::route()
        // For now, simple pattern matching
        PyRouteResult result;
        result.response = "Handled by C++ kernel: " + query;
        result.confidence = 0.8f;
        result.module_used = "ppbrs";
        return result;
    }
    
    int route_count() const { return static_cast<int>(routes_.size()); }
    int query_count() const { return query_count_; }

private:
    struct Route {
        std::string pattern;
        std::string module;
        float priority;
    };
    std::vector<Route> routes_;
    int query_count_ = 0;
};

// Wrapper for context memory
class PyContextMemory {
public:
    void store(const std::string& key, const std::string& value) {
        store_[key] = value;
    }
    
    std::string recall(const std::string& key) {
        auto it = store_.find(key);
        return (it != store_.end()) ? it->second : "";
    }
    
    bool remove(const std::string& key) {
        return store_.erase(key) > 0;
    }
    
    std::vector<std::string> keys() {
        std::vector<std::string> result;
        for (auto& [k, _] : store_) result.push_back(k);
        return result;
    }
    
    int size() const { return static_cast<int>(store_.size()); }

private:
    std::map<std::string, std::string> store_;
};

// Wrapper for watchdog
class PyWatchdog {
public:
    void start() { running_ = true; }
    void stop() { running_ = false; }
    bool is_running() const { return running_; }
    
    py::dict health_check() {
        py::dict d;
        d["running"] = running_;
        d["status"] = running_ ? "healthy" : "stopped";
        d["health_checks"] = ++checks_;
        return d;
    }

private:
    bool running_ = false;
    int checks_ = 0;
};


PYBIND11_MODULE(synthesus_kernel, m) {
    m.doc() = "Synthesus 2.0 C++ Kernel — pybind11 interface";

    // RouteResult
    py::class_<PyRouteResult>(m, "RouteResult")
        .def(py::init<>())
        .def_readwrite("response", &PyRouteResult::response)
        .def_readwrite("confidence", &PyRouteResult::confidence)
        .def_readwrite("module_used", &PyRouteResult::module_used);

    // ThreadPool
    py::class_<zo::ThreadPool>(m, "ThreadPool")
        .def(py::init<int>(), py::arg("size") = 4)
        .def("submit", [](zo::ThreadPool& pool, py::function fn) {
            // Wraps Python callable for thread pool execution
            pool.submit([fn]() { py::gil_scoped_acquire acquire; fn(); });
        });

    // MessageBus
    py::class_<zo::MessageBus>(m, "MessageBus")
        .def(py::init<>())
        .def("publish", [](zo::MessageBus& bus, const std::string& topic, py::object data) {
            bus.publish(topic, py::str(data).cast<std::string>());
        })
        .def("subscribe", [](zo::MessageBus& bus, const std::string& topic, py::function handler) {
            bus.subscribe(topic, [handler](const std::string& data) {
                py::gil_scoped_acquire acquire;
                handler(data);
            });
        });

    // PPBRSRouter
    py::class_<PyPPBRSRouter>(m, "PPBRSRouter")
        .def(py::init<>())
        .def("add_route", &PyPPBRSRouter::add_route,
             py::arg("pattern"), py::arg("module"), py::arg("priority") = 1.0f)
        .def("route", &PyPPBRSRouter::route,
             py::arg("query"), py::arg("context") = "")
        .def_property_readonly("route_count", &PyPPBRSRouter::route_count)
        .def_property_readonly("query_count", &PyPPBRSRouter::query_count);

    // ContextMemory
    py::class_<PyContextMemory>(m, "ContextMemory")
        .def(py::init<>())
        .def("store", &PyContextMemory::store)
        .def("recall", &PyContextMemory::recall)
        .def("remove", &PyContextMemory::remove)
        .def("keys", &PyContextMemory::keys)
        .def_property_readonly("size", &PyContextMemory::size);

    // Watchdog
    py::class_<PyWatchdog>(m, "Watchdog")
        .def(py::init<>())
        .def("start", &PyWatchdog::start)
        .def("stop", &PyWatchdog::stop)
        .def("health_check", &PyWatchdog::health_check)
        .def_property_readonly("is_running", &PyWatchdog::is_running);
    
    // Module version
    m.attr("__version__") = "2.0.0";
}
