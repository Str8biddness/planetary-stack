#pragma once
// Synthesus 2.0 Phase 7 - ZO Kernel Message Bus
// Pub/sub IPC between VCUs and reasoning modules
#include <string>
#include <functional>
#include <unordered_map>
#include <vector>
#include <mutex>
#include <any>

namespace zo {

struct Message {
    std::string topic;
    std::string payload;
    uint64_t timestamp_ms;
    int priority{0};
};

using MessageHandler = std::function<void(const Message&)>;

class MessageBus {
public:
    static MessageBus& instance();
    void subscribe(const std::string& topic, MessageHandler handler);
    void unsubscribe(const std::string& topic);
    void publish(const Message& msg);
    void publish(const std::string& topic, const std::string& payload, int priority = 0);
    size_t subscriber_count(const std::string& topic) const;

private:
    MessageBus() = default;
    mutable std::mutex mutex_;
    std::unordered_map<std::string, std::vector<MessageHandler>> subscribers_;
};

} // namespace zo
