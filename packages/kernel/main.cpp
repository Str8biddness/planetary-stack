// Synthesus 2.0 - main.cpp - IPC stdin/stdout protocol entry point
// Build: bash build.sh --rebuild
// Manual: g++ -std=c++17 -O3 -march=native -o zo_kernel main.cpp \
//   kernel/*.cpp memory/*.cpp reasoning/*.cpp vcu/*.cpp \
//   core/*.cpp automation/*.cpp onnx_bridge/*.cpp \
//   vendor/sqlite3.c -lpthread
#include <iostream>
#include <string>
#include <sstream>
#include <iomanip>
#include "kernel/thread_pool.hpp"
#include "kernel/message_bus.hpp"
#include "core/hemi_reconciler.hpp"
#include "core/ppbrs_router.hpp"
#include "core/context_memory.hpp"
#include "automation/watchdog.hpp"

std::string json_escape(const std::string& s) {
    std::ostringstream o;
    for (auto c : s) {
        if (c == '"') o << "\\\"";
        else if (c == '\\') o << "\\\\";
        else if (c == '\b') o << "\\b";
        else if (c == '\f') o << "\\f";
        else if (c == '\n') o << "\\n";
        else if (c == '\r') o << "\\r";
        else if (c == '\t') o << "\\t";
        else if ('\x00' <= c && c <= '\x1f') {
            o << "\\u" << std::hex << std::setw(4) << std::setfill('0') << (int)c;
        } else o << c;
    }
    return o.str();
}
int main(int argc, char* argv[]) {
    zo::ThreadPool pool(4);
    zo::MessageBus& bus = zo::MessageBus::instance();
    zo::PPBRSRouter router;
    zo::ContextMemory ctx("context.db");
    zo::Watchdog watchdog;
    watchdog.start();
    std::cerr << "[ZO] Synthesus 2.0 kernel ready (stdin IPC)\n";
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;
        if (line == "quit" || line == "exit") break;
        ctx.store("last_query", line);
        auto result = router.route(line, ctx.recall("context"));
        std::cout << "{\"response\":\"" << json_escape(result.response)
                  << "\",\"confidence\":" << result.confidence
                  << ",\"module_used\":\"" << json_escape(result.module_used)
                  << "\"}" << std::endl;
    }
    watchdog.stop();
    return 0;
}