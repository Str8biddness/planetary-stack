#include "kn_database.hpp"
#include <fstream>
#include <algorithm>
#include <sstream>

namespace zo {

KNDatabase::KNDatabase(const std::string& path) { load(path); }

bool KNDatabase::load(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    std::lock_guard<std::mutex> lk(mutex_);
    nodes_.clear(); key_index_.clear();
    while (f.good()) {
        KNode n;
        uint32_t klen, vlen, lcount;
        f.read((char*)&n.id, 8);
        f.read((char*)&n.weight, 4);
        f.read((char*)&n.timestamp_ms, 8);
        f.read((char*)&klen, 4); if (!f) break;
        n.key.resize(klen); f.read(&n.key[0], klen);
        f.read((char*)&vlen, 4);
        n.value.resize(vlen); f.read(&n.value[0], vlen);
        f.read((char*)&lcount, 4);
        n.links.resize(lcount);
        f.read((char*)n.links.data(), lcount * 8);
        if (!f) break;
        nodes_[n.id] = n;
        key_index_[n.key] = n.id;
        if (n.id >= next_id_) next_id_ = n.id + 1;
    }
    return true;
}

bool KNDatabase::save(const std::string& path) const {
    std::ofstream f(path, std::ios::binary);
    if (!f) return false;
    std::lock_guard<std::mutex> lk(mutex_);
    for (auto& [id, n] : nodes_) {
        uint32_t klen = n.key.size(), vlen = n.value.size(), lcount = n.links.size();
        f.write((char*)&n.id, 8); f.write((char*)&n.weight, 4);
        f.write((char*)&n.timestamp_ms, 8);
        f.write((char*)&klen, 4); f.write(n.key.data(), klen);
        f.write((char*)&vlen, 4); f.write(n.value.data(), vlen);
        f.write((char*)&lcount, 4); f.write((char*)n.links.data(), lcount * 8);
    }
    return true;
}

bool KNDatabase::checkpoint(const std::string& path) const { return save(path + ".ckpt"); }

uint64_t KNDatabase::insert(const KNode& node) {
    std::lock_guard<std::mutex> lk(mutex_);
    KNode n = node; n.id = next_id_++;
    key_index_[n.key] = n.id;
    nodes_[n.id] = std::move(n);
    return nodes_[n.id].id;
}

bool KNDatabase::update(uint64_t id, const KNode& node) {
    std::lock_guard<std::mutex> lk(mutex_);
    auto it = nodes_.find(id);
    if (it == nodes_.end()) return false;
    key_index_.erase(it->second.key);
    it->second = node; it->second.id = id;
    key_index_[it->second.key] = id;
    return true;
}

bool KNDatabase::remove(uint64_t id) {
    std::lock_guard<std::mutex> lk(mutex_);
    auto it = nodes_.find(id);
    if (it == nodes_.end()) return false;
    key_index_.erase(it->second.key);
    nodes_.erase(it); return true;
}

const KNode* KNDatabase::find(uint64_t id) const {
    std::lock_guard<std::mutex> lk(mutex_);
    auto it = nodes_.find(id);
    return it != nodes_.end() ? &it->second : nullptr;
}

const KNode* KNDatabase::find_by_key(const std::string& key) const {
    std::lock_guard<std::mutex> lk(mutex_);
    auto it = key_index_.find(key);
    if (it == key_index_.end()) return nullptr;
    auto jt = nodes_.find(it->second);
    return jt != nodes_.end() ? &jt->second : nullptr;
}

std::vector<KNode> KNDatabase::search(const std::string& query, size_t top_k) const {
    std::lock_guard<std::mutex> lk(mutex_);
    std::vector<std::pair<float,const KNode*>> scored;
    for (auto& [id, n] : nodes_) {
        if (n.key.find(query) != std::string::npos ||
            n.value.find(query) != std::string::npos)
            scored.push_back({n.weight, &n});
    }
    std::sort(scored.begin(), scored.end(),
        [](auto& a, auto& b){ return a.first > b.first; });
    std::vector<KNode> res;
    for (size_t i = 0; i < std::min(top_k, scored.size()); ++i)
        res.push_back(*scored[i].second);
    return res;
}

size_t KNDatabase::size() const {
    std::lock_guard<std::mutex> lk(mutex_); return nodes_.size();
}
void KNDatabase::clear() {
    std::lock_guard<std::mutex> lk(mutex_); nodes_.clear(); key_index_.clear();
}

} // namespace zo
