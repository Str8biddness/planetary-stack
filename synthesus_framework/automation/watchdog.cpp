#include "watchdog.hpp"
#include <chrono>
#include <iostream>
namespace zo {
Watchdog::Watchdog(const WatchdogConfig& cfg) : cfg_(cfg) {}
Watchdog::~Watchdog() { stop(); }
void Watchdog::register_health_check(std::function<bool()> fn) {
    std::lock_guard<std::mutex> lk(mutex_); health_checks_.push_back(fn);
}
void Watchdog::register_checkpoint_fn(std::function<void()> fn) {
    std::lock_guard<std::mutex> lk(mutex_); checkpoint_fns_.push_back(fn);
}
void Watchdog::heartbeat() {
    auto now = (uint64_t)std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    last_heartbeat_.store(now);
    healthy_.store(true);
}
void Watchdog::run_loop() {
    uint64_t last_checkpoint = 0;
    while (running_.load()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(cfg_.heartbeat_ms));
        if (!running_.load()) break;
        // Check health
        bool all_healthy = true;
        std::lock_guard<std::mutex> lk(mutex_);
        for (auto& fn : health_checks_) if (!fn()) { all_healthy = false; break; }
        healthy_.store(all_healthy);
        if (!all_healthy) {
            if (restarts_.load() < cfg_.max_restarts) {
                std::cerr << "[Watchdog] Unhealthy - restart #" << ++restarts_ << std::endl;
            }
        }
        // Checkpoint
        auto now = (uint64_t)std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        if (now - last_checkpoint >= cfg_.checkpoint_ms) {
            for (auto& fn : checkpoint_fns_) fn();
            last_checkpoint = now;
        }
    }
}
void Watchdog::start() {
    if (running_.load()) return;
    running_.store(true);
    watch_thread_ = std::thread(&Watchdog::run_loop, this);
}
void Watchdog::stop() {
    running_.store(false);
    if (watch_thread_.joinable()) watch_thread_.join();
}
} // namespace zo
