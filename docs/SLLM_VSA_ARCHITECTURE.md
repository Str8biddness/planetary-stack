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

### 5.12 Amplified Memory Router — governance over memory sources — `vsa_memory.py`
The §5.11 loop reused verbatim (`MetaController`), pointed at the legacy 4-module
fallback cascade (Knowledge Graph → Cloud → Personality → Context). A fixed
cascade has a failure mode: the greedy semantic source answers *almost*
anything, intercepting queries it gets WRONG before the right source is reached.
```
                     | coverage | accuracy | avg conf
  fixed cascade      |   100%   |    50%   |   0.71
  learned routing    |   100%   |   100%   |   0.89
learned: factual->kgraph, topical->cloud, personal->persona, contextual->context
```
Same coverage, accuracy recovered 50%→100% by learning per-query-type which
source to trust first — from real retrieval outcomes. Confirms the governance
loop is substrate-general: the same metacognitive layer optimizes *reasoning*
(§5.11) and *memory* (here).

### 5.13 Live AIVM integration — reasoning runs in the real kernel tick
The operators are no longer demo-only: `packages/aivm/devices/synthesus_core.py`
(`SynthesusReasoningCore`) wraps the NL front end + routers and mounts as an
NPC's `reasoning_core`. `VGD`/`VRD`/`VND` delegate to it **only when a core is
mounted** (core-less path unchanged → existing tests green). Running the
canonical 12-step `AIVMKernel.tick`:
```
Q: Who bit the man?            VGD.generate -> 'dog'                 coherence pre/post = pass/pass
Q: Is a dog an animal?         VGD.generate -> 'yes'                 pass/pass
Q: What kind of thing is a wolf? -> 'animal, canine, entity, mammal' pass/pass
Q: Who flies the airplane?     VGD.generate -> (declined)            pre=pass POST=FAIL
```
The stubbed `VGD.generate` ("Generated response…") and the `VND.coherence_check`
that did `return True` are now real: generation is grounded reasoning, and the
coherence gate **refuses to emit an ungrounded answer** (the airplane query
fails `coherence_post`). Demo: `tools/aivm_live_demo.py`.

**Groundedness tagging (imagination upgrade).** Generation and hallucination are
the same predictive act — the difference is support. So the gate is 3-way, not
binary, and every answer is tagged:
```
Who bit the man?        tag=GROUNDED     -> [verified] dog
Is a dog an animal?     tag=GROUNDED     -> [verified] yes
Who chases the wolf?    tag=IMAGINATION  -> [educated guess] ...canine level: wolf chases fox
Who flies the airplane? tag=UNGROUNDED   -> (declined, coherence_post=fail)
```
- **grounded** — verified by the symbolic operators → stated as fact.
- **imagination** — no direct support, inferred by abstraction (the smelter
  loop) → surfaced but FLAGGED as an educated guess, never as fact. This is the
  mount point for a future GPU "imagination hemisphere" (dual-process: it
  proposes, the symbolic layer verifies/tags).
- **ungrounded** — neither → declined.

The system always knows, and says, whether it is recalling or imagining.

### 5.14 Energy / Hopfield settling reasoner — the imagination organ — `vsa_hopfield.py`
Reasoning as energy minimisation: a modern Hopfield net (Ramsauer 2020) settles a
noisy/partial cue into the nearest stored attractor. The stored attractors are
the **grounded concept coordinates**, so it settles into real meaning — the
rigorous, GPU-shaped form of "settle into a stable node," and the principled
version of VSA cleanup / associative completion.
```
update: xi <- X^T softmax(beta·X xi)     energy: E = -lse(beta,X xi) + ½xi·xi
A. noisy 'dog' cue -> energy descends monotonically -> settles to 'dog' (overlap 1.00, 14 steps)
B. recovery vs noise: sigma 0.3->87%, 0.6->44%, 0.9->32%, 1.3->20%  (capacity scales with dims)
C. beta = imagination temperature: beta=1 -> blended/imaginative; beta=16 -> decisive recall
```
Role: the GPU **imagination hemisphere**. It proposes a completed pattern; the
symbolic layer verifies/tags it (high overlap → grounded, low → educated guess,
feeding §5.13). Core op is dense matmul (`X@xi`, `X^T@softmax`), batchable over
cues — CPU/NumPy here, a CuPy/torch swap parallelises it on GPU unchanged.
Honest scope: small-dim/few-pattern here limits noisy recovery; capacity grows
with dimensionality (the scale dial).

