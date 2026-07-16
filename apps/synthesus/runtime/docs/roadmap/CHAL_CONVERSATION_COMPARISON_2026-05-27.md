# Synthesus Legacy vs 4.1 CHAL Conversation Comparison

This harness compares the old template/fallback surface against the CHAL hemi-sync path.

| Axis | Legacy | Synthesus 4.1 CHAL |
| --- | --- | --- |
| PPBRS role | Emits user-facing template strings | Emits CHAL firmware metadata |
| Left hemisphere | Pattern/fallback text | Bounded route, confidence, constraints, checkpoint |
| Right hemisphere | Usually bypassed or bolted on | Runs narrative/generative candidate in parallel |
| Final wording | `response_template`, `[module] Handled`, `[fallback]` | Generation-spine realization plus arbitration |
| Inspection | Source label only | State handoff, signals, confidence, telemetry-shaped trace |

## Turn 1

**User:** How should CHAL treat the Knowledge Cloud compared to legacy retrieval?

**Legacy output**

> [module] Handled: knowledge_cloud. The Knowledge Cloud provides retrieval context for this query.

- source: `legacy_ppbrs_template`
- confidence: `0.74`
- template leakage risk: `high`

**CHAL output**

> CHAL should treat the Knowledge Cloud as mounted cognitive hardware, not a retrieval sidecar. That means knowledge becomes addressable substrate: partitions carry provenance, cache locality, confidence, and constraints before either hemisphere forms the final answer. Retrieval stops being a sidecar and becomes addressable cognitive hardware with provenance, locality, cache behavior, and traceable constraints.

- hemisphere: `both`
- confidence: `1.0`
- agreement: `0.22`
- left firmware route: `knowledge_hardware_mount`
- trace: `trace-c95954593c9f`
- runtime: `2.214ms`
- template leakage risk: `low`

**Observed difference**

Legacy exposes routing/fallback scaffolding as conversation. CHAL converts the route into inspectable firmware, runs a right-hemisphere candidate, and returns an arbitrated surface response.

## Turn 2

**User:** What happens when PPBRS has a pattern match but final wording needs to be natural?

**Legacy output**

> [module] Handled: ppbrs. Use the matched response_template for the user.

- source: `legacy_response_template`
- confidence: `0.69`
- template leakage risk: `high`

**CHAL output**

> A PPBRS match should act like firmware, not speech. It can identify the route, confidence, and boundaries, but the generation spine has to turn that signal into fresh bounded language so the system does not leak templates into the conversation. The match is preserved as route and confidence metadata, then realized as bounded natural language by the generation spine.

- hemisphere: `both`
- confidence: `1.0`
- agreement: `0.13`
- left firmware route: `bounded_generation_handoff`
- trace: `trace-70717e0f40a9`
- runtime: `0.603ms`
- template leakage risk: `low`

**Observed difference**

Legacy exposes routing/fallback scaffolding as conversation. CHAL converts the route into inspectable firmware, runs a right-hemisphere candidate, and returns an arbitrated surface response.

## Turn 3

**User:** Explain the difference between a demo and a platform for AIVM NPCs.

**Legacy output**

> [fallback] No route matched. I understand you're asking about this. Let me provide what I know.

- source: `legacy_fallback`
- confidence: `0.22`
- template leakage risk: `high`

**CHAL output**

> A demo proves one exchange can work. A platform proves the system can persist memory, mount knowledge, route tasks, checkpoint decisions, and improve over repeated use while keeping the output inspectable. The platform boundary is persistence, inspection, and repeatable orchestration: mounted memory, routed modules, logged decisions, and improvement without template leakage.

- hemisphere: `both`
- confidence: `1.0`
- agreement: `0.122`
- left firmware route: `platform_boundary_reasoner`
- trace: `trace-ee4fe820d913`
- runtime: `0.592ms`
- template leakage risk: `low`

**Observed difference**

Legacy exposes routing/fallback scaffolding as conversation. CHAL converts the route into inspectable firmware, runs a right-hemisphere candidate, and returns an arbitrated surface response.
