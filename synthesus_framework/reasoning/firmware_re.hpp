#pragma once
// Synthesus 2.0 Phase 7 - Firmware Reverse Engineering (ELF/CVE analysis)
#include <string>
#include <vector>
#include <unordered_map>
namespace zo {
struct CVEEntry { std::string id; std::string description; float severity{0.0f}; std::string mitigation; };
struct ELFSection { std::string name; uint64_t offset; uint64_t size; std::string type; };
struct FirmwareAnalysis {
    std::string filename;
    std::string arch; // "x86_64"|"arm"|"mips"
    std::vector<ELFSection> sections;
    std::vector<CVEEntry> vulnerabilities;
    std::vector<std::string> strings_found;
    std::string summary;
};
class FirmwareRE {
public:
    FirmwareAnalysis analyze(const std::string& binary_path) const;
    std::vector<CVEEntry> check_cve(const std::string& component, const std::string& version) const;
    void load_cve_db(const std::string& path);
    std::vector<std::string> extract_strings(const std::string& binary_path, size_t min_len = 4) const;
private:
    std::unordered_map<std::string, std::vector<CVEEntry>> cve_db_;
    std::string detect_arch(const uint8_t* header, size_t sz) const;
};
} // namespace zo
