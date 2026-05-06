#include "thread_pool.hpp"

namespace zo {

ThreadPool::ThreadPool(size_t num_threads) {
    for (size_t i = 0; i < num_threads; ++i) {
        workers_.emplace_back([this] {
            while (true) {
                std::function<void()> task;
                {
                    std::unique_lock<std::mutex> lock(queue_mutex_);
                    condition_.wait(lock, [this] {
                        return stop_.load() || !tasks_.empty();
                    });
                    if (stop_ && tasks_.empty()) return;
                    task = std::move(tasks_.front());
                    tasks_.pop();
                }
                ++active_;
                task();
                --active_;
                std::unique_lock<std::mutex> lk(done_mutex_);
                done_cv_.notify_all();
            }
        });
    }
}

ThreadPool::~ThreadPool() {
    stop_.store(true);
    condition_.notify_all();
    for (auto& w : workers_) {
        if (w.joinable()) w.join();
    }
}

size_t ThreadPool::pending() const {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    return tasks_.size();
}

void ThreadPool::wait_all() {
    std::unique_lock<std::mutex> lk(done_mutex_);
    done_cv_.wait(lk, [this] {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        return tasks_.empty() && active_ == 0;
    });
}

} // namespace zo
