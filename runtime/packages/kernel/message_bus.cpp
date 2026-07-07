#include "message_bus.hpp"
#include <chrono>

namespace zo {

MessageBus& MessageBus::instance() {
    static MessageBus bus;
    return bus;
}

void MessageBus::subscribe(const std::string& topic, MessageHandler handler) {
    std::lock_guard<std::mutex> lk(mutex_);
    subscribers_[topic].push_back(std::move(handler));
}

void MessageBus::unsubscribe(const std::string& topic) {
    std::lock_guard<std::mutex> lk(mutex_);
    subscribers_.erase(topic);
}

void MessageBus::publish(const Message& msg) {
    std::lock_guard<std::mutex> lk(mutex_);
    auto it = subscribers_.find(msg.topic);
    if (it != subscribers_.end())
        for (auto& h : it->second) h(msg);
}

void MessageBus::publish(const std::string& topic, const std::string& payload, int priority) {
    auto now = (uint64_t)std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    publish({topic, payload, now, priority});
}

size_t MessageBus::subscriber_count(const std::string& topic) const {
    std::lock_guard<std::mutex> lk(mutex_);
    auto it = subscribers_.find(topic);
    return it != subscribers_.end() ? it->second.size() : 0;
}

} // namespace zo
