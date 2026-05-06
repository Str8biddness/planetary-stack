#pragma once
// Synthesus 2.0 Phase 7 - KN Database (Knowledge Node Binary Store)
#include <string>
#include <vector>
#include <unordered_map>
#include <mutex>
#include <cstdint>

namespace zo {

struct KNode {
    uint64_t id;
    std::string key;
    std::string value;
    float weight{1.0f};
    uint64_t timestamp_ms{0};
    std::vector<uint64_t> links;
};

class KNDatabase {
public:
    KNDatabase() = default;
    explicit KNDatabase(const std::string& path);
    bool load(const std::string& path);
    bool save(const std::string& path) const;
    bool checkpoint(const std::string& path) const;
    uint64_t insert(const KNode& node);
    bool update(uint64_t id, const KNode& node);
    bool remove(uint64_t id);
    const KNode* find(uint64_t id) const;
    const KNode* find_by_key(const std::string& key) const;
    std::vector<KNode> search(const std::string& query, size_t top_k = 10) const;
    size_t size() const;
    void clear();
private:
    mutable std::mutex mutex_;
    std::unordered_map<uint64_t, KNode> nodes_;
    std::unordered_map<std::string, uint64_t> key_index_;
    uint64_t next_id_{1};
};

} // namespace zo
