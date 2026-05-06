#include "long_term_memory.hpp"
namespace zo {
LongTermMemory::LongTermMemory(const std::string& db_path) : db_path_(db_path) { db_.load(db_path); }
void LongTermMemory::store(const std::string& key, const std::string& value, float weight) {
    auto existing = db_.find_by_key(key);
    if (existing) { KNode n = *existing; n.value = value; n.weight = weight; db_.update(n.id, n); }
    else { KNode n; n.key = key; n.value = value; n.weight = weight; db_.insert(n); }
}
std::string LongTermMemory::retrieve(const std::string& key) const {
    auto n = db_.find_by_key(key); return n ? n->value : "";
}
std::vector<KNode> LongTermMemory::search(const std::string& query, size_t top_k) const {
    return db_.search(query, top_k);
}
bool LongTermMemory::forget(const std::string& key) {
    auto n = db_.find_by_key(key); if (!n) return false; return db_.remove(n->id);
}
bool LongTermMemory::flush() { return db_.save(db_path_); }
size_t LongTermMemory::size() const { return db_.size(); }
} // namespace zo
