#pragma once
// Synthesus 2.0 Phase 7 - MEMO VCU: 4-tier memory orchestration
#include "vcu_base.hpp"
#include "../memory/working_memory.hpp"
#include "../memory/episodic_memory.hpp"
#include "../memory/long_term_memory.hpp"
#include "../memory/kn_database.hpp"
namespace zo {
class MemoVCU : public VCUBase {
public:
    std::string id() const override { return "MEMO"; }
    VCUOutput process(const VCUInput& input) override;
    bool can_handle(const VCUInput& input) const override;
    WorkingMemory& working() { return wm_; }
    EpisodicMemory& episodic() { return em_; }
    LongTermMemory& longterm() { return ltm_; }
    KNDatabase& kn() { return kn_; }
private:
    WorkingMemory wm_;
    EpisodicMemory em_;
    LongTermMemory ltm_{"synthesus.kndb"};
    KNDatabase kn_;
};
} // namespace zo
