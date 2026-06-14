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
    find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
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
    if(NOT pybind11_FOUND)
        message(FATAL_ERROR "BUILD_PYBIND=ON requires pybind11. Install the Python package with `python -m pip install pybind11`.")
    endif()
endif()

if(ENABLE_ONNX)
    find_package(onnxruntime QUIET)
endif()

# ── Source files ──
set(KERNEL_SOURCES
    thread_pool.cpp
    message_bus.cpp
    memory_allocator.cpp
    telemetry.cpp
    watchdog.cpp
    ppbrs_router.cpp
    context_memory.cpp
    hemi_reconciler.cpp
    geometric_engine.cpp
    geometric_optics.cpp
    resonance_observer.cpp
    shard_manager.cpp
    fusion_transformer_block.cpp
)

set(REASONING_SOURCES
    ../reasoning/ppbrs.cpp
    ../reasoning/bayesian.cpp
    ../reasoning/causal.cpp
    ../reasoning/symbolic.cpp
    ../reasoning/sinn.cpp
    ../reasoning/planner.cpp
    ../reasoning/ensemble_synth.cpp
)

set(MEMORY_SOURCES
    ../core/memory/working_memory.cpp
    ../core/memory/episodic_memory.cpp
    ../core/memory/long_term_memory.cpp
    ../core/memory/kn_database.cpp
    ../core/memory/self_perception.cpp
)

set(VCU_SOURCES
    emotion_vcu.cpp
    executive_vcu.cpp
    language_vcu.cpp
    memo_vcu.cpp
    motor_vcu.cpp
    voice_vcu.cpp
    perception_vcu.cpp
    sensory_vcu.cpp
    social_vcu.cpp
    ct_vcu.cpp
    vpu_router.cpp
    hardware_router.cpp
)

set(VMM_SOURCES
    vmm/vmm.cpp
    vmm/serial_console.cpp
    vmm/virtual_parameter_device.cpp
    vmm/virtual_quantum_device.cpp
    vmm/virtual_gpu_device.cpp
    vmm/virtual_network_device.cpp
    vmm/virtual_mirror_device.cpp
    vmm/virtual_vpu_device.cpp
    vmm/virtual_sllm_device.cpp
    vmm/virtual_accelerator_device.cpp
)

set(EMUL_SOURCES
    emul_engineering/hardware_profiler.cpp
    emul_engineering/emul_engine.cpp
)

set(ALL_CPP_SOURCES
    ${KERNEL_SOURCES}
    ${VMM_SOURCES}
    ${EMUL_SOURCES}
    ${VCU_SOURCES}
    ${MEMORY_SOURCES}
)

# ── Standalone kernel binary ──
if(BUILD_KERNEL)
    add_executable(synthesus_kernel
        main.cpp
        ${ALL_CPP_SOURCES}
        ../reasoning/ppbrs.cpp
        ../reasoning/sinn.cpp
    )
    target_include_directories(synthesus_kernel PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
        ${CMAKE_CURRENT_SOURCE_DIR}/vmm
        ${CMAKE_CURRENT_SOURCE_DIR}/emul_engineering
        ${CMAKE_CURRENT_SOURCE_DIR}/../reasoning
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
        vmm/test_vmm.cpp
        ${VMM_SOURCES}
    )
    target_include_directories(test_vmm PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/vmm
    )

    # --- EmulEngineering Test ---
    add_executable(test_emul
        emul_engineering/test_emul.cpp
        ${EMUL_SOURCES}
        ${VMM_SOURCES}
    )
    target_include_directories(test_emul PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/vmm
        ${CMAKE_CURRENT_SOURCE_DIR}/emul_engineering
    )
endif()

# ── pybind11 Python module ──
if(BUILD_PYBIND AND pybind11_FOUND)
    pybind11_add_module(_synthesus_kernel
        pybind_module.cpp
        ${ALL_CPP_SOURCES}
        ../reasoning/ppbrs.cpp
        ../reasoning/sinn.cpp
    )
    target_include_directories(_synthesus_kernel PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
        ${CMAKE_CURRENT_SOURCE_DIR}/vmm
        ${CMAKE_CURRENT_SOURCE_DIR}/emul_engineering
        ${CMAKE_CURRENT_SOURCE_DIR}/../reasoning
    )
    target_link_libraries(_synthesus_kernel PRIVATE Threads::Threads)
    
    # Install to Python site-packages
    install(TARGETS _synthesus_kernel LIBRARY DESTINATION .)
endif()

# ── Compile flags ──
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(-O3 -march=native -Wall -Wextra)
endif()

message(STATUS "")
message(STATUS "=== Synthesus 4.0 Kernel Build Configuration ===")
message(STATUS "  Build type:    ${CMAKE_BUILD_TYPE}")
message(STATUS "  C++ standard:  C++${CMAKE_CXX_STANDARD}")
message(STATUS "  Kernel binary: ${BUILD_KERNEL}")
message(STATUS "  pybind11:      ${BUILD_PYBIND} (found: ${pybind11_FOUND})")
message(STATUS "=========================================")
message(STATUS "")
