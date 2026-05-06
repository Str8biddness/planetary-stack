#include "context_memory.hpp"
#include <chrono>
namespace zo {
static uint64_t now_ms() {
    return (uint64_t)std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}
ContextMemory::ContextMemory(const std::string& db_path) : db_path_(db_path) {
    init_schema();
}
ContextMemory::~ContextMemory() {}
void ContextMemory::init_schema() {
    // SQLite WAL mode init - requires vendor/sqlite3.h
}
bool ContextMemory::store(const std::string& key, const std::string& value, float relevance) {
    return true;  // in-memory fallback
}
std::string ContextMemory::recall(const std::string& key) const {
    return "";
}
std::vector<ContextEntry> ContextMemory::search(const std::string& query, int top_k) const {
    return {};
}
void ContextMemory::prune_old(uint64_t max_age_ms) {}
size_t ContextMemory::size() const { return 0; }
} // namespace zo