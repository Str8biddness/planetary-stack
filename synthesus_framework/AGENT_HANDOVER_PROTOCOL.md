# AIVM Agent Handover Protocol

## 🎯 Objective
To ensure every AI agent (Antigravity/AIVM) building Synthesus maintains a persistent, cumulative understanding of the system's evolution, avoiding redundant work and ensuring each session builds directly on the progress of the last.

---

## 🛠️ Mandatory Start-of-Session (SOS) Workflow
Upon initialization, an agent MUST perform the following research sequence:

1.  **Read `AGENTS.md`**: Understand the current mission, core architecture, and "Runtime Contracts."
2.  **Read `AGENT_HANDOVER_PROTOCOL.md`**: (This document) To ensure compliance with the handover process.
3.  **Read the last 3 entries in `AGENT_LOG.md`**: Identify exactly what was accomplished in the last session and where the previous agent left off.
4.  **Check `walkthrough.md`**: For a summary of the current "Production Ready" state.
5.  **Verify Baseline**: Run the core E2E suite (`python -m pytest tests/e2e/`) to ensure the system is stable before making changes.

---

## 📝 Mandatory End-of-Session (EOS) Workflow
Before concluding a turn or session, the agent MUST update `AGENT_LOG.md` using the following standardized template:

### Standard Log Template:
```markdown
## Current Session — [YYYY-MM-DD] ([Short Project Theme])

### 📝 Summary
- [Bullet points of high-level accomplishments]
- [Rationale for any non-obvious architectural decisions]

### ✅ Verified
- [Specific test files run and their results]
- [Manual verification steps taken (e.g., API status checks)]

### 🚧 Left Off / Next Steps
- [Actionable tasks for the next agent]
- [Unfinished work or identified bugs]

### 💡 Architectural Notes
- [Updates to the 'Internal Model' of the system]
- [Deprecations or standard shifts implemented in this session]
```

---

## 📜 Rules for Cumulative Progression

1.  **Build, Don't Rebuild**: If a component is marked "Production Ready" in a walkthrough or log, do not refactor it for cosmetic reasons. Only modify it for documented optimizations or bug fixes.
2.  **Actionable Handoffs**: The "Left Off" section of the log is a binding contract for the next agent. Be specific (e.g., "Implement function X in file Y" rather than "Continue development").
3.  **Artifact Integrity**: When a major milestone is reached, update `walkthrough.md`. If a major change is planned, create/update `implementation_plan.md`.
4.  **Version Awareness**: Always check `V3_ARCHITECTURE.md` before adding new modules to ensure they align with the 3.0 directory layout and "Shared Backbone" philosophy.
5.  **Protocol Evolution**: If this protocol itself needs improvement to better serve agent-to-agent coordination, update it and log the change.

---
**Standardized by:** Antigravity (Synthesus Core)  
**Date:** 2026-05-05
