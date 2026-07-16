# Synthesus 5 Agent Law

This repository is now governed by the Synthesus 5 CHAL blueprint.

Before any agent changes code, docs, prompts, automations, tests, or repository structure, it must read:

1. `README.md`
2. `docs/roadmap/SYNTHESUS_5_CHAL_BLUEPRINT.md`
3. `docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md`
4. `docs/agents/AGENTS.md`
5. `docs/agents/AGENT_HANDOVER_PROTOCOL.md`
6. the last three relevant entries in `docs/agents/AGENT_LOG.md`

Every development session must accomplish at least one concrete Synthesus 5 item:

- implement a checklist component
- delete or quarantine a legacy/template path
- create a missing test, harness, trace, interface, or module
- improve a benchmark or validation surface
- document and isolate a real blocker with exact files and next action

If a task does not connect to the Synthesus 5 blueprint, stop and re-scope it unless it is required for safety, correctness, build health, or git hygiene.

Hard constraints:

- CHAL is the architectural substrate.
- Cognitive Hypervisor is the scheduler/control layer.
- Quad Brain is the default topology.
- CGPU owns rendering/simulation, not truth.
- Knowledge Cloud is mounted hardware.
- PPBRS emits firmware signals, not normal-path final language.
- Normal user-facing template fallback output is a defect outside safety/platform/explicit NPC-script exceptions.
- Update `docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md` and `docs/agents/AGENT_LOG.md` before ending the session.
