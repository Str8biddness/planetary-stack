// Synthesus kernel — IPC stdin/stdout protocol entry point
// Accepts either plain text lines OR JSON: {"query":"...","character_id":"...","rag_context":"..."}
// Responds with one JSON object per line:
//   {"response":"...","confidence":0.0,"module_used":"...","found":true}
#include <iostream>
#include <string>
#include <sstream>
#include <iomanip>
#include "thread_pool.hpp"
#include "message_bus.hpp"
#include "hemi_reconciler.hpp"
#include "ppbrs_router.hpp"
#include "context_memory.hpp"
#include "watchdog.hpp"

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

// Minimal extract of "query" string value from a flat JSON object line.
// Falls back to the full line when not JSON / field missing (plain-text IPC).
std::string extract_query(const std::string& line) {
    if (line.empty() || line[0] != '{') return line;
    const std::string key = "\"query\"";
    auto pos = line.find(key);
    if (pos == std::string::npos) return line;
    pos = line.find(':', pos + key.size());
    if (pos == std::string::npos) return line;
    pos = line.find('"', pos + 1);
    if (pos == std::string::npos) return line;
    ++pos;
    std::string out;
    for (size_t i = pos; i < line.size(); ++i) {
        char c = line[i];
        if (c == '\\' && i + 1 < line.size()) {
            char n = line[++i];
            if (n == 'n') out.push_back('\n');
            else if (n == 't') out.push_back('\t');
            else if (n == 'r') out.push_back('\r');
            else out.push_back(n);
            continue;
        }
        if (c == '"') break;
        out.push_back(c);
    }
    return out.empty() ? line : out;
}

// Optional rag_context for PPBRS context string
std::string extract_string_field(const std::string& line, const std::string& field) {
    if (line.empty() || line[0] != '{') return "";
    const std::string key = "\"" + field + "\"";
    auto pos = line.find(key);
    if (pos == std::string::npos) return "";
    pos = line.find(':', pos + key.size());
    if (pos == std::string::npos) return "";
    pos = line.find('"', pos + 1);
    if (pos == std::string::npos) return "";
    ++pos;
    std::string out;
    for (size_t i = pos; i < line.size(); ++i) {
        char c = line[i];
        if (c == '\\' && i + 1 < line.size()) {
            char n = line[++i];
            if (n == 'n') out.push_back('\n');
            else if (n == 't') out.push_back('\t');
            else if (n == 'r') out.push_back('\r');
            else out.push_back(n);
            continue;
        }
        if (c == '"') break;
        out.push_back(c);
    }
    return out;
}

int main(int argc, char* argv[]) {
    (void)argc;
    (void)argv;
    zo::ThreadPool pool(4);
    zo::MessageBus& bus = zo::MessageBus::instance();
    (void)bus;
    zo::PPBRSRouter router;
    zo::ContextMemory ctx("context.db");
    zo::Watchdog watchdog;
    watchdog.start();
    std::cerr << "[ZO] Synthesus kernel ready (stdin IPC)\n";
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;
        if (line == "quit" || line == "exit") break;

        std::string query = extract_query(line);
        std::string rag = extract_string_field(line, "rag_context");
        if (!rag.empty()) {
            ctx.store("context", rag);
        }
        ctx.store("last_query", query);

        auto result = router.route(query, ctx.recall("context"));
        bool found = !result.response.empty() && result.confidence > 0.0;
        std::cout << "{\"response\":\"" << json_escape(result.response)
                  << "\",\"confidence\":" << result.confidence
                  << ",\"module_used\":\"" << json_escape(result.module_used)
                  << "\",\"found\":" << (found ? "true" : "false")
                  << ",\"r\":\"" << json_escape(result.response)
                  << "\",\"c\":" << result.confidence
                  << ",\"m\":\"" << json_escape(result.module_used)
                  << "\"}" << std::endl;
    }
    watchdog.stop();
    return 0;
}
