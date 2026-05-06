#pragma once
// Synthesus 2.0 Phase 7 - Program Synthesis (template-based code generation)
#include <string>
#include <vector>
#include <unordered_map>
namespace zo {
struct CodeTemplate {
    std::string name;
    std::string language; // "python"|"cpp"|"bash"
    std::string template_str; // {param_name} placeholders
    std::vector<std::string> params;
};
struct SynthResult { std::string code; std::string language; bool success; std::string error; };
class ProgSynth {
public:
    void add_template(const CodeTemplate& t);
    SynthResult synthesize(const std::string& task_desc,
                           const std::unordered_map<std::string,std::string>& params = {}) const;
    SynthResult fill_template(const std::string& tmpl_name,
                              const std::unordered_map<std::string,std::string>& params) const;
    std::vector<std::string> list_templates() const;
private:
    std::unordered_map<std::string, CodeTemplate> templates_;
    std::string render(const std::string& tmpl_str,
                       const std::unordered_map<std::string,std::string>& params) const;
};
} // namespace zo
