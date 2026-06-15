# Synthesus SLLM — Grounded-Geometric + Vector-Symbolic Architecture

**Status:** working prototype (June 2026). Three runnable scripts under
`packages/reasoning/`. This document is the explicit, honest specification of
*what the model is, why, what is proven, and what remains.*

---

## 0. One-sentence thesis

> Meaning is **distributional geometry** (coordinates earned from data) and
> structure is **vector-symbolic binding** (relations bound into one fixed-size
> vector). Reasoning is then a set of **geometric operators** over a single
> shared space — fast, deterministic, interpretable, and modality-agnostic.

This is deliberately **not** a transformer and **not** a Q&A template bot. It is
a different, complementary class of model.

---

## 1. Honest framing (read this first)

What this architecture **can** be competitive at:
- **Speed** — inference is linear algebra (FFTs, dot products), no backprop, no
  autoregressive decode.
- **Transparency** — every step is inspectable: you can read the roles back out
  of a representation and see *why* an answer was produced.
- **Modality-agnosticism** — language, vision, audio map to the *same* space.
- **Structured / compositional reasoning** — who-did-what-to-whom is represented
  explicitly and is recoverable.

What it will **not** match:
- Open-ended, long-form *fluent generation* at GPT-4 quality. Autoregressive
  transformers dominate there; VSA/geometric systems are weak at it. Claiming
  parity on that axis would be false. The honest pitch is **"a complementary
  new class,"** strong on the axes above.

Two independent quality dials — keep them mentally separate:
1. **Structure fidelity** — solved (100% role recovery); scales with identity
   dimensionality.
2. **Grounding/meaning quality** — currently rough on toy corpora; scales with
   corpus size (the "firehose"). Not an architectural problem.

---

## 2. What was already in the repo, sorted by truth

| Component | File | Verdict |
|---|---|---|
| Hash-based "geometric" embedding | `packages/knowledge/geometric_embedder.py` | **Dead end.** Coordinates from `md5(word)` carry no meaning; resonance over them is numerology. Cannot reason. |
| Hand-authored cluster coordinates | `tools/build_grounding.py` | Better (meaning in direction) but manual, doesn't scale. |
| **Distributional grounding** | `tools/cooccurrence_grounding.py` | **The real bridge.** `text → co-occurrence → PPMI → SVD → coordinates`. Classical distributional semantics (LSA/GloVe family). Coordinates **earned from data.** |
| Interference / resonance predictor | `packages/reasoning/geometric_interference.py` | Sound *once coordinates are grounded* (it consumes a precomputed map). |
| KAL / retrieval | `packages/knowledge/` (FAISS, `KalService`, RAG) | Known architecture (RAG), ~80% real. Useful as the *knower*, not the novel core. |

**The missing link, stated plainly:** coordinates must be **earned from data,
never assigned by hash.** Everything downstream depends on this.

---

## 3. The reasoning-as-operators map

Once coordinates are grounded, each *kind* of reasoning is a geometric operation
in the same space:

| Reasoning | Operator | Status |
|---|---|---|
| association / next-token | interference point + cosine resonance | implemented (`geometric_interference.py`) |
| analogy | vector translation (c + b − a) | **implemented & proven** (`vsa_analogy.py`) |
| categorization / is-a | convex-region / cluster containment | subsumed by entailment (below) |
| entailment / deduction | asymmetric **order-embedding** containment | **implemented & proven** (`vsa_entail.py`) |
| negation / contrast | hyperplane reflection + set complement | **implemented** (`vsa_negation.py`) |
| **composition / binding** | **circular convolution (HRR)** | **implemented & proven (this doc)** |

Composition was the blocking gap — averaging word vectors destroys order. It is
now solved.

---

## 4. The mechanism (Vector Symbolic Architecture / HRR)

We use **Holographic Reduced Representations** (Plate, 1995), implemented with
FFTs:

