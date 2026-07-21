# The consciousness model, as implemented — 2026-07-21

There are currently three different statements of this model in circulation:
the artwork, a reconstruction from a chat log, and the code. Only one of them
runs. This document writes down what the code actually computes, so there is a
single canonical statement to build, sell and (if applicable) file against.

Source of truth: `apps/synthesus/runtime/packages/core/consciousness_integrator.py`
and `core/conscious_state.py`.

## The formulation

    C(t) = Φ( w_f(t)·Ψ_f(t) ,  w_m(t)·M_c(t) ,  w_n(t)·N_s(t) )

Three state components, dynamically weighted, fused into one actionable state:

| term | name | source |
|---|---|---|
| `Ψ_f(t)` | fluid state — pattern recognition, live hypotheses, novelty, uncertainty | `FluidState` |
| `M_c(t)` | crystallized state — stable traits and consolidated memory | `CrystallizedState` |
| `N_s(t)` | narrative state — identity, role, scene, goals, emotional tone, continuity summary | `NarrativeState` |
| `C(t)` | fused self-state — dominant emotion, action biases, confidence, update directives | `IntegratedConsciousnessState` |

### Weighting

Weights are not fixed. Each component contributes a salience modifier, and the
three are normalised so they always sum to 1:

    s_f = min(0.5, novelty + uncertainty + 0.2·[hypotheses present])
    s_m = 0.2 · mean(traits)
    s_n = 0.3 · arousal

    w_f = (0.4 + s_f)/Z    w_m = (0.3 + s_m)/Z    w_n = (0.3 + s_n)/Z
    Z   = (0.4 + s_f) + (0.3 + s_m) + (0.3 + s_n)

This is the "weighted model" form — it is what `integrate()` does, and it is
already implemented. A novel, uncertain situation shifts weight toward the
fluid component; a settled one lets traits and narrative dominate.

### Outputs

    dominant_emotion  = fluid push if w_f > w_n else narrative push
    action_biases     = ranked, weighted by w_f / w_n
    confidence        = 1 − uncertainty · w_f
    update_directives = what to store, and what to promote into crystallized memory

The promotion rule (`novelty > 0.7`) is the learning term: it is how fluid
experience becomes crystallized memory.

## Continuity: the term the equation does not contain

`C(t)` is computed fresh each tick. On its own it is memoryless across
restarts — which is why a character that had run for months was
indistinguishable from a fresh copy of the same genome.

Continuity is supplied separately, by the identity chain
(`characters/identity.py`):

    genesis  = H(genome archive digest ‖ character_id)
    entry_n  = H(entry_{n-1} ‖ digest(C(t)) ‖ narrative delta)
    identity = head of the chain

So the persistence term people reach for when they write `… × T` is not a
coefficient inside the fusion. It is the chain: an append-only history that
each `C(t)` is committed into. That is the honest place for it, and it is
checkable.

## What this model claims, and what it does not

**It is a specification, not a scientific result.** It defines a deterministic
procedure that turns three structured inputs into one structured output. Given
identical inputs it produces identical outputs, which is what makes it
testable and shippable.

It does **not** claim to explain, measure, or produce consciousness in the
philosophical or neuroscientific sense. No part of the codebase validates such
a claim, and nothing here should be sold as though it does. The value is that
the behaviour is *specified and reproducible*, not that the label is literal.

The component decomposition (fluid / crystallized / narrative) is a reasonable
cognitive-architecture split and is genuinely useful — it is why the character
behaves consistently and why continuity can be committed to a chain.

## Notation

The artwork's notation is stylised and not everywhere well-formed — fragments
such as `M(αchbb(N_est))` do not define an expression, and `⊕` is used as an
informal fusion operator rather than a defined algebraic one. That is fine for
artwork. It is not fine as a specification, and it should not be transcribed
into product material, documentation, or any filing.

Where a symbol is needed, use `Φ(·)` for the fusion function and state the
weighting explicitly, as above.

## Open, and blocking any "patented" wording

A repository-wide search finds **no patent number and no application number** —
only the comments `"Patent-Aligned State"` and `"patent equation"`.

- Marking a product patented without a granted patent is false patent marking
  (35 U.S.C. § 292). "Patent pending" requires an actually filed application.
- Separately, patent claims must be *definite* (35 U.S.C. § 112(b)). The
  artwork's notation would not satisfy that; the formulation in this document
  is the one that could.

Until a number and status are supplied, product material should say
**proprietary**, not patented. Nothing shipped currently uses the word.

## Status

- Implemented and running: the weighted fusion above.
- Implemented: continuity via the identity chain, rooted in the shipped genome.
- Not built: signing a chain head to bind a history to an issuer.
- No FINISH_CHECKLIST box is checked by this document.
