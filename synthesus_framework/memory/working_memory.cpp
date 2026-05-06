#include "working_memory.hpp"
namespace zo {
void WorkingMemory::push(const ContextEntry& e) {
    std::lock_guard<std::mutex> lk(mutex_);
    buffer_.push_back(e);
    while (buffer_.size() > capacity_) buffer_.pop_front();
}
void WorkingMemory::clear() { std::lock_guard<std::mutex> lk(mutex_); buffer_.clear(); }
std::vector<ContextEntry> WorkingMemory::get_recent(size_t n) const {
    std::lock_guard<std::mutex> lk(mutex_);
    size_t start = buffer_.size() > n ? buffer_.size() - n : 0;
    return {buffer_.begin() + start, buffer_.end()};
}
size_t WorkingMemory::size() const { std::lock_guard<std::mutex> lk(mutex_); return buffer_.size(); }
void WorkingMemory::set_capacity(size_t cap) { std::lock_guard<std::mutex> lk(mutex_); capacity_ = cap; }
} // namespace zo