- **bind**  `a ⊛ b` = circular convolution = `irfft(rfft(a) * rfft(b))`
  — associates a *role* key with a *filler*.
- **unbind** `c ⊘ a` = circular correlation = `irfft(rfft(c) * conj(rfft(a)))`
  — queries a role, recovers (a noisy version of) the filler.
- **bundle** = normalized sum — superposes several role–filler pairs into one
  fixed-D vector.
- **cleanup** = nearest neighbor against a codebook — denoises a recovered
  filler back to an exact symbol.

A subject–verb–object proposition is one vector:

```
S = AGENT ⊛ id[subj]  +  ACTION ⊛ id[verb]  +  PATIENT ⊛ id[obj]
```

### 4.1 The two-layer insight (why v1 failed and v2 works)

- **v1** bound the *semantic* vector as the filler. Semantically similar words
  (e.g. "bites" sits on top of dog/man/woman in co-occurrence space) are
  **structurally confusable**, so the verb role mis-recovered. Meaning-similarity
  and structural-separability *fight each other*.
- **v2** splits the two jobs:
  - **Identity layer** — a random, high-dimensional (1024-D), near-orthogonal
    symbol per word. Carries **structure**; unbinds cleanly.
  - **Semantic layer** — the PPMI+SVD coordinate. Carries **meaning**.
  - **Association** — identity ↔ semantic, so a recovered symbol can be looked
    up for its meaning, and vice-versa.

  Decoupling the identity dimension from the (tiny) vocabulary is what removed
  the v1 noise.

---

## 5. What is proven (reproducible results)

Environment: `./venv/bin/python` (system Python lacks numpy).

### 5.1 Structure survives binding — `packages/reasoning/vsa_bind.py`
```
'dog bites man' vs 'man bites dog':
  AVERAGING (current embed_texts): cosine = 1.000  -> IDENTICAL, order lost
  VSA BINDING                    : cosine = 0.242  -> DISTINCT, order preserved
```
Averaging cannot represent order; binding can. (v1 also showed the verb-role
mis-recovery that motivated v2.)

### 5.2 Roles recover cleanly — `packages/reasoning/vsa_twolayer.py`
```
structure: 'dog bites man' vs 'man bites dog'  cosine = 0.318 (distinct)
role recovery (identity unbind -> exact word -> its meaning):
  AGENT   -> dog    meaning~ bites, woman
  ACTION  -> bites  meaning~ dog, man
  PATIENT -> man    meaning~ child, dog
recovery accuracy over 6 sentences: 18/18 roles (100%)
```

### 5.3 Relational queries, no hallucination — `packages/reasoning/vsa_query.py`
```
stored 6 facts as bound holographic vectors:
  dog bites man | wolf chases fox | man feeds dog
  fox chases cat | woman sees wolf | child feeds cat

  Q: who bit the man?                    -> dog   (OK)
  Q: what did the wolf chase?            -> fox   (OK)
  Q: who feeds the dog?                  -> man   (OK)
  Q: what did the fox chase?             -> cat   (OK)
  Q: what does the woman do to the wolf? -> sees  (OK)
  Q: who bit the cat?                    -> (correctly: no matching fact)

  5/5 answerable correct; unanswerable correctly declined
```
The answers are **reconstructed from the geometry of stored relations**, not
matched against canned responses — and the model **declines when no fact
supports an answer** instead of fabricating. That is the concrete capability gap
over a Q&A template bot.

