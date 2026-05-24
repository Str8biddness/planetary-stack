cmake_minimum_required(VERSION 3.18)
project(Synthesus VERSION 3.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ── Options ──
option(BUILD_PYBIND "Build pybind11 Python module" ON)
option(BUILD_KERNEL "Build standalone C++ kernel binary" ON)
option(BUILD_TESTS  "Build C++ unit tests" OFF)
option(ENABLE_ONNX  "Enable ONNX Runtime support" OFF)

# ── Find packages ──
find_package(Threads REQUIRED)

if(BUILD_PYBIND)
    find_package(pybind11 CONFIG QUIET)
    if(NOT pybind11_FOUND)
        # Try pip-installed pybind11
        execute_process(
            COMMAND ${Python3_EXECUTABLE} -m pybind11 --cmakedir
            OUTPUT_VARIABLE pybind11_DIR
            OUTPUT_STRIP_TRAILING_WHITESPACE
            ERROR_QUIET
        )
        if(pybind11_DIR)
            find_package(pybind11 CONFIG PATHS ${pybind11_DIR})
        endif()
    endif()
endif()

if(ENABLE_ONNX)
    find_package(onnxruntime QUIET)
endif()

# ── Source files ──
set(KERNEL_SOURCES
    kernel/thread_pool.cpp
    kernel/message_bus.cpp
    kernel/memory_allocator.cpp
)

set(REASONING_SOURCES
    reasoning/ppbrs.cpp
    reasoning/bayesian.cpp
    reasoning/causal.cpp
    reasoning/symbolic.cpp
    reasoning/sinn.cpp
    reasoning/planner.cpp
    reasoning/ensemble_synth.cpp
)

set(MEMORY_SOURCES
    memory/working_memory.cpp
    memory/episodic_memory.cpp
    memory/long_term_memory.cpp
    memory/kn_database.cpp
    memory/self_perception.cpp
)

set(VCU_SOURCES
    vcu/emotion_vcu.cpp
    vcu/executive_vcu.cpp
    vcu/language_vcu.cpp
    vcu/memo_vcu.cpp
    vcu/motor_vcu.cpp
    vcu/perception_vcu.cpp
    vcu/sensory_vcu.cpp
    vcu/social_vcu.cpp
    vcu/ct_vcu.cpp
    vcu/vpu_router.cpp
)

set(AUTOMATION_SOURCES
    automation/watchdog.cpp
    automation/telemetry.cpp
)

set(CORE_CPP_SOURCES
    core/ppbrs_router.cpp
    core/context_memory.cpp
    core/hemi_reconciler.cpp
)

set(VMM_SOURCES
    kernel/vmm/vmm.cpp
    kernel/vmm/serial_console.cpp
    kernel/vmm/virtual_parameter_device.cpp
    kernel/vmm/virtual_quantum_device.cpp
    kernel/vmm/virtual_gpu_device.cpp
    kernel/vmm/virtual_network_device.cpp
    kernel/vmm/virtual_mirror_device.cpp
    kernel/vmm/virtual_vpu_device.cpp
    kernel/vmm/virtual_sllm_device.cpp
)

set(EMUL_SOURCES
    kernel/emul_engineering/hardware_profiler.cpp
    kernel/emul_engineering/emul_engine.cpp
)

set(ALL_CPP_SOURCES
    ${KERNEL_SOURCES}
    ${VMM_SOURCES}
    ${EMUL_SOURCES}
    ${REASONING_SOURCES}
    ${MEMORY_SOURCES}
    ${VCU_SOURCES}
    ${AUTOMATION_SOURCES}
    ${CORE_CPP_SOURCES}
)

# ── Standalone kernel binary ──
if(BUILD_KERNEL)
    add_executable(synthesus_kernel
        main.cpp
        ${ALL_CPP_SOURCES}
    )
    target_include_directories(synthesus_kernel PRIVATE
        ${CMAKE_SOURCE_DIR}
        ${CMAKE_SOURCE_DIR}/kernel
        ${CMAKE_SOURCE_DIR}/kernel/vmm
        ${CMAKE_SOURCE_DIR}/kernel/emul_engineering
        ${CMAKE_SOURCE_DIR}/reasoning
        ${CMAKE_SOURCE_DIR}/memory
        ${CMAKE_SOURCE_DIR}/vcu
        ${CMAKE_SOURCE_DIR}/core
    )
    target_link_libraries(synthesus_kernel PRIVATE Threads::Threads)
    
    if(ENABLE_ONNX AND onnxruntime_FOUND)
        target_link_libraries(synthesus_kernel PRIVATE onnxruntime::onnxruntime)
        target_compile_definitions(synthesus_kernel PRIVATE ONNX_ENABLED=1)
    endif()
    
    set_target_properties(synthesus_kernel PROPERTIES
        OUTPUT_NAME "zo_kernel"
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
    )

    # --- AIOS VMM Test ---
    add_executable(test_vmm
        kernel/vmm/test_vmm.cpp
        ${VMM_SOURCES}
    )
    target_include_directories(test_vmm PRIVATE
        ${CMAKE_SOURCE_DIR}/kernel/vmm
    )

    # --- EmulEngineering Test ---
    add_executable(test_emul
        kernel/emul_engineering/test_emul.cpp
        ${EMUL_SOURCES}
        ${VMM_SOURCES}
    )
    target_include_directories(test_emul PRIVATE
        ${CMAKE_SOURCE_DIR}/kernel/vmm
        ${CMAKE_SOURCE_DIR}/kernel/emul_engineering
    )

    # Assemble test payload
    add_custom_command(
        OUTPUT ${CMAKE_BINARY_DIR}/test_payload.bin
        COMMAND as -32 -o ${CMAKE_BINARY_DIR}/test_payload.o ${CMAKE_SOURCE_DIR}/kernel/vmm/test_payload.S
        COMMAND objcopy -O binary -j .text ${CMAKE_BINARY_DIR}/test_payload.o ${CMAKE_BINARY_DIR}/test_payload.bin
        DEPENDS ${CMAKE_SOURCE_DIR}/kernel/vmm/test_payload.S
        COMMENT "Assembling VMM test payload"
    )
    add_custom_target(vmm_payload ALL DEPENDS ${CMAKE_BINARY_DIR}/test_payload.bin)
    add_dependencies(test_vmm vmm_payload)
endif()

# ── pybind11 Python module ──
if(BUILD_PYBIND AND pybind11_FOUND)
    pybind11_add_module(_synthesus_kernel
        kernel/pybind_module.cpp
        ${ALL_CPP_SOURCES}
    )
    target_include_directories(_synthesus_kernel PRIVATE
        ${CMAKE_SOURCE_DIR}
        ${CMAKE_SOURCE_DIR}/kernel
        ${CMAKE_SOURCE_DIR}/kernel/vmm
        ${CMAKE_SOURCE_DIR}/kernel/emul_engineering
        ${CMAKE_SOURCE_DIR}/reasoning
        ${CMAKE_SOURCE_DIR}/memory
        ${CMAKE_SOURCE_DIR}/vcu
        ${CMAKE_SOURCE_DIR}/core
    )
    target_link_libraries(_synthesus_kernel PRIVATE Threads::Threads)
    
    if(ENABLE_ONNX AND onnxruntime_FOUND)
        target_link_libraries(_synthesus_kernel PRIVATE onnxruntime::onnxruntime)
        target_compile_definitions(_synthesus_kernel PRIVATE ONNX_ENABLED=1)
    endif()
    
    # Install to Python site-packages
    install(TARGETS _synthesus_kernel LIBRARY DESTINATION .)
endif()

# ── Compile flags ──
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(-O3 -march=native -Wall -Wextra)
endif()

message(STATUS "")
message(STATUS "=== Synthesus 3.0 Quadbrain Build Configuration ===")
message(STATUS "  Build type:    ${CMAKE_BUILD_TYPE}")
message(STATUS "  C++ standard:  C++${CMAKE_CXX_STANDARD}")
message(STATUS "  Kernel binary: ${BUILD_KERNEL}")
message(STATUS "  pybind11:      ${BUILD_PYBIND} (found: ${pybind11_FOUND})")
message(STATUS "  ONNX Runtime:  ${ENABLE_ONNX}")
message(STATUS "=========================================")
message(STATUS "")
