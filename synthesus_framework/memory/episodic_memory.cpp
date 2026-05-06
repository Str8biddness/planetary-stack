#include "episodic_memory.hpp"
#include <algorithm>
namespace zo {
uint64_t EpisodicMemory::record(const Episode& e) {
    std::lock_guard<std::mutex> lk(mutex_);
    Episode ep = e; ep.id = next_id_++;
    episodes_.push_back(ep);
    return ep.id;
}
std::vector<Episode> EpisodicMemory::recall(const std::string& query, size_t top_k) const {
    std::lock_guard<std::mutex> lk(mutex_);
    std::vector<std::pair<float,const Episode*>> scored;
    for (auto& ep : episodes_) {
        float score = ep.salience;
        if (ep.summary.find(query) != std::string::npos) score += 2.0f;
        for (auto& ent : ep.entities) if (ent.find(query) != std::string::npos) score += 1.0f;
        scored.push_back({score, &ep});
    }
    std::sort(scored.begin(), scored.end(), [](auto& a, auto& b){ return a.first > b.first; });
    std::vector<Episode> res;
    for (size_t i = 0; i < std::min(top_k, scored.size()); ++i) res.push_back(*scored[i].second);
    return res;
}
std::vector<Episode> EpisodicMemory::recall_by_tag(const std::string& tag) const {
    std::lock_guard<std::mutex> lk(mutex_);
    std::vector<Episode> res;
    for (auto& ep : episodes_) if (ep.emotional_tag == tag) res.push_back(ep);
    return res;
}
bool EpisodicMemory::forget(uint64_t id) {
    std::lock_guard<std::mutex> lk(mutex_);
    auto it = std::find_if(episodes_.begin(), episodes_.end(), [id](auto& ep){ return ep.id == id; });
    if (it == episodes_.end()) return false;
    episodes_.erase(it); return true;
}
size_t EpisodicMemory::size() const { std::lock_guard<std::mutex> lk(mutex_); return episodes_.size(); }
void EpisodicMemory::consolidate(KNDatabase& kn) {
    std::lock_guard<std::mutex> lk(mutex_);
    for (auto& ep : episodes_) {
        if (ep.salience >= 0.8f) {
            KNode n; n.key = "episode:" + std::to_string(ep.id);
            n.value = ep.summary; n.weight = ep.salience;
            kn.insert(n);
        }
    }
}
} // namespace zo