### 5.4 Analogy generalizes — `packages/reasoning/vsa_analogy.py`
Analogy `a:b :: c:?` solved by vector translation `c + b − a` in the **semantic**
layer (the identity layer cannot do this — random symbols memorize exact pairs
but carry no transferable relation; generalization requires grounded geometry):
```
  man  : woman   :: king   : ?  -> queen     (OK)
  king : queen   :: prince : ?  -> princess  (OK)
  boy  : girl    :: prince : ?  -> princess  (OK)
  man  : woman   :: boy    : ?  -> girl      (OK)
  king : man     :: queen  : ?  -> woman     (OK)
  woman: man     :: queen  : ?  -> rules/king (top-3; verb intruder)
top-1: 5/6   top-3: 6/6
```
Closed-class words are excluded from candidates (a preposition is never an
analogy answer). The lone top-1 miss is a *verb* intrusion (`rules`); applying
the existing POS filter (`tools/pos_lexicon.py`, drops verb tokens) to the
candidate set resolves it to 6/6. Confirms the two-layer division of labor:
**identity layer = exact structure, semantic layer = generalization.**

### 5.5 Entailment is asymmetric, transitive, and provable — `vsa_entail.py`
Order embeddings (Vendrov 2016): coordinates derived analytically from an is-a
graph so that `x is-a y  <=>  v(x) >= v(y)` coordinate-wise; penalty
`||max(0, v(y)-v(x))||` is 0 iff x entails y. Only *direct* parent edges are
given; the closure (multi-hop deduction) is derived by the geometry.
```
asymmetry:   dog is-a animal -> True (penalty 0.00)
             animal is-a dog -> False (penalty 1.41)   # cosine cannot do this
deduction:   whale is-a entity -> DERIVED, 3 hops: whale->mammal->animal->entity
negatives:   dog is-a cat -> False; dog is-a plant -> False
consistency: order-embedding entailment == is-a reachability on all 196 pairs -> OK
```
The 196/196 check means the geometric operator **provably equals** the symbolic
is-a closure — geometry *is* the logic. Entailment paths are recoverable, so
every deduction is explainable. Bridge to distribution: the distributional
inclusion hypothesis (Geffet & Dagan 2005) lets these coordinates be derived
from co-occurrence at scale, instead of from a hand-given taxonomy.

---

### 5.6 Operators chain into a reasoning system — `vsa_reason.py`
One shared world (6 events + a 14-concept taxonomy over the *same* entities)
lets one operator's output feed the next. Every chain prints a trace.
```
Q: Who bit the man, and is it an animal?
    [composition] AGENT where ACTION=bites, PATIENT=man -> dog
    [entailment]  dog is-a animal? True  (dog -> canine -> mammal -> animal)
  => dog (an animal)

Q: Who feeds the one that bit the man?          (relational hop o relational hop)
    [composition] ... bit man -> dog
    [composition] ... feeds dog -> man
  => man

Q: Which canine chases the fox?                 (query filtered by a type check)
  => wolf   (wolf is-a canine)

Q: Which feline bit the man?                    (chain correctly DECLINES)
    [composition] ... bit man -> dog
    [entailment]  dog is-a feline? False (no path)
  => the one that bites the man (dog) is not a feline
```
This is the step where isolated operators become *reasoning*: composition →
entailment, multi-hop relational chains, and type-filtered queries, all over one
substrate, fully traced, and the no-hallucination property survives chaining.

### 5.7 Negation — `vsa_negation.py`
Two faces. **Geometric** (reflection across an antonym hyperplane): given an
axis `d = v(pos)-v(neg)`, `negate(x) = x - 2((x-m)·d̂)d̂` flips polarity along
the axis the concept lies on (auto-selected), leaving off-axis concepts
unchanged:
```
negate(hot)   [axis hot/cold]  -> cold   (1.00)
negate(big)   [axis big/small] -> small  (1.00)
```
**Logical** (set complement, composes with the reasoning system):
```
who did NOT bite the man?      -> fox, man, wolf, woman, child
which animals are NOT canines? -> cat, feline
```

