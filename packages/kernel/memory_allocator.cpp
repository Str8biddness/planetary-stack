#include "memory_allocator.hpp"
#include <cstdlib>
#include <new>

namespace zo {

thread_local size_t MemoryAllocator::usage_ = 0;

void* MemoryAllocator::aligned_alloc(size_t size, size_t alignment) {
#ifdef _WIN32
    void* ptr = _aligned_malloc(size, alignment);
#else
    void* ptr = nullptr;
    if (::posix_memalign(&ptr, alignment, size) != 0) ptr = nullptr;
#endif
    if (!ptr) throw std::bad_alloc();
    usage_ += size;
    return ptr;
}

void MemoryAllocator::aligned_free(void* ptr) {
#ifdef _WIN32
    _aligned_free(ptr);
#else
    ::free(ptr);
#endif
}

size_t MemoryAllocator::pool_usage() { return usage_; }
void MemoryAllocator::reset_pool() { usage_ = 0; }

} // namespace zo
