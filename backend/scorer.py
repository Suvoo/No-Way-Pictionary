"""Guess checking. Pure functions, no state, no I/O. The backend referee uses these;
the PAL never scores itself.

Rules (v1, rule-based):
  - case-insensitive, punctuation stripped
  - a guess is correct if the secret word or one of its variants appears as a whole
    word/phrase, with an optional plural "s"/"es"
  - user speech counts as a guess only if it is short (<= MAX_GUESS_WORDS after fillers
    are stripped) or it contains the secret word; longer chatter is logged, not counted
  - PAL speech is scanned for guess patterns ("is it a X?") as a fallback to the
    submit_guess tool (speech is the main path in practice)
"""
from __future__ import annotations

import re
from typing import List, Optional

from backend.words import WORDS

MAX_GUESS_WORDS = 4

_FILLER_PREFIXES = [
    "is it a", "is it an", "is it the", "is it", "is that a", "is that an", "is that",
    "is this a", "is this", "it's a", "it's an", "its a", "it is a", "it is an", "it is",
    "it's", "i think it's a", "i think it's", "i think it is a", "i think", "maybe a",
    "maybe", "a", "an", "the", "um", "uh", "hmm", "oh", "ok", "okay", "so", "like",
    "i guess", "could it be a", "could it be", "how about a", "how about", "what about a",
    "no", "nope", "yes", "yeah", "wait", "well", "oh wait", "hmm wait", "actually", "or",
]
_NON_GUESSES = {
    "", "yes", "no", "yeah", "nope", "wait", "hold on", "hmm", "um", "uh", "ok", "okay",
    "what", "huh", "next", "skip", "hint", "i don't know", "no idea", "pass", "ready",
    "hello", "hi", "hey", "thanks", "thank you", "go", "let's go", "cool", "nice",
}
UNSURE_PHRASES = [
    "can't see", "cannot see", "can not see", "hold it closer", "hold it up", "too far",
    "too blurry", "not clear", "too dark", "can't make it out", "don't see",
]

_PAL_GUESS_RE = re.compile(
    r"\b(?:is it|is that|is this|it's|it is|that's|that is|looks like|could it be|"
    r"i think it's|i bet it's|maybe it's|my guess is|i'm guessing|i guess)"
    r"\s+(?:an?|the|some)?\s*([a-z][a-z' -]{1,30}?)(?=\s*(?:[?.!,]|$|\bor\b|\bmaybe\b))"
)


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'").replace("-", " ")
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def accepted_answers(word: str) -> List[str]:
    entry = WORDS.get(word)
    answers = [word] + (list(entry["variants"]) if entry else [])
    return [normalize(a) for a in answers]


def _phrase_in(phrase: str, text: str) -> bool:
    return re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?:s|es)?(?![a-z])", text) is not None


def matches_word(text: str, word: str) -> bool:
    """True if `text` names `word` (or an accepted variant) anywhere."""
    norm = normalize(text)
    return any(_phrase_in(a, norm) for a in accepted_answers(word))


def strip_fillers(text: str) -> str:
    norm = normalize(text)
    changed = True
    while changed:
        changed = False
        for p in sorted(_FILLER_PREFIXES, key=len, reverse=True):
            if norm == p:
                return ""
            if norm.startswith(p + " "):
                norm = norm[len(p) + 1:]
                changed = True
                break
    return norm.strip()


def extract_user_guess(text: str, secret: str) -> Optional[str]:
    """What the user guessed, or None if the utterance is chatter / a command."""
    if matches_word(text, secret):
        return normalize(secret)
    core = strip_fillers(text)
    if core in _NON_GUESSES or not core:
        return None
    if len(core.split()) > MAX_GUESS_WORDS:
        return None
    return core


def extract_pal_guesses(text: str) -> List[str]:
    """Guesses the PAL said out loud, in order. Fallback for when it skips the tool."""
    norm = text.lower().replace("’", "'")
    found: List[str] = []
    for m in _PAL_GUESS_RE.finditer(norm):
        g = normalize(m.group(1))
        g = strip_fillers(g)
        if g and g not in _NON_GUESSES and len(g.split()) <= MAX_GUESS_WORDS and g not in found:
            found.append(g)
    return found


def is_unsure(text: str) -> bool:
    """The PAL is saying it cannot see the paper (honesty fallback), not guessing."""
    norm = text.lower().replace("’", "'")
    return any(p in norm for p in UNSURE_PHRASES)


def same_guess(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    return na == nb or na.rstrip("s") == nb.rstrip("s")


# ---------------------------------------------------------------- voice commands between rounds

_START_PHRASES = [
    "let's start", "lets start", "let us start", "start", "start the game", "start round", "let's go", "lets go",
    "go", "ready", "i'm ready", "im ready", "we're ready", "next round", "next", "let's play", "lets play",
    "begin", "let's begin", "let's do it", "lets do it", "let's do this", "bring it on", "hit me",
]
_NOT_YET = ["not ready", "not yet", "don't start", "dont start", "do not start", "wait", "hold on", "one sec",
            "one second", "give me a", "hang on", "not now", "stop"]


def is_start_intent(text: str) -> bool:
    """Player wants to start / move to the next round ("let's start", "go", "ready", "next round").
    Negatives like "I'm not ready" or "wait" win over any start phrase."""
    norm = normalize(text)
    if not norm or any(_phrase_in(normalize(p), norm) for p in _NOT_YET):
        return False
    return any(_phrase_in(normalize(p), norm) for p in _START_PHRASES)


# ---------------------------------------------------------------- near misses (speech-to-text mishearings)

def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def is_near_miss(guess: str, word: str) -> bool:
    """A guess that is almost the word, like "slow man" for "snowman": probably a mishearing.
    Spaces are ignored; 1 letter off for words of 4-6 letters, 2 for longer. 3-letter words never
    count as near misses (cat/car/cap are real different guesses)."""
    g = normalize(guess).replace(" ", "")
    for answer in accepted_answers(word):
        a = answer.replace(" ", "")
        if len(a) < 4 or g == a:
            continue
        limit = 1 if len(a) <= 6 else 2
        if abs(len(g) - len(a)) <= limit and _edit_distance(g, a) <= limit:
            return True
    return False
