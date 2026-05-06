#pragma once
// Synthesus 2.0 Phase 7 - Long Term Memory (persistent KN-backed semantic store)
#include "kn_database.hpp"
#include <string>
namespace zo {
class LongTermMemory {
public:
    explicit LongTermMemory(const std::string& db_path = "ltm.kndb");
    void store(const std::string& key, const std::string& value, float weight = 1.0f);
    std::string retrieve(const std::string& key) const;
    std::vector<KNode> search(const std::string& query, size_t top_k = 5) const;
    bool forget(const std::string& key);
    bool flush();
    size_t size() const;
private:
    std::string db_path_;
    KNDatabase db_;
};
} // namespace zo