**Wired LIVE (dual-process).** `SynthesusReasoningCore` now runs both
hemispheres in the kernel tick: LEFT (symbolic VSA) grounds; if it can't, RIGHT
imagines — first by abstraction (inference), then by Hopfield settling
(association into the nearest grounded attractor). Live trace:
```
Who bit the man?                    hemisphere=symbolic    -> [verified] dog
Who chases the wolf?                hemisphere=abstraction -> [educated guess] ...canine level: wolf chases fox
tell me about the wolf and the fox  hemisphere=hopfield    -> [educated guess] settles toward 'fox'
Who flies the airplane?             hemisphere=none        -> (declined)
```
The full loop: imagination *proposes* → symbolic *verifies* → tagger *labels*
(verified / educated guess). Demo: `tools/aivm_live_demo.py`.

**Governed hemispheres (§5.11 loop applied to the hemispheres).** The three
hemispheres are organs; the `MetaController` learns per query-type which to try
first (grounded valued above imagined, structured inference above loose
association):
```
learned routing:  who/isa/what -> symbolic     open -> hopfield
Who bit the man?                    symbolic    attempts=1  [verified] dog
Who chases the wolf?                abstraction attempts=2  [educated guess] ...canine level
tell me about the wolf and the fox  hopfield    attempts=1  [educated guess] settles toward 'fox'
Who flies the airplane?             none        attempts=3  (declined)
```
Governance gives correct routing (relational → abstraction, open → association)
AND efficiency (open queries reach imagination in 1 attempt, not 3). The same
loop now governs operators (§5.11), memory (§5.12), and hemispheres (here).

### 5.16 Scaled grounding across the hemispheres — `vsa_scaled_hemispheres.py`
Scales the shared semantic substrate to the real 292k-word corpus and runs the
grounding-dependent hemispheres on 1500 concepts × 128 dims:
```
similarity:  light ~ velocity, propagation, ray   |  mass ~ energy, force, gravitation
imagination: Hopfield recovery 99.5% up to 1.2x-signal corruption (toy 13-dim collapsed)
settling:    space+time -> 'space'   mass+energy -> 'energy'   light+velocity -> 'velocity'
analogy:     space:time::length:? -> measured, rod   (force analogy noisier: single-domain)
```
Two honest results: (1) the imagination/analogy/similarity hemispheres scale to
real geometry with **zero architecture change** — they're pure functions of the
coordinate space; (2) scale **fixes the Hopfield capacity** weakness — the toy
13-dim collapse was dimensionality, not the method (note: must use norm-relative
corruption to compare fairly across dims; fixed per-component sigma grows like
√dims and falsely swamps the signal).

**Honest scope:** the STRUCTURED hemispheres (symbolic fact-store, entailment
taxonomy) need *relations* (facts, is-a edges), which raw text doesn't provide —
they scale by relation EXTRACTION (e.g. distributional inclusion for hypernyms),
a separate frontier, not by feeding more words.

### 5.17 Image-space GPU optimization — `vsa_gpu_imagespace.py`
The spatial/image-space math insight applied to reasoning: a BATCH of reasoning
states is an image (B states × d dims), and settling becomes one parallel
tensor op instead of a per-state Python loop — the GPU's native parallel-element
path (the same shape anaglyph/texture math rides).
```
  per-state loop:  for each cue:  xi <- X^T softmax(beta X xi)     (serial)
  image-space:     XI <- softmax(beta·C @ X^T) @ X  over ALL cues  (parallel)

backend=numpy(CPU)  attractors 1500x128  batch 512:
  correctness: image-space vs loop agree 100.0%
  per-state loop 8228 ms  ->  image-space 985 ms   = 8.4x  (CPU BLAS proxy)
```
Identical results, 8.4× from CPU vectorization alone; the code is
backend-agnostic, so a one-line CuPy swap runs it on GPU unchanged (adding
thousands of parallel lanes). This is the GPU-optimization path for the
imagination hemisphere — settle many cues at once. (`bind` is likewise
convolution, the most GPU-optimized op of all.)

### 5.18 Dual-process image generation — `vsa_imagine_image.py`
Wires the imagination hemisphere to the pattern-based generator
(`tools/scene_composer.py`):
- **System 1 (imagination):** a vague/noisy visual cue → Hopfield settles it into
  the nearest grounded, *renderable* concept(s), via the image-space batched fast
  path (`ModernHopfield.recall_batch`, added here).
- **System 2 (pattern-base):** `scene_composer` renders those concepts (shape
  primitives + grounded colour + scene layout).
