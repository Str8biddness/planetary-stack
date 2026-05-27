# Synthesus 5 AIVM Agent Handover Protocol

## 🎯 Objective
To ensure every AI agent building Synthesus maintains a persistent, cumulative understanding of the system's evolution, avoids redundant work, and moves the Synthesus 5 CHAL blueprint toward implementation in every session.

The binding blueprint is `docs/roadmap/SYNTHESUS_5_CHAL_BLUEPRINT.md`. The binding progress ledger is `docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md`.

---

## 🛠️ Mandatory Start-of-Session (SOS) Workflow
Upon initialization, an agent MUST perform the following research sequence:

1.  **Read root `AGENTS.md`**: Confirm Synthesus 5 law and the required boot sequence.
2.  **Read `README.md`**: Confirm the active architecture and repository map.
3.  **Read `docs/roadmap/SYNTHESUS_5_CHAL_BLUEPRINT.md`**: Treat it as non-negotiable architecture law.
4.  **Read `docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md`**: Select the checklist item this session will advance.
5.  **Read `docs/agents/AGENTS.md`**: Understand current contracts, runtime rules, and historical constraints.
6.  **Read `AGENT_HANDOVER_PROTOCOL.md`**: (This document) To ensure compliance with the handover process.
7.  **Read the last 3 relevant entries in `AGENT_LOG.md`**: Identify exactly what was accomplished in recent sessions and where the previous agent left off.
8.  **Verify Baseline**: Run targeted validation for the files/modules you will touch. Use the full E2E suite only when the change warrants it or when the environment supports it.

---

## 📝 Mandatory End-of-Session (EOS) Workflow
Before concluding a turn or session, the agent MUST update `AGENT_LOG.md` using the following standardized template:

The agent MUST also update `docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md` in the same session.

### Standard Log Template:
```markdown
## Current Session — [YYYY-MM-DD] ([Short Project Theme])

### 📝 Summary
- [Bullet points of high-level accomplishments]
- [Rationale for any non-obvious architectural decisions]
- [Exact Synthesus 5 checklist item(s) advanced]

### ✅ Verified
- [Specific test files run and their results]
- [Manual verification steps taken (e.g., API status checks)]

### 🚧 Left Off / Next Steps
- [Actionable tasks for the next agent]
- [Unfinished work or identified bugs]
- [Next checklist item to advance]

### 💡 Architectural Notes
- [Updates to the 'Internal Model' of the system]
- [Deprecations or standard shifts implemented in this session]
```

---

## 📜 Rules for Cumulative Progression

1.  **Build, Don't Rebuild**: If a component is marked "Production Ready" in a walkthrough or log, do not refactor it for cosmetic reasons. Only modify it for documented optimizations or bug fixes.
2.  **Actionable Handoffs**: The "Left Off" section of the log is a binding contract for the next agent. Be specific (e.g., "Implement function X in file Y" rather than "Continue development").
3.  **Artifact Integrity**: When a major milestone is reached, update `walkthrough.md`. If a major change is planned, create/update `implementation_plan.md`.
4.  **Version Awareness**: Synthesus 5 supersedes V3/4.0/4.1 as the target. Use older docs only as compatibility context unless the Synthesus 5 blueprint explicitly preserves them.
5.  **Protocol Evolution**: If this protocol itself needs improvement to better serve agent-to-agent coordination, update it and log the change.
6.  **Checklist Discipline**: No session is complete until the Synthesus 5 checklist reflects what moved, what remains blocked, or what was validated.
7.  **No Drift**: Do not spend sessions on broad cleanup, cosmetic refactors, or speculative modules unless they directly advance the Synthesus 5 checklist or protect the build.

---
**Standardized by:** Synthesus 5 CHAL control plane
**Date:** 2026-05-27
