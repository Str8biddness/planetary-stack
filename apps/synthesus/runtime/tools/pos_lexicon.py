#!/usr/bin/env python3
"""
POS Lexicon — derive noun-vs-verb tags from the corpus (no tagger, no neural net).

Distributional part-of-speech: a word that frequently follows a DETERMINER
(the/a/this ...) is noun-like; one that follows "to" or a subject pronoun
(I/we/they ...) is verb-like. Used to filter PPBRS concept families so the
realizer stops listing verbs ("Energy is tied to mass, expression, and
*requires*") — keep the nouns, drop the verbs.
"""
import sys, os, json
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricRefinery

SHARD_DIR = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")
CORPUS = "data/corpus/real_corpus.txt"

DET = set("the a an this that these those its his her their our your my no each every some any one".split())
VERB_CUE = set("to i we they you he she it who".split())   # word after these tends to be a verb


# suffixes that reliably mark nouns — never tag these as verbs (avoids dropping
# "descent", "variation", "density" just because they appeared after "to" once).
NOUN_SUFFIX = ("tion", "sion", "ment", "ness", "ity", "ance", "ence", "ship",
               "ism", "ology", "ure", "scent", "sity", "graph")


def build(tokens):
    noun, verb = {}, {}
    for prev, w in zip(tokens, tokens[1:]):
        if prev in DET:
            noun[w] = noun.get(w, 0) + 1
        elif prev in VERB_CUE:
            verb[w] = verb.get(w, 0) + (2 if prev == "to" else 1)
    nouns = {w for w in set(noun) | set(verb)
             if noun.get(w, 0) >= 1 and noun.get(w, 0) >= verb.get(w, 0)}
    # Conservative: strong verb signal, no noun evidence, not a noun-suffix word.
    verbs = {w for w in set(verb)
             if verb.get(w, 0) >= 2 and noun.get(w, 0) == 0
             and not w.endswith(NOUN_SUFFIX)}
    return nouns, verbs


if __name__ == "__main__":
    r = GeometricRefinery()
    toks = r.clean_and_tokenize(open(CORPUS, encoding="utf-8").read())
    nouns, verbs = build(toks)
    print(f"corpus {len(toks)} tokens -> {len(nouns)} noun-like, {len(verbs)} verb-like")

    probe = ["mass", "energy", "motion", "species", "requires", "satisfy",
             "believe", "moving", "varieties", "descent", "velocity"]
    print("probe:", {w: ("noun" if w in nouns else "verb" if w in verbs else "?") for w in probe})

    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    json.dump({"nouns": sorted(nouns), "verbs": sorted(verbs)},
              open(SHARD_DIR / "pos_lexicon.kn", "w"))
    print(f"💾 saved {SHARD_DIR/'pos_lexicon.kn'}")
