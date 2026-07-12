#!/usr/bin/env python3
"""
Rule-based English G2P for SI formant speech — ARPABET phonemes.

DATA + rules only. No neural G2P, no network. CMUdict-style exception
lexicon is plain text tables, not a learned model.
"""
from __future__ import annotations

import re
from typing import List

# ── Exception lexicon (common words; ARPABET space-separated) ─────────
# Subset sufficient for demos + general English; extend freely as DATA.
EXCEPTIONS: dict[str, str] = {
    "a": "AH",
    "an": "AE N",
    "the": "DH AH",
    "to": "T UW",
    "of": "AH V",
    "and": "AE N D",
    "or": "AO R",
    "for": "F AO R",
    "you": "Y UW",
    "your": "Y AO R",
    "i": "AY",
    "is": "IH Z",
    "are": "AA R",
    "was": "W AH Z",
    "were": "W ER",
    "be": "B IY",
    "been": "B IH N",
    "have": "HH AE V",
    "has": "HH AE Z",
    "had": "HH AE D",
    "do": "D UW",
    "does": "D AH Z",
    "did": "D IH D",
    "not": "N AA T",
    "no": "N OW",
    "yes": "Y EH S",
    "hello": "HH EH L OW",
    "hi": "HH AY",
    "hey": "HH EY",
    "world": "W ER L D",
    "word": "W ER D",
    "words": "W ER D Z",
    "speak": "S P IY K",
    "speech": "S P IY CH",
    "voice": "V OY S",
    "synthesus": "S IH N TH AH S AH S",
    "sovereign": "S AA V R AH N",
    "kernel": "K ER N AH L",
    "welcome": "W EH L K AH M",
    "mate": "M EY T",
    "quick": "K W IH K",
    "brown": "B R AW N",
    "fox": "F AA K S",
    "jumps": "JH AH M P S",
    "jumped": "JH AH M P T",
    "over": "OW V ER",
    "lazy": "L EY Z IY",
    "dog": "D AO G",
    "cat": "K AE T",
    "one": "W AH N",
    "two": "T UW",
    "three": "TH R IY",
    "four": "F AO R",
    "five": "F AY V",
    "six": "S IH K S",
    "seven": "S EH V AH N",
    "eight": "EY T",
    "nine": "N AY N",
    "ten": "T EH N",
    "zero": "Z IH R OW",
    "please": "P L IY Z",
    "thank": "TH AE NG K",
    "thanks": "TH AE NG K S",
    "you": "Y UW",
    "me": "M IY",
    "we": "W IY",
    "they": "DH EY",
    "them": "DH EH M",
    "this": "DH IH S",
    "that": "DH AE T",
    "these": "DH IY Z",
    "those": "DH OW Z",
    "with": "W IH DH",
    "from": "F R AH M",
    "into": "IH N T UW",
    "onto": "AA N T UW",
    "about": "AH B AW T",
    "above": "AH B AH V",
    "below": "B IH L OW",
    "under": "AH N D ER",
    "after": "AE F T ER",
    "before": "B IH F AO R",
    "because": "B IH K AO Z",
    "through": "TH R UW",
    "though": "DH OW",
    "thought": "TH AO T",
    "there": "DH EH R",
    "their": "DH EH R",
    "here": "HH IY R",
    "where": "W EH R",
    "what": "W AH T",
    "when": "W EH N",
    "who": "HH UW",
    "how": "HH AW",
    "why": "W AY",
    "which": "W IH CH",
    "could": "K UH D",
    "would": "W UH D",
    "should": "SH UH D",
    "can": "K AE N",
    "will": "W IH L",
    "shall": "SH AE L",
    "may": "M EY",
    "might": "M AY T",
    "must": "M AH S T",
    "people": "P IY P AH L",
    "little": "L IH T AH L",
    "water": "W AO T ER",
    "fire": "F AY ER",
    "earth": "ER TH",
    "air": "EH R",
    "time": "T AY M",
    "year": "Y IH R",
    "day": "D EY",
    "night": "N AY T",
    "light": "L AY T",
    "right": "R AY T",
    "left": "L EH F T",
    "good": "G UH D",
    "great": "G R EY T",
    "small": "S M AO L",
    "large": "L AA R JH",
    "open": "OW P AH N",
    "close": "K L OW S",
    "closed": "K L OW Z D",
    "system": "S IH S T AH M",
    "computer": "K AH M P Y UW T ER",
    "image": "IH M AH JH",
    "sound": "S AW N D",
    "audio": "AO D IY OW",
    "speech": "S P IY CH",
    "formant": "F AO R M AH N T",
    "synthetic": "S IH N TH EH T IH K",
    "intelligence": "IH N T EH L AH JH AH N S",
    "artificial": "AA R T AH F IH SH AH L",
    "robot": "R OW B AA T",
    "robotic": "R OW B AA T IH K",
    "human": "HH Y UW M AH N",
    "natural": "N AE CH ER AH L",
    "language": "L AE NG G W AH JH",
    "english": "IH NG G L IH SH",
    "australian": "AO S T R EY L Y AH N",
    "accent": "AE K S EH N T",
    "pitch": "P IH CH",
    "frequency": "F R IY K W AH N S IY",
    "hello": "HH EH L OW",
    "world": "W ER L D",
    "quick": "K W IH K",
    "brown": "B R AW N",
    "fox": "F AA K S",
    "the": "DH AH",
}


