#include "shard_manager.hpp"
#include <fstream>
#include <iostream>
#include <algorithm>

namespace zo {

ShardManager::ShardManager(std::shared_ptr<GeometricEngine> engine)
    : engine_(engine) {}

bool ShardManager::load_shard(const std::string& category, const std::string& path) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    Shard new_shard;
    if (!parse_kn_file(path, new_shard)) {
        std::cerr << "❌ Failed to parse shard: " << path << std::endl;
        return false;
    }

    shards_[category] = std::move(new_shard);
    std::cout << "📂 Loaded shard [" << category << "] with " 
              << shards_[category].vectors.size() << " concept vectors." << std::endl;
    return true;
}

void ShardManager::unload_shard(const std::string& category) {
    std::lock_guard<std::mutex> lock(mutex_);
    shards_.erase(category);
}

std::vector<ResonanceResult> ShardManager::predict_global(const std::string& context, 
                                                       const std::vector<std::string>& candidates,
                                                       int top_n) {
    // In a global prediction, we can use the engine to calculate resonance 
    // against the combined concepts of all loaded shards.
    // For now, we delegate to the engine which calculates resonance on-the-fly.
    return engine_->predict_next(context, candidates, top_n);
}

std::vector<std::string> ShardManager::list_shards() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::string> keys;
    for (auto const& [key, _] : shards_) keys.push_back(key);
    return keys;
}

bool ShardManager::parse_kn_file(const std::string& path, Shard& out_shard) {
    // Minimal stub parser for the JSON-based .kn shards
    // In a production build, this would use nlohmann/json or simdjson.
    std::ifstream f(path);
    if (!f.is_open()) return false;

    // For this prototype, we simulate a successful parse of concept count
    // Real implementation would populate out_shard.vectors
    out_shard.metadata = {"Sovereign Source", 0.0, 5};
    
    return true;
}

} // namespace zo
