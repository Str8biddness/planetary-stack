#pragma once
// Synthesus 2.0 Phase 7 - Episodic Memory (event-based long-term recall)
#include "kn_database.hpp"
#include <string>
#include <vector>
namespace zo {
struct Episode {
    uint64_t id;
    std::string summary;
    std::string emotional_tag;
    float salience{1.0f};
    uint64_t timestamp_ms;
    std::vector<std::string> entities;
};
class EpisodicMemory {
public:
    uint64_t record(const Episode& e);
    std::vector<Episode> recall(const std::string& query, size_t top_k = 5) const;
    std::vector<Episode> recall_by_tag(const std::string& tag) const;
    bool forget(uint64_t id);
    size_t size() const;
    void consolidate(KNDatabase& kn);
private:
    mutable std::mutex mutex_;
    std::vector<Episode> episodes_;
    uint64_t next_id_{1};
};
} // namespace zo
