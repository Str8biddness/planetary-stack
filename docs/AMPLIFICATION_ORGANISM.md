# Amplification Organisms — Synthesus's Ability Dependencies

**Core principle (enforced, not just stated):**
Every Synthesus ability **depends on** an *amplification organism*. Without the
organism, the ability does not exist. Synthesus **cannot** converse, predict the
next word, etc. unless the corresponding organism is **registered, trained, and
measured-passing**. Capability is gated by *proof*, never by claim.

```
Synthesus
  ability "predict_next"  ──requires──▶  NextWordOrganism      { organs: transition, context }
  ability "converse"      ──requires──▶  ConversationOrganism  { organs: intent, ... }
  ability "<new>"         ──requires──▶  <new organism>        { its co-trained organ group }
```

## What an organism is
An **amplification organism** = a group of **co-trained organ *dependencies*** +
a governing amplification loop, existing to uplift exactly one ability:
- **organs are dependencies** of the organism (e.g. next-word needs a *transition*
  organ Ψf and a *context/meaning* organ Mc/Ns), co-trained so they stay coherent
  (you can't swap one in isolation — they play off each other through the kernel),
- the organism **earns its ability by measurement** — it exposes the ability only
  after passing its bar,
- **new ability = new organism**, plugged in as a module; existing organisms stay
  coherent. This is what lets the model scale without re-deriving everything.

## Enforced dependency (proven in code)
`packages/reasoning/amplification_organism.py` hard-gates it:
```
no organism registered   → can('predict_next')=False  → do() raises CapabilityUnavailable
organism untrained       → can=False                  → do() BLOCKED ("not ready")
organism trained+measured→ can=True                   → do(['the','river']) → 'runs'
   organs (dependencies) = [transition, context]   measured next-word top-1 = 72.1% (toy corpus)
```
The 72.1% is on a small repetitive corpus (exercises the framework fast) — it
demonstrates the machinery, not a real-world benchmark; each organism earns its
*real* number on real data.

## Why this matters
- **Dependency is explicit and enforced:** Synthesus's abilities literally cannot
  run without their organisms — no silent degradation, no faking.
- **Proof-gated capability:** an ability appears only when its organism measures
  up. The name "amplification organism" is earned per ability, by measurement.
- **Scales by composition:** add an ability → train one organism → register it.
  No 25-hour re-derivation; the organism is a self-contained module.

## Files
- `packages/reasoning/amplification_organism.py` — framework (`Organ`,
  `AmplificationOrganism`, `Synthesus` registry with hard dependency gating) +
  `NextWordOrganism` (ability #1) + measurement harness.