```
cue~[apple, grass]        -> imagined [apple, grass]        -> imagined_apple_grass.png
cue~[sun, sky, cloud]     -> imagined [sun, sky, cloud]     -> imagined_sun_sky_cloud.png
cue~[mountain,grass,sky]  -> imagined [mountain,grass,sky]  -> imagined_mountain_grass_sky.png
```
60%-corrupted cues recover the right concepts, then render real images (blue-sky
gradient, green ground, grey mountain, grounded colours). The system "imagines
what to draw," then draws it; output flagged as imagination. (Also fixed a stale
absolute shard path in `scene_composer.py` so grounded colours load.) Honest
ceiling unchanged: vector illustrations, not photographs — recognisable objects
need a learned visual model.

### 5.19 Resolution-independent analytic rendering — `vsa_hd_render.py`
The "maximum world size + pi" idea, made rigorous:
- **Maximum world size** = a normalized [0,1]² reference frame; geometry is stored
  relative to it, not in pixels → the same scene rasterizes to ANY resolution.
- **pi / continuous math** = shapes are continuous functions (signed-distance
  fields, radial `(1+cos(pi·t))/2` glows, smooth gradients); edges anti-aliased
  to sub-pixel precision using pixel-size (1/res) in world units.
```
same scene -> hd_..._256.png and hd_..._1024.png : both crisp (mountain, sun glow, gradient sky)
```
**What this surpasses:** the resolution/sharpness bottleneck — crisp HD/4K at any
res, because the image is defined by equations, not a pixel grid. **What it does
NOT:** the semantic bottleneck — it makes mathematically-perfect *procedural
illustrations*, not photographs. pi buys infinite sharpness, not learned content;
a photorealistic real object still needs a learned visual model. (The deeper form
of this is harmonic/Fourier synthesis — also pi-based, resolution-free, more
terms = more detail — the rigorous version of the original "interference" idea.)

### 5.20 Coarse-to-fine pipeline: pattern document → geometric HD — `vsa_pipeline_image.py`
The CPU-only path: request → (reasoning kernel) **pattern document** (a
resolution-free scene graph of primitives + normalized dimensions + colour) →
(Hopfield imagination fills unknowns) → (geometric engine, max-world-size + pi)
→ crisp HD raster. The symbolic graph *is* the rough draft, so no intermediate
raster is needed and it renders to any resolution deterministically.

Result (`pipeline_scene.png`): a clean HD scene — gradient sky, glowing sun,
cloud, tree, red apple on grass — from text, sequentially, CPU-only.

**What the image proves (the honest line):** the engine perfected the *rendering*
(smooth, anti-aliased, HD, grounded colour, glow) — but the apple is a red
*disc* and the tree a green *circle*, because that is what the vocabulary
(`SHAPES`) maps them to. Refinement + pi + imagination sharpen the form that was
*specified*; they do not invent the apple's real form (dimple, stem, subsurface
gradient). **Content = the vocabulary in the graph.** Photoreal novel objects
need richer per-object geometry — hand-authored templates (bounded) or learned
from images (open-ended, needs visual data). The ceiling is knowledge, not
engineering.

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
| `packages/reasoning/vsa_memory.py` | Amplified Memory Router — same loop governing the 4-source memory cascade (`MemoryRouter`) |
| `packages/reasoning/vsa_hopfield.py` | Energy/Hopfield settling reasoner — GPU-shaped imagination organ (`ModernHopfield`) |
| `packages/reasoning/vsa_scaled_hemispheres.py` | grounding-dependent hemispheres on the real 292k-word corpus (1500 concepts) |
| `packages/reasoning/vsa_gpu_imagespace.py` | image-space GPU optimization of settling (backend-agnostic NumPy/CuPy) |
| `packages/reasoning/vsa_imagine_image.py` | dual-process image generation: imagination (Hopfield) → pattern-base render |
| `packages/reasoning/vsa_hd_render.py` | resolution-independent analytic rendering (normalized world + pi-based continuous shapes) |

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
./venv/bin/python packages/reasoning/vsa_memory.py   # amplified memory governance
./venv/bin/python packages/reasoning/vsa_hopfield.py # energy/Hopfield settling (imagination organ)
./venv/bin/python packages/reasoning/vsa_scaled_hemispheres.py  # hemispheres on the real corpus
./venv/bin/python packages/reasoning/vsa_gpu_imagespace.py      # image-space GPU optimization
./venv/bin/python packages/reasoning/vsa_imagine_image.py      # dual-process image generation
./venv/bin/python packages/reasoning/vsa_hd_render.py          # resolution-independent HD rendering
```
