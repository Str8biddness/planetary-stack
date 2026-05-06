#include "prog_synth.hpp"
namespace zo {
void ProgSynth::add_template(const CodeTemplate& t) { templates_[t.name] = t; }
std::string ProgSynth::render(const std::string& tmpl_str,
        const std::unordered_map<std::string,std::string>& params) const {
    std::string result = tmpl_str;
    for (auto& [k, v] : params) {
        std::string placeholder = "{" + k + "}";
        size_t pos;
        while ((pos = result.find(placeholder)) != std::string::npos)
            result.replace(pos, placeholder.size(), v);
    }
    return result;
}
SynthResult ProgSynth::fill_template(const std::string& name,
        const std::unordered_map<std::string,std::string>& params) const {
    auto it = templates_.find(name);
    if (it == templates_.end())
        return {"", "", false, "Template not found: " + name};
    return {render(it->second.template_str, params), it->second.language, true, ""};
}
SynthResult ProgSynth::synthesize(const std::string& task_desc,
        const std::unordered_map<std::string,std::string>& params) const {
    // Find best matching template by task description
    for (auto& [name, tmpl] : templates_) {
        if (task_desc.find(name) != std::string::npos)
            return fill_template(name, params);
    }
    // Generate basic Python scaffold
    std::string code = "# Auto-generated scaffold for: " + task_desc + "\ndef solution():\n    pass\n";
    return {code, "python", true, ""};
}
std::vector<std::string> ProgSynth::list_templates() const {
    std::vector<std::string> keys;
    for (auto& [k, _] : templates_) keys.push_back(k);
    return keys;
}
} // namespace zo
