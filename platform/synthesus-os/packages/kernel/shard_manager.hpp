#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <memory>
#include <mutex>
#include "geometric_engine.hpp"

namespace zo {

struct ShardMetadata {
    std::string source;
    double timestamp;
    int dimensions;
};

/**
 * ShardManager - Handles loading and querying of categorical .kn shards.
 * Bridges the filesystem to the GeometricEngine.
 */
class ShardManager {
public:
    ShardManager(std::shared_ptr<GeometricEngine> engine);

    // Loads a .kn shard from disk into memory
    bool load_shard(const std::string& category, const std::string& path);

    // Unloads a shard
    void unload_shard(const std::string& category);

    // Performs resonance prediction across all loaded shards
    std::vector<ResonanceResult> predict_global(const std::string& context, 
                                               const std::vector<std::string>& candidates,
                                               int top_n = 5);

    // Lists currently loaded categories
    std::vector<std::string> list_shards() const;

private:
    std::shared_ptr<GeometricEngine> engine_;
    
    struct Shard {
        ShardMetadata metadata;
        std::unordered_map<std::string, GeometricVector> vectors;
    };

    std::unordered_map<std::string, Shard> shards_;
    mutable std::mutex mutex_;

    // Helper to parse JSON (simulated - would use nlohmann/json in full impl)
    bool parse_kn_file(const std::string& path, Shard& out_shard);
};

} // namespace zo
