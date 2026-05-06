#pragma once
// Synthesus 2.0 Phase 7 - Watchdog (self-healing, KN checkpoint guard)
#include <string>
#include <functional>
#include <thread>
#include <atomic>
#include <mutex>
namespace zo {
struct WatchdogConfig {
    uint32_t heartbeat_ms{5000};   // Health check interval
    uint32_t checkpoint_ms{30000}; // KN DB checkpoint interval
    std::string kn_db_path{"synthesus.kndb"};
    uint32_t max_restarts{5};
};
class Watchdog {
public:
    explicit Watchdog(const WatchdogConfig& cfg = {});
    ~Watchdog();
    void start();
    void stop();
    void heartbeat(); // Called by main process to signal health
    void register_health_check(std::function<bool()> fn);
    void register_checkpoint_fn(std::function<void()> fn);
    uint32_t restart_count() const { return restarts_.load(); }
    bool is_healthy() const { return healthy_.load(); }
private:
    WatchdogConfig cfg_;
    std::atomic<bool> running_{false};
    std::atomic<bool> healthy_{true};
    std::atomic<uint32_t> restarts_{0};
    std::atomic<uint64_t> last_heartbeat_{0};
    std::thread watch_thread_;
    std::vector<std::function<bool()>> health_checks_;
    std::vector<std::function<void()>> checkpoint_fns_;
    std::mutex mutex_;
    void run_loop();
};
} // namespace zo
