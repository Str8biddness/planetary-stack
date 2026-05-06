#pragma once
// Synthesus 2.0 Phase 7 - Working Memory (short-term context buffer)
#include "kn_database.hpp"
#include <deque>
#include <string>
namespace zo {
struct ContextEntry { std::string role; std::string content; uint64_t ts; };
class WorkingMemory {
public:
    void push(const ContextEntry& e);
    void clear();
    std::vector<ContextEntry> get_recent(size_t n = 10) const;
    size_t size() const;
    void set_capacity(size_t cap);
private:
    mutable std::mutex mutex_;
    std::deque<ContextEntry> buffer_;
    size_t capacity_{256};
};
} // namespace zo