def _clean_word(w: str) -> str:
    return re.sub(r"[^a-z']", "", w.lower())


def _rule_g2p(word: str) -> List[str]:
    """Letter-group rules → ARPABET list. Best-effort for OOV words."""
    w = word
    out: List[str] = []
    i = 0
    # ordered multi-letter patterns
    patterns = [
        (r"^tion", ["SH", "AH", "N"]),
        (r"^sion", ["ZH", "AH", "N"]),
        (r"^ough", ["AH", "F"]),
        (r"^augh", ["AO", "F"]),
        (r"^eigh", ["EY"]),
        (r"^igh", ["AY"]),
        (r"^ing", ["IH", "NG"]),
        (r"^ang", ["AE", "NG"]),
        (r"^ong", ["AO", "NG"]),
        (r"^ung", ["AH", "NG"]),
        (r"^ch", ["CH"]),
        (r"^sh", ["SH"]),
        (r"^th", ["TH"]),
        (r"^ph", ["F"]),
        (r"^wh", ["W"]),
        (r"^ck", ["K"]),
        (r"^qu", ["K", "W"]),
        (r"^kn", ["N"]),
        (r"^wr", ["R"]),
        (r"^gn", ["N"]),
        (r"^oo", ["UW"]),
        (r"^ee", ["IY"]),
        (r"^ea", ["IY"]),
        (r"^oa", ["OW"]),
        (r"^oi", ["OY"]),
        (r"^oy", ["OY"]),
        (r"^ou", ["AW"]),
        (r"^ow", ["AW"]),
        (r"^ai", ["EY"]),
        (r"^ay", ["EY"]),
        (r"^au", ["AO"]),
        (r"^aw", ["AO"]),
        (r"^ie", ["IY"]),
        (r"^ey", ["IY"]),
        (r"^ue", ["UW"]),
        (r"^ui", ["UW"]),
        (r"^er", ["ER"]),
        (r"^ar", ["AA", "R"]),
        (r"^or", ["AO", "R"]),
        (r"^ir", ["ER"]),
        (r"^ur", ["ER"]),
        (r"^ng", ["NG"]),
        (r"^nk", ["NG", "K"]),
        (r"^ll", ["L"]),
        (r"^ss", ["S"]),
        (r"^ff", ["F"]),
        (r"^zz", ["Z"]),
        (r"^pp", ["P"]),
        (r"^tt", ["T"]),
        (r"^dd", ["D"]),
        (r"^bb", ["B"]),
        (r"^mm", ["M"]),
        (r"^nn", ["N"]),
        (r"^rr", ["R"]),
        (r"^gg", ["G"]),
        (r"^cc", ["K"]),
    ]
    singles = {
        "a": ["AE"], "e": ["EH"], "i": ["IH"], "o": ["AA"], "u": ["AH"],
        "y": ["IY"],
        "b": ["B"], "c": ["K"], "d": ["D"], "f": ["F"], "g": ["G"],
        "h": ["HH"], "j": ["JH"], "k": ["K"], "l": ["L"], "m": ["M"],
        "n": ["N"], "p": ["P"], "q": ["K"], "r": ["R"], "s": ["S"],
        "t": ["T"], "v": ["V"], "w": ["W"], "x": ["K", "S"], "z": ["Z"],
    }
    # magic-e: CVCe → long vowel
    if len(w) >= 3 and w.endswith("e") and w[-2] not in "aeiou" and w[-3] in "aeiou":
        # handle later via scan
        pass

    while i < len(w):
        rest = w[i:]
        matched = False
        # magic-e pattern at position: V C e end
        if i + 2 < len(w) and w[i] in "aeiou" and w[i + 1] not in "aeiou" and w[i + 2 :] == "e":
            long_v = {
                "a": ["EY"], "e": ["IY"], "i": ["AY"], "o": ["OW"], "u": ["UW"],
            }
            out.extend(long_v.get(w[i], ["AH"]))
            # consonant
            c = w[i + 1]
            if c == "c":
                out.append("S")
            else:
                out.extend(singles.get(c, ["AH"]))
            i = len(w)
            matched = True
            break
        for pat, phones in patterns:
            m = re.match(pat, rest)
            if m:
                out.extend(phones)
                i += m.end()
                matched = True
                break
        if matched:
            continue
        ch = rest[0]
        # soft c/g before e,i,y
        if ch == "c" and len(rest) > 1 and rest[1] in "eiy":
            out.append("S")
            i += 1
            continue
        if ch == "g" and len(rest) > 1 and rest[1] in "eiy":
            out.append("JH")
            i += 1
            continue
        # silent e at end
        if ch == "e" and i == len(w) - 1 and len(out) > 0:
            i += 1
            continue
        out.extend(singles.get(ch, ["AH"]))
        i += 1

    return out if out else ["AH"]


