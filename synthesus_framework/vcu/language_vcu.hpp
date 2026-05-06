#pragma once
// Synthesus 2.0 - LanguageVCU: NLP, tokenization, generation
#include "vcu_base.hpp"
#include <string>
namespace zo {
class LanguageVCU : public VCUBase {
public:
    LanguageVCU() : VCUBase("language") {}
    VCUOutput process(const VCUInput& in) override;
    std::string tokenize(const std::string& text) const;
    float sentiment(const std::string& text) const;  // -1.0 to +1.0
    std::string generate(const std::string& prompt, int max_tokens = 128) const;
private:
    float temperature_ = 0.7f;
    int max_vocab_ = 32000;
};
} // namespace zo