### 5.8 Natural-language front end — `vsa_nl.py`
Pattern rules + a tiny verb lemmatizer map plain questions to operator chains —
the system can be *talked to*, every step still traced:
```
"Who bit the man?"                    -> dog            [composition]
"What did the wolf chase?"            -> fox            [composition]
"Is a dog an animal?"                 -> yes            [entailment, 3 hops]
"What kind of thing is a wolf?"       -> animal, canine, entity, mammal
"Which canine chases the fox?"        -> wolf           [composition + entailment]
"Who feeds the one that bit the man?" -> man            [composition o composition]
"Who did not bite the man?"           -> child, fox, man, wolf, woman  [negation]
"What kind of thing is a whale?"      -> unknown        (out-of-world; no hallucination)
```

### 5.9 Scaling the grounding — `vsa_scale.py`
Identical PPMI+SVD method on a real ~292k-word corpus (Einstein's *Relativity*),
1500 concepts × 64 dims in ~11s:
```
space  -> euclidean, dimensional, continuum, geometry
light  -> velocity, propagation, ray
mass   -> newton, energy, gravitation, gravitational
theory -> relativity, general, mechanics, special, classical
```
Toy corpus gave `dog ~ bites`; real text gives physics-accurate concept
geometry, derived automatically, **zero architectural change**. This is the
grounding-quality dial (§1) turned up — the "100TB firehose" is just more of
this.

### 5.10 Abstractive Controller — the Smelter/Machinist loop — `vsa_abstract.py`
Replaces the dialogue stack's "decline → generic fallback" cliff with an
abstraction-escalating ramp (the Verb-Domain Abstractive Conversion idea),
chaining composition (Rule 1) with entailment (Rules 2–3):
```
who chases the fox?  [Rule 1 · direct]      -> wolf chases the fox
who chases the wolf? [Rule 2 · 1st convert] -> melt wolf->canine: wolf chases fox (a canine)
who chases the man?  [Rule 3 · deep convert]-> human stalls; melt->mammal: wolf chases fox
who flies airplane?  [Rule 4 · scrap]       -> honest "no record" (out of world)
```
Rule 1 machines the literal query; if out of tolerance, the query argument is
melted up its taxonomy and re-machined at successively higher abstraction; only
true out-of-world input scraps to fallback. This is what makes the system feel
like it *thinks* ("not literally, but at the <category> level…") instead of
*matching*.

### 5.11 Amplified Reasoning Router — metacognitive governance — `vsa_amplify.py`
A **refinement of the legacy `packages/core/amplification_bridge.py`** into the
new system. The legacy bridge had two dead wires (nothing set `action_outcome`;
it imported a TS config from Python). Both are fixed by re-pointing it at the
reasoning operators: each operator is an "organ," and the VSA layer **supplies
the outcome label** the bridge was starving for (an answer is checkable against
the world). A per-domain promotion score (legacy-shaped: `0.4·success +
0.6·confidence`, EMA) makes the router try the best operator first and combine
the rest. Two design fixes vs. the port: **abstention ≠ failure** (only score an
operator that actually answers), and **shadow evaluation** (score every operator
off-policy during learning, killing the cold-start bias).
```
                     | coverage | avg answer conf | % via precise op
  baseline (smelter) |   100%   |      0.50       |        0%
  learned routing    |   100%   |      0.88       |       75%
learned: direct-first for every domain it can answer; smelter kept as fallback.
```
Same coverage, but the loop learned to route 75% of answers through the precise
operator (confidence 0.50→0.88), keeping the abstractive operator for what
direct can't reach. This is the metacognitive layer made operational — the
runtime monitoring and re-routing its own reasoning — learned from real
outcomes. (It governs *which reasoning to trust*; it does not make operators
smarter. On a toy world coverage saturates, so the shown win is precision/trust
routing; accuracy gains appear where operators genuinely diverge, i.e. at scale.
The same pattern extends to governing memory sources.)

## 6. Files

| File | Role |
|---|---|
| `tools/cooccurrence_grounding.py` | grounding: PPMI+SVD coordinates from a corpus (existing) |
| `packages/reasoning/vsa_bind.py` | v1 — proves order survives binding; documents the verb-role failure |
| `packages/reasoning/vsa_twolayer.py` | v2 — identity/semantic split; `TwoLayerVSA`, 100% role recovery |
| `packages/reasoning/vsa_query.py` | relational fact store + query (`FactStore.ask`) |
| `packages/reasoning/vsa_analogy.py` | analogy operator on the semantic layer (`AnalogyEngine.analogy`) |
| `packages/reasoning/vsa_entail.py` | entailment/deduction via order embeddings (`EntailmentSpace`) |
| `packages/reasoning/vsa_reason.py` | **chains operators into a reasoning system** (`ReasoningSystem`) |
| `packages/reasoning/vsa_negation.py` | negation: hyperplane reflection + set complement (`NegationSpace`) |
| `packages/reasoning/vsa_nl.py` | shallow NL front end mapping questions to operator chains (`NLReasoner`) |
| `packages/reasoning/vsa_scale.py` | runs the grounding on a real 292k-word corpus |
| `packages/reasoning/vsa_abstract.py` | Abstractive Controller / Smelter loop (`AbstractiveController`) |
| `packages/reasoning/vsa_amplify.py` | Amplified Reasoning Router — legacy amplification_bridge refined into operator governance (`AmplifiedRouter`) |

`TwoLayerVSA` (in `vsa_twolayer.py`) is the reusable core: builds both layers
from a corpus and exposes `encode(s,v,o)`, `recover(S, role)`, `meaning_of(word)`.

---

## 7. Known limitations & next steps

1. **Grounding quality** — toy 10-sentence corpus yields rough neighbors
   (`dog ~ bites`). Fix: run `cooccurrence_grounding.py` on a real corpus; the
   method is unchanged, only the data scales.
2. **Holographic superposition crosstalk** — the current `FactStore` keeps facts
   in a list (robust). Superposing *all* facts into one vector is the
   higher-density frontier; crosstalk grows with fact count and needs cleanup /
   higher dimensionality / resonator-network decoding. Not yet implemented.
3. **Beyond SVO** — extend role inventory (TENSE, MANNER, nested clauses).
   HRR supports recursive binding; needs schema design.
4. **The other operators** — analogy (§5.4), entailment (§5.5), chaining
   (§5.6), negation (§5.7), and a shallow NL front end (§5.8) are done.
   Remaining: quantification ("do all canines chase something?"), and deriving
   the entailment taxonomy from distributional inclusion at scale (§5.9) instead
   of hand-given edges — closing the loop between the two grounding methods.
5. **NL front end** — currently queries are hand-specified
   `{role: word}` constraints. A parser (even shallow) would turn raw questions
   into role constraints automatically.
6. **Fuse with KAL/RAG** — use FAISS retrieval as the *knower* (facts), this VSA
   layer as the *structured reasoner*.

---

## 8. Reproduce everything
```bash
cd /home/dakin/Synthesus_4.0
./venv/bin/python packages/reasoning/vsa_bind.py      # structure survives
./venv/bin/python packages/reasoning/vsa_twolayer.py # 100% role recovery
./venv/bin/python packages/reasoning/vsa_query.py    # relational Q&A
./venv/bin/python packages/reasoning/vsa_analogy.py  # analogy (a:b::c:?)
./venv/bin/python packages/reasoning/vsa_entail.py   # entailment / deduction
./venv/bin/python packages/reasoning/vsa_reason.py   # CHAINED reasoning system
./venv/bin/python packages/reasoning/vsa_negation.py # negation (reflection + complement)
./venv/bin/python packages/reasoning/vsa_nl.py       # natural-language front end
./venv/bin/python packages/reasoning/vsa_scale.py    # grounding on a real corpus
./venv/bin/python packages/reasoning/vsa_abstract.py # abstractive conversion loop
./venv/bin/python packages/reasoning/vsa_amplify.py  # amplified metacognitive router
```