def word_to_phonemes(word: str) -> List[str]:
    w = _clean_word(word)
    if not w:
        return []
    if w in EXCEPTIONS:
        return EXCEPTIONS[w].split()
    # strip possessive
    if w.endswith("'s"):
        base = w[:-2]
        ph = word_to_phonemes(base)
        return ph + (["Z"] if ph and ph[-1][-1:] in "bdgvzmn" else ["S"])
    return _rule_g2p(w)


def text_to_phonemes(text: str) -> List[tuple]:
    """Return list of (word, [phones]) including silence markers between words.

    Punctuation becomes pause markers (word='.', phones=['SIL']).
    """
    text = text.strip()
    if not text:
        return []
    # split keeping sentence enders
    tokens = re.findall(r"[A-Za-z']+|[.!?]|[,;:]", text)
    result = []
    for tok in tokens:
        if tok in ".!?":
            result.append((".", ["SIL_LONG"]))
        elif tok in ",;:":
            result.append((",", ["SIL"]))
        else:
            phones = word_to_phonemes(tok)
            if phones:
                result.append((tok.lower(), phones))
    return result


def phoneme_string(text: str) -> str:
    parts = []
    for w, ph in text_to_phonemes(text):
        if w in (".", ","):
            parts.append(ph[0])
        else:
            parts.append(f"{w}:{' '.join(ph)}")
    return " | ".join(parts)


if __name__ == "__main__":
    for s in ("hello world", "the quick brown fox", "Synthesus sovereign kernel"):
        print(s, "->", phoneme_string(s))
