# Synthesus 3.0 Architecture

Synthesus 3.0 = **synthetic core** + **Amplification Plane** + **ML organs**, reasoning across all domains (GM, SysOps, Chat) with one shared brain. Extra compute is used as "fuel" to think deeper and learn, not just answer faster.

## Directory Layout

- **synthetic_core/**: Core interfaces and stub implementation (WorldState, Action, SynthesusCore).
- **amplification/**: Amplification Plane entrypoints, feature views, MlOrgansHub, domain-specific amplification handlers.
- **organs/**: ML organs (PolicyPrior, RiskOutcome, Attention, Prediction, Forecast, SequencePrediction, Relation, AnomalyEvent, Summarizer) with registry and versioning.
- **domains/**: Domain-specific types and feature adapters (gm/, sysops/, chat/).
- **learning/**: Teacher/Trace logging, data builders, and training runners for organs.
- **utils/**: Shared utilities (e.g., numeric normalization).
- **scripts/**: Training session runners and tooling.

Legacy Synthesus 2.0 remains outside these directories; 3.0 modules are self-contained and can be integrated incrementally.

---

## 1. Core Idea: Synthetic Brain + Fuel

- One shared brain reasons across all domains, not separate agents.
- Extra compute = rocket fuel for deeper thinking and learning.
- Split into:
  - **Synthetic Core** (symbolic/world-model engine) — runs alone on CPU.
  - **Amplification Plane** — converts fuel into better plans, futures, and learning.
  - **ML Organs** — main learners and intuition providers.

## 2. Synthetic Core (v3): The Always-On Brain

Must always work, even with no GPU/ML/external models.

### WorldState / Action Abstractions

| Domain | WorldState | Actions |
|--------|-----------|---------|
| **GM** | Characters, locations, conflicts, history | Narrative moves, NPC actions |
| **SysOps** | Hosts, services, metrics, incidents | Runbook steps, scaling, failover, restarts |
| **Chat** | Dialogue history, user goals, topics | Ask, answer, clarify, summarize, propose plan |

### SynthesusCore Interface

```typescript
interface SynthesusCore {
  intake(input): Promise<CoreIntakeResult>;   // Update world state from new input
  plan(world): Promise<CorePlanResult>;       // Decide what to do next
  act(plan): Promise<CoreActionResult>;       // Apply the plan, produce output
}
```

Stub/naive implementation can reason without amplification — the system never depends on ML to function.

## 3. Amplification Plane: Turning Fuel into Cognition

Three main calls per turn:

1. **`amplifyIntake(ctx, input)`** — right after new input arrives.
2. **`amplifyPlanning(ctx, input)`** — while thinking/deciding.
3. **`amplifyOutput(ctx, input)`** — right before committing an action/response.

`ctx` includes: `computeBudget` (how much fuel), `domain`, session IDs, metadata.

### Feature Views (shared across domains)

| Feature | Purpose |
|---------|---------|
| **StateFeatures** | Numeric/structured summary of a world state |
| **ActionFeatures** | Summary of a (state, action) pair |
| **TrajectoryFeatures** | Summary of a state/action/outcome sequence |
| **MultiFocusFeatures** | Summary of attention targets (characters, services, topics) |

Each domain has **adapters** that produce these same shapes (`chatStateToStateFeatures`, `sysActionToActionFeatures`, etc.), so the Amplification Plane always sees uniform inputs.

### MlOrgansHub

Middleman that looks up the right organ for the current domain, tracks `computeBudget`, and provides:
- `scoreActionsWithPolicyPrior(...)` — policy scoring
- `estimateRiskWithRiskOutcome(...)` — trajectory risk
- `allocateAttentionWithAttentionOrgan(...)` — attention weights
- `detectEventsWithAnomalyEvent(...)` — anomaly flags
- `summarizeWithSummarizer(...)` — structured summaries
- `predictWithPredictionOrgan(...)` — state-level prediction scores
- `forecastTrajectory(...)` — trajectory trend forecasting
- `predictSequence(...)` — continuity/churn estimation
- `scoreRelation(...)` — trust/rapport/conflict scoring

If budget is too low or an organ is missing, returns safe fallbacks (heuristics / no-ops).

## 4. ML Organs: Specialized Learning Organs

Intelligence is learned and stored in multiple specialized models.

| Organ | Input | Output | Role |
|-------|-------|--------|------|
| **PolicyPrior** | State + candidate actions | Scores per action | Guide planning toward good actions |
| **RiskOutcome** | Trajectory features | Scalar risk/quality | Avoid bad futures, prefer good trajectories |
| **Attention** | Multi-focus features | Attention weights | Focus extra compute on important world parts |
| **Prediction** | State features | Prediction score / direction | Fast state-level forecasting |
| **Forecast** | Trajectory features | Trend / horizon forecast | Anticipate near-future shifts |
| **SequencePrediction** | State + trajectory features | Continuity / churn estimate | Preserve narrative or operational continuity |
| **Relation** | State features | Trust / rapport / conflict score | Estimate relationship health |
| **AnomalyEvent** | State diffs / metrics | Anomaly flags / event types | Detect regime changes |
| **Summarizer** | Histories, states, traces | Structured summaries | Build abstractions for reasoning |

### Organ Interface and Registry

Each organ has a `type` (OrganType), `version`, optional `domain`. Implements `predict(input, ctx)` respecting `computeBudget`. Registered in `OrganRegistry` for lookup, versioning, and rollback.

### Models Behind Organs

Each organ has a model class: `*PolicyPriorModel`, `*RiskOutcomeModel`, `*AttentionModel` per domain.

Shared/default organs are heuristic-first runtime modules with optional train hooks. They are meant to broaden the amplification surface without breaking the triad.

Each model:
- Operates on feature views
- Has `score(...)`, `train(inputs, targets, options)`, `toJSON()` / `fromJSON()`
- Organs use the model when available + budget allows, fall back to heuristic otherwise

## 5. Teacher/Trace Logging: Capturing Experience

Every amplified turn is logged as `TeacherTraceEntry` (intake/planning/output phases):
- `stateFeatures`, `actionFeatures`, `trajectoryFeatures`, `multiFocusFeatures`
- Organ outputs (PolicyPrior scores, RiskOutcome, Attention weights, Anomaly flags, Summaries)
- Final decision (chosen action, plan, response)
- Outcome signals (domain-specific quality proxies)
- Amplification info (fuel used, etc.)

All domains share the same structure so training code is generic.

## 6. Learning Loop: How Organs Get Smarter

### 6.1 Data Builders (`learning/<domain>/...Data.ts`)

| Organ | Inputs | Targets |
|-------|--------|---------|
| **PolicyPrior** | stateFeatures + actionFeatures list | chosenIndex + quality scalar |
| **RiskOutcome** | trajectoryFeatures | scalar outcome quality |
| **Attention** | multiFocusFeatures | target attention vectors |
| **Prediction** | stateFeatures | state-level score |
| **Forecast** | trajectoryFeatures | trend score |
| **SequencePrediction** | stateFeatures + trajectoryFeatures | continuity/churn score |
| **Relation** | stateFeatures | trust/rapport/conflict score |

### 6.2 Training Runners (`learning/train*.ts`)

Each runner: loads recent logs → builds inputs/targets → initializes model → trains → evaluates metrics vs baseline → if better, creates new organ version in OrganRegistry and marks it "current".

**Metrics:**
- PolicyPrior: top-1 accuracy vs chosenIndex
- RiskOutcome: MSE or correlation
- Attention: MSE/KL divergence + top-1 hit rate
- Prediction/Forecast/SequencePrediction/Relation: scalar regression or bounded-score loss against domain-specific baselines

### 6.3 Deployment Back into Organs

On startup/reload: organ asks registry for latest "current" version → loads model params if available → otherwise keeps heuristic behavior. Over time, organs get smarter from trace data without changing the core's structure.

### 6.4 Monitoring & Rollback

`learning/monitoring.ts` tracks MSE/Accuracy trends.
`organs/organConfig.ts` defines thresholds (max regression allowed before rollback).
If a new model's performance drops below `old + threshold`, the monitor signals `shouldRevert()` and the registry rolls back to the `lastGoodVersion`.

## 7. Domain Implementations

### GM (Worlds / Narrative)
- **Intake**: Summarizer builds scene summary; AnomalyEvent flags story turns
- **Planning**: PolicyPrior scores narrative moves; Attention focuses on characters/conflicts; Rollout + RiskOutcome simulate and evaluate story futures
- **Output**: RiskOutcome sanity-checks; Summarizer produces narrative text

### SysOps (Infrastructure / Incidents)
- **Intake**: Summarizer builds incident summary; AnomalyEvent detects real incidents
- **Planning**: PolicyPrior scores remediation actions; Attention focuses on services/incidents; Rollout + RiskOutcome simulate stability/risk
- **Output**: RiskOutcome checks action safety; Summarizer explains actions

### Chat (Dialog / Agents)
- **Intake**: Summarizer captures user intent/context; AnomalyEvent flags safety/topic shifts
- **Planning**: PolicyPrior scores conversational actions; Attention focuses on topics/goals; Rollout + RiskOutcome choose resolution-oriented paths
- **Output**: RiskOutcome flags bad responses; Summarizer maintains internal summary

### Shared / Default Organs
- **Prediction**: Fast state-level projection for any domain
- **Forecast**: Trajectory trend estimation for any domain
- **SequencePrediction**: Continuity/churn signal for narrative or operational flow
- **Relation**: Trust/rapport/conflict signal for social and conversational state

## 8. Full Turn Flow (Any Domain)

```
1. INTAKE
   └─ Core parses input, updates WorldState
   └─ amplifyIntake → Summarizer + AnomalyEvent organs

2. PLANNING
   └─ Core proposes candidate actions
   └─ amplifyPlanning →
       ├─ PolicyPrior scores actions
       ├─ Attention focuses rollouts/history
       ├─ RolloutAmplifier simulates futures
       └─ RiskOutcome scores trajectories
   └─ Core chooses final plan via own reasoning

3. OUTPUT
   └─ Core applies plan, prepares output
   └─ amplifyOutput →
       ├─ RiskOutcome last risk check
       └─ Summarizer clean explanation + internal note

4. LOGGING & LEARNING
   └─ TeacherTraceLogger logs entire step
   └─ Training runners consume logs, update organ models
   └─ New models promoted if they beat baselines

## 9. Self-Improvement Loop

The `selfImprove` CLI command orchestrates a continuous improvement cycle:
1. **Analyze**: Scans recent `TeacherTrace` logs from session runners.
2. **Train**: Iterates through all domains (GM, SysOps, Chat) and organs (PolicyPrior, RiskOutcome, Attention).
3. **Verify**: Checks metrics against baselines and regression thresholds.
4. **Deploy**: Automatically promotes valid models in `OrganRegistry`.
5. **Extend**: Shared/default organs can be registered in the same loop when a new generic signal family is added.

### Command Reference
- `npm run self-improve`: Run the full loop.
- `npm run train-chat-policy-prior`: Train a specific organ.
- `npm run run-training-sessions`: Generate synthetic trace data.
```
## 10. Persona and Reasoning Style

The canonical persona and reasoning transparency specification for Synthesus V3 is defined in [PERSONA.md](PERSONA.md). 

This file covers:
- Self-description and core principles.
- Internal reasoning phases (Intake, Planning, Output).
- Transparency patterns for explaining decisions to users.
- Domain-specific roles (GM, SysOps, Chat).

Developers building frontends or agent prompts should refer to that document to ensure consistent V3 behavior.

## 11. Autonomy and Guardrails

Synthesus V3 implements a dynamic autonomy system that transitions between purely advisory roles and bounded auto-execution.

### Autonomy Levels
1. **Advisor (Level 1)**: Pure reasoning and simulation. Proposes actions but never executes.
2. **Co-pilot (Level 2)**: Drafts actions (story moves, runbooks, tool calls) and requires human confirmation.
3. **Autopilot (Level 3)**: Bounded autonomy. Can execute actions automatically inside a strict sandbox.

### The Guardrails Engine (`utils/guardrails.ts`)
Gating logic uses the **Learned Triads** to decide if an action is safe for Autopilot:
- **PolicyPrior**: Confidence score must be above `minConfidenceThreshold`.
- **RiskOutcome**: Safety/Quality score must be above `maxRiskThreshold`.
- **Attention**: Targets must not be in "sensitive" world zones.
- **Allowed Tools**: Only tools in the domain's whitelist can be auto-executed.
- **Kill Switch**: A global override (`GLOBAL_KILL_SWITCH`) that immediately downgrades all domains to Level 1.

### Configuration (`organs/autonomyConfig.ts`)
Settings are configured per-domain, allowing gradual rollout (e.g., Level 2 for GM, Level 1 for Production SysOps).
