#pragma once
// Synthesus 2.0 Phase 7 - SIMD-ready Memory Allocator
#include <cstddef>
#include <cstdlib>
#include <memory>

namespace zo {

class MemoryAllocator {
public:
    static void* aligned_alloc(size_t size, size_t alignment = 64);
    static void aligned_free(void* ptr);
    template<typename T, size_t Align = 64>
    static T* alloc_array(size_t count);
    static size_t pool_usage();
    static void reset_pool();
private:
    static thread_local size_t usage_;
};

template<typename T, size_t Align>
T* MemoryAllocator::alloc_array(size_t count) {
    return static_cast<T*>(aligned_alloc(count * sizeof(T), Align));
}

} // namespace zo
