#pragma once
// Synthesus 2.0 - ContextMemory: SQLite WAL-backed context store
#include <string>
#include <vector>
#include <cstdint>
namespace zo {
struct ContextEntry {
    std::string key;
    std::string value;
    uint64_t timestamp_ms;
    float relevance;
};
class ContextMemory {
public:
    explicit ContextMemory(const std::string& db_path = "context.db");
    ~ContextMemory();
    bool store(const std::string& key, const std::string& value, float relevance = 1.0f);
    std::string recall(const std::string& key) const;
    std::vector<ContextEntry> search(const std::string& query, int top_k = 5) const;
    void prune_old(uint64_t max_age_ms = 86400000ULL);  // 24h default
    size_t size() const;
private:
    std::string db_path_;
    void* db_ = nullptr;  // sqlite3*
    void init_schema();
};
} // namespace zo