"""Game state machine. The backend owns ALL game state; the PAL owns none of it.

States, in order (no skipping, one round at a time):

    ROUND_START  game created, Tavus call joining, waiting for the player to start (button or voice)
    USER_DRAW    rounds 1, 3, 5: player draws on paper, PAL guesses
    PAL_DRAW     rounds 2, 4, 6: PAL draws on the canvas, player guesses
    REVEAL       round over: word shown, point given, waiting for "Next round"
    GAME_OVER    after round 6: scoreboard, Tavus conversation closed

Scoring ("guessers only"): a correct guess within MAX_GUESSES scores 1 point for the guesser. A missed
round (3 wrong guesses or the timer runs out) scores for nobody. So the score is who guessed more, and
drawing badly on purpose never earns the drawer a point (the old "drawer wins a miss" rule did).

This module is pure: callers pass `now` (unix seconds) and get back a list of Effects,
plain dicts describing what to tell the PAL. `app.py` sends them to Tavus. That keeps the
whole game testable without a video call (see backend/evals/run_evals.py).

Effect kinds:
    {"kind": "context", "text": ...}         overwrite the PAL's conversational context
    {"kind": "append_context", "text": ...}  add a silent note to the PAL's context
    {"kind": "say", "text": ...}             make the PAL respond now (conversation.respond)
    {"kind": "speak", "text": ...}           make the PAL say exactly this text (conversation.echo)
    {"kind": "tool_result", "tool_call_id": ..., "output": ...}
    {"kind": "end_conversation", "delay": seconds}
"""
from __future__ import annotations

import json
import random
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend import prompts, scorer
from backend.words import V1_WORDS, WORDS

ROUNDS = 6
ROUND_SECONDS = 45
MAX_GUESSES = 3
LATE_GRACE_SECONDS = 3.0  # a guess heard this soon after the buzzer still counts (speech-to-event lag measured ~1-2s live)
AUTO_STROKE_SECONDS = 7  # backend draws the next stroke itself if the PAL has not for this long
SILENCE_NUDGE_SECONDS = 15  # PAL-draw round: nudge the player once after this much silence (10s talked over a guess live)
LOOK_QUIET_SECONDS = 9  # player-draw round: prompt the PAL to look again after this long without it speaking
MAX_LOOK_NUDGES = 3
NARRATE_QUIET_SECONDS = 4  # auto-stroke: PAL narrates it only if both sides have been quiet this long
CONTINUATION_SECONDS = 10  # a user utterance that extends the previous one within this window is one utterance
HINT_AFTER_WRONG = 2  # hint unlocks after this many wrong guesses...
HINT_AFTER_SECONDS = 20  # ...or this many seconds into the round
SAME_GUESS_WINDOW = 8  # same guess via tool + transcript within this window = one guess

STATES = ["ROUND_START", "USER_DRAW", "PAL_DRAW", "REVEAL", "GAME_OVER"]
ACTIVE_STATES = ("USER_DRAW", "PAL_DRAW")

Effect = Dict[str, Any]

STROKES: Dict[str, List[Dict[str, Any]]] = json.loads(
    (Path(__file__).parent / "strokes.json").read_text()
)["templates"]


def drawer_for(index: int) -> str:
    """Round 1 = user draws, round 2 = PAL draws, alternating."""
    return "user" if index % 2 == 1 else "pal"


def other(role: str) -> str:
    return "pal" if role == "user" else "user"


@dataclass
class Guess:
    round: int
    guesser: str  # "user" | "pal"
    text: str  # raw text as heard / typed (audit trail)
    guess: Optional[str]  # normalized guess, None if the line was not a guess
    correct: bool
    counted: bool  # did it use up one of the 3 guesses
    note: str  # why: "wrong", "correct", "already tried", "too late", ...
    source: str  # "tool" | "transcript" | "speech" | "typed" | "mock"
    at: float


@dataclass
class Round:
    index: int
    drawer: str
    word: str
    status: str = "pending"  # pending | active | guessed | missed
    started_at: Optional[float] = None
    deadline: Optional[float] = None
    ended_at: Optional[float] = None
    end_reason: Optional[str] = None  # correct | out_of_guesses | timeout | quit
    winner: Optional[str] = None
    guesses_used: int = 0
    wrong_guesses: List[str] = field(default_factory=list)
    strokes_drawn: int = 0
    stroke_log: List[Dict[str, Any]] = field(default_factory=list)
    last_stroke_at: Optional[float] = None
    last_user_speech_at: Optional[float] = None
    nudged: bool = False
    started_by: str = "button"  # "button" or "voice" (audit only)
    look_nudges: int = 0
    last_look_nudge_at: Optional[float] = None
    last_pal_speech_at: Optional[float] = None
    last_user_text: str = ""
    hint_shown: bool = False
    flags: List[str] = field(default_factory=list)  # audit notes, e.g. "player said the word out loud"
    word_swaps: int = 0  # times the player's word was replaced because they said it out loud
    retired_words: List[str] = field(default_factory=list)
    notice: Optional[str] = None  # one-line message for the player's screen this round


@dataclass
class Game:
    id: str
    player_token: str
    created_at: float
    rounds: List[Round]
    state: str = "ROUND_START"
    current: int = 1
    score: Dict[str, int] = field(default_factory=lambda: {"user": 0, "pal": 0})
    guesses: List[Guess] = field(default_factory=list)
    conversation_id: Optional[str] = None
    conversation_url: Optional[str] = None
    mock: bool = True
    processed: List[str] = field(default_factory=list)  # idempotency keys already handled
    conversation_ended: bool = False
    transcript: Optional[List[Dict[str, Any]]] = None  # filled by the post-call webhook
    latencies: List[float] = field(default_factory=list)  # seconds from player stops talking to PAL starts
    last_user_stop_ts: Optional[float] = None
    pal_speaking: bool = False  # from Tavus started/stopped_speaking events (live mode only)
    pal_speaking_since: Optional[float] = None
    pal_speaking_until: Optional[float] = None  # estimated end of the PAL's current sentence
    pending_says: List[Dict[str, Any]] = field(default_factory=list)  # "say" effects held while the PAL talks

    # ---------- persistence ----------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Game":
        d = dict(d)
        d["rounds"] = [Round(**r) for r in d["rounds"]]
        d["guesses"] = [Guess(**g) for g in d["guesses"]]
        return Game(**d)

    def round(self) -> Round:
        return self.rounds[self.current - 1]

    def seen(self, key: str) -> bool:
        """Idempotency: returns True if `key` was already handled, else records it."""
        if key in self.processed:
            return True
        self.processed.append(key)
        self.processed = self.processed[-500:]
        return False


# ---------------------------------------------------------------- setup

def pick_words(rng: random.Random, exclude: Iterable[str] = ()) -> List[str]:
    """6 distinct words from the v1 bank, avoiding `exclude` (e.g. last game's words)."""
    pool = [w for w in V1_WORDS if w not in set(exclude)]
    if len(pool) < ROUNDS:
        pool = list(V1_WORDS)
    return rng.sample(pool, ROUNDS)


def new_game(now: float, rng: Optional[random.Random] = None, words: Optional[List[str]] = None,
             exclude: Iterable[str] = (), mock: bool = True) -> Game:
    rng = rng or random.Random()
    words = words or pick_words(rng, exclude)
    if len(words) != ROUNDS or len(set(words)) != ROUNDS:
        raise ValueError("a game needs 6 distinct words")
    for w in words:
        if w not in WORDS or w not in STROKES:
            raise ValueError(f"word not in v1 bank: {w}")
    rounds = [Round(index=i + 1, drawer=drawer_for(i + 1), word=w) for i, w in enumerate(words)]
    return Game(id=secrets.token_urlsafe(8), player_token=secrets.token_urlsafe(16),
                created_at=now, rounds=rounds, mock=mock)


# ---------------------------------------------------------------- round lifecycle

def start_round(g: Game, now: float) -> List[Effect]:
    """ROUND_START -> round 1, or REVEAL -> next round."""
    if g.state == "REVEAL":
        g.current += 1
    elif g.state != "ROUND_START":
        raise GameError(f"cannot start a round from {g.state}")
    r = g.round()
    r.status, r.started_at, r.deadline = "active", now, now + ROUND_SECONDS
    r.last_user_speech_at = now
    g.state = "USER_DRAW" if r.drawer == "user" else "PAL_DRAW"

    if r.drawer == "user":
        return [
            {"kind": "context", "text": prompts.user_draw_context(r.index, ROUNDS, g.score, MAX_GUESSES, ROUND_SECONDS)},
            {"kind": "say", "text": f"[game] Round {r.index} starts now. The player is drawing. "
                                    "Tell them to go in one short sentence, then watch the camera."},
        ]
    labels = [s["label"] for s in STROKES[r.word]]
    effects: List[Effect] = [
        {"kind": "context", "text": prompts.pal_draw_context(r.index, ROUNDS, r.word, labels, g.score, ROUND_SECONDS)}
    ]
    label, _ = draw_next_stroke(g, now, by="auto")  # canvas never starts blank
    effects.append({"kind": "say", "text": f"[game] Round {r.index} starts now. You are drawing. "
                                           f"Stroke 1 is on the canvas: {label}. Tell the player to watch the "
                                           "canvas and describe that shape, without saying the word."})
    return effects


def end_round(g: Game, now: float, reason: str) -> List[Effect]:
    """The backend-only reveal_answer. The PAL cannot call this.
    reason: "correct" (the guesser scores) | "out_of_guesses" | "timeout" (nobody scores)
            | "gave_away" (player said their own word twice: the PAL scores)."""
    r = g.round()
    if r.status != "active":
        return []
    r.status = "guessed" if reason == "correct" else "missed"
    winner = other(r.drawer) if reason in ("correct", "gave_away") else None
    r.ended_at, r.end_reason, r.winner = now, reason, winner
    if winner:
        g.score[winner] += 1
    last = r.index >= ROUNDS
    g.state = "GAME_OVER" if last else "REVEAL"

    # Live findings: the PAL misread who won ("No way, you got me!" after its own correct guess) and its
    # reactions skipped the word ("Boom! I nailed it."). Reveals are now fixed lines the PAL speaks word
    # for word (conversation.echo), so every reveal names the word and the outcome exactly.
    line = reveal_line(r)
    if last:
        line += (f" That's the game: you {g.score['user']}, me {g.score['pal']}. "
                 "Thanks for playing, see you next time!")
    else:
        line += " Say next round when you're ready."
    # The spoken line goes first so the PAL talks as the reveal appears on screen; the context overwrite
    # (which clears the round's secret and tells the PAL what happened) follows right behind it.
    effects: List[Effect] = [
        {"kind": "speak", "text": line},
        {"kind": "context", "text": prompts.reveal_context(r.index, ROUNDS, r.word, g.score)
         + f" What happened: {reveal_outcome(r)} You already announced it."},
    ]
    if last:
        effects.append({"kind": "end_conversation", "delay": 15})
        g.conversation_ended = True
    return effects


def reveal_line(r: Round) -> str:
    """The exact words the PAL says at the reveal. Always names the word."""
    w = r.word
    if r.drawer == "user":  # the PAL was guessing the player's drawing
        if r.end_reason == "correct":
            return f"Boom, it was {w}."
        if r.end_reason == "gave_away":
            return f"You said it again! It was {w}, so the point is mine."
        if r.end_reason == "out_of_guesses":
            return f"Aw, it was {w}! I'm out of guesses. No point this round."
        return f"Time's up! It was {w}. No point this round."
    if r.end_reason == "correct":  # the player was guessing the PAL's drawing
        return f"Yes! It was {w}. Point to you."
    if r.end_reason == "out_of_guesses":
        return f"Nope, it was {w}! No point this round."
    return f"Time's up! It was {w}. No point this round."


def reveal_outcome(r: Round) -> str:
    """What happened this round, said TO the PAL ("you" = the PAL). Guessers-only scoring."""
    if r.drawer == "user":  # the PAL was guessing the player's drawing
        if r.end_reason == "gave_away":
            return "The player said their secret word out loud again, so you get the point. Tease them gently."
        if r.end_reason == "correct":
            return "You guessed it, your guess was right! You get the point. Celebrate."
        if r.end_reason == "out_of_guesses":
            return "You used all 3 guesses without getting it. No point this round."
        return "Time ran out before you guessed it. No point this round."
    if r.end_reason == "correct":  # the player was guessing the PAL's drawing
        return "The player guessed your drawing correctly. They get the point. Congratulate them."
    if r.end_reason == "out_of_guesses":
        return "The player used all 3 guesses without getting your drawing. No point this round."
    return "Time ran out before the player guessed your drawing. No point this round."


def quit_game(g: Game, now: float) -> List[Effect]:
    if g.state in ACTIVE_STATES:
        r = g.round()
        r.status, r.ended_at, r.end_reason = "missed", now, "quit"
    g.state = "GAME_OVER"
    if g.conversation_ended:
        return []
    g.conversation_ended = True
    return [{"kind": "end_conversation", "delay": 0}]


def tick(g: Game, now: float) -> List[Effect]:
    """Timers. Called every second by the app and on every read. Idempotent."""
    if g.state not in ACTIVE_STATES:
        return []
    r = g.round()
    if r.deadline is not None and now > r.deadline + LATE_GRACE_SECONDS:
        return end_round(g, now, reason="timeout")
    effects: List[Effect] = []
    if r.drawer == "user":
        # Live findings: the PAL waits for the player to speak before it looks, and goes quiet after a
        # wrong guess. Whenever it has been quiet for LOOK_QUIET_SECONDS (and since the last prompt),
        # prompt it to look again, up to MAX_LOOK_NUDGES times a round.
        quiet_since = max(r.last_pal_speech_at or 0, r.started_at or 0, r.last_look_nudge_at or 0)
        if not g.pal_speaking and r.look_nudges < MAX_LOOK_NUDGES and now - quiet_since >= LOOK_QUIET_SECONDS:
            r.look_nudges += 1
            r.last_look_nudge_at = now
            effects.append({"kind": "say", "droppable": True, "text": (
                "[game] Look at the camera now and keep guessing, in your own words (do not repeat this message). "
                "Describe what you see and guess, or change your guess if you already made one. Only if you "
                "truly see no paper, ask the player to hold it up.")})
    if r.drawer == "pal":
        if r.last_stroke_at is not None and now - r.last_stroke_at >= AUTO_STROKE_SECONDS:
            label, _ = draw_next_stroke(g, now, by="auto")
            if label:
                quiet = (now - (r.last_pal_speech_at or 0) >= NARRATE_QUIET_SECONDS
                         and now - (r.last_user_speech_at or 0) >= NARRATE_QUIET_SECONDS)
                if quiet:  # nobody is talking: have the PAL narrate the new line out loud
                    effects.append({"kind": "say", "text": (
                        f"[game] Stroke {r.strokes_drawn} just appeared on the canvas: {label}. "
                        "Describe the new line in a few words, without saying the word.")})
                else:  # someone is mid-sentence: tell the PAL silently, do not talk over them
                    effects.append({"kind": "append_context", "text": (
                        f"[game] Stroke {r.strokes_drawn} just appeared on the canvas: {label}.")})
        quiet_since = max(r.last_user_speech_at or 0, r.started_at or 0)
        if not r.nudged and now - quiet_since >= SILENCE_NUDGE_SECONDS:
            r.nudged = True
            effects.append({"kind": "say", "droppable": True, "text": (
                "[game] The player has been quiet for a while. Encourage them once, in one short sentence: "
                "they can shout a guess, or say 'skip' for another line.")})
    return effects


# ---------------------------------------------------------------- strokes and hints

def draw_next_stroke(g: Game, now: float, by: str) -> Tuple[Optional[str], List[Effect]]:
    """Reveal the next pre-made stroke. Returns (label for the PAL, effects). The PAL decides
    WHEN to draw; the template decides WHAT is drawn, so the PAL cannot draw nonsense."""
    if g.state != "PAL_DRAW":
        return None, []
    r = g.round()
    template = STROKES[r.word]
    if r.strokes_drawn >= len(template):
        return None, []
    stroke = template[r.strokes_drawn]
    r.strokes_drawn += 1
    r.last_stroke_at = now
    r.stroke_log.append({"stroke": r.strokes_drawn, "by": by, "at": now})
    return stroke["label"], []


def hint_available(r: Round, now: float) -> bool:
    if r.drawer != "pal" or r.status != "active" or r.hint_shown:
        return False
    return len(r.wrong_guesses) >= HINT_AFTER_WRONG or (now - (r.started_at or now)) >= HINT_AFTER_SECONDS


def request_hint(g: Game, now: float) -> Tuple[Optional[str], List[Effect]]:
    """PAL-draw rounds only; a hint in a user-draw round would leak the player's word to the PAL."""
    if g.state != "PAL_DRAW":
        return None, []
    r = g.round()
    if not hint_available(r, now):
        return None, []
    r.hint_shown = True
    hint = WORDS[r.word]["hint"]
    return hint, [{"kind": "append_context", "text": f"[game] The player was shown this hint on screen: \"{hint}\"."}]


def look_now(g: Game, now: float) -> List[Effect]:
    """The "Look now" button: Raven watches the camera all the time; this just tells the PAL
    the paper is up right now, so it guesses immediately instead of waiting."""
    if g.state != "USER_DRAW":
        return []
    return [{"kind": "say", "text": "[game] The player is holding the drawing up to the camera right now. "
                                    "Look at it, say what you see, and guess."}]


# ---------------------------------------------------------------- guesses

def record_guess(g: Game, guesser: str, raw: str, guess: Optional[str], now: float,
                 source: str) -> Tuple[Guess, List[Effect]]:
    """The referee. Checks one guess against the secret, counts it, maybe ends the round."""
    r = g.round()
    entry = Guess(round=r.index, guesser=guesser, text=raw, guess=guess, correct=False,
                  counted=False, note="", source=source, at=now)

    def log(note: str) -> Tuple[Guess, List[Effect]]:
        entry.note = note
        g.guesses.append(entry)
        return entry, []

    if g.state not in ACTIVE_STATES or r.status != "active":
        entry.note = "no active round"
        return entry, []  # not logged: chatter between rounds is not part of the audit trail
    if guesser == r.drawer:
        return log("not your turn to guess")
    if not guess:
        return log("not a guess")
    if r.deadline is not None and now > r.deadline + LATE_GRACE_SECONDS:
        return log("too late")

    for prev in g.guesses:
        if (prev.round == r.index and prev.guesser == guesser and prev.guess and not prev.note.startswith("void")
                and scorer.same_guess(prev.guess, guess)):
            if prev.source != source and now - prev.at <= SAME_GUESS_WINDOW:
                entry.correct = prev.correct
                return log("same guess, heard twice")
            return log("already tried")

    if guesser == "user" and source == "speech" and not scorer.matches_word(guess, r.word) and scorer.is_near_miss(guess, r.word):
        # Live finding: "Snowman" was transcribed as "slow man". Almost the word = probably a mishearing,
        # so it does not use up a guess; the PAL asks the player to say it again.
        log("close: possible mishearing, not counted")
        return entry, [{"kind": "say", "text": (
            f"[game] The player said '{guess}', which sounds very close to your word. In one short sentence, "
            "tell them it's so close and to say it again clearly. Do not say the word.")}]

    entry.counted = True
    r.guesses_used += 1
    if scorer.matches_word(guess, r.word):
        entry.correct = True
        entry.note = "correct"
        g.guesses.append(entry)
        return entry, end_round(g, now, reason="correct")

    r.wrong_guesses.append(guess)
    entry.note = "wrong"
    g.guesses.append(entry)
    if r.guesses_used >= MAX_GUESSES:
        return entry, end_round(g, now, reason="out_of_guesses")

    effects: List[Effect] = []
    if guesser == "user" and r.drawer == "pal":  # wrong guess -> the PAL draws another line
        label, _ = draw_next_stroke(g, now, by="after_wrong_guess")
        left = MAX_GUESSES - r.guesses_used
        note = f"[game] The player guessed '{guess}', which is wrong. {left} guesses left."
        if label:
            note += f" Stroke {r.strokes_drawn} just appeared: {label}."
        effects.append({"kind": "append_context", "text": note})
    return entry, effects


def handle_user_speech(g: Game, text: str, now: float, source: str = "speech") -> List[Effect]:
    if text.strip().startswith("[game]"):
        return []
    if g.state in ("ROUND_START", "REVEAL"):
        # Voice start: "let's start", "go", "ready", "next round" do what the Start / Next button does.
        if scorer.is_start_intent(text):
            effects = start_round(g, now)
            g.round().started_by = "voice"
            if g.round().drawer == "user":
                # Live finding: the PAL already answers "let's start" itself ("Let's go!"). A second
                # scripted line made it talk twice and added ~2s. Keep only the silent context update.
                effects = [e for e in effects if e["kind"] != "say"]
            return effects
        return []
    if g.state not in ACTIVE_STATES:
        return []
    r = g.round()
    # Live finding: Tavus re-sends a growing user utterance ("No, I think-" then "No, I think- Drummers.").
    # Only the new tail of an utterance that extends the previous one is scored, and a fragment that
    # ends mid-sentence (trailing dash) is not a guess yet.
    prev, full = scorer.normalize(r.last_user_text), scorer.normalize(text)
    if (prev and len(full) > len(prev) and full.startswith(prev)
            and now - (r.last_user_speech_at or 0) <= CONTINUATION_SECONDS):
        text = full[len(prev):].strip()
    r.last_user_text = full
    r.last_user_speech_at = now
    if not text or text.rstrip().endswith(("—", "–", "-", "...", "…")):
        return []
    norm = scorer.normalize(text)
    if r.drawer == "user":
        # The player is drawing. Saying their own word out loud (live, Nov 26: "The word is fish, bro.")
        # voids it: first time they get a new word and a fresh round; second time Pip gets the point.
        if scorer.matches_word(text, r.word):
            return said_word_out_loud(g, now)
        return []
    # PAL is drawing: commands first, then guesses.
    if norm in ("skip", "next", "next line", "another line", "draw more", "more"):
        label, _ = draw_next_stroke(g, now, by="player_skip")
        return [{"kind": "append_context", "text": f"[game] The player asked for another line. Stroke {r.strokes_drawn} appeared: {label}."}] if label else []
    if norm in ("hint", "give me a hint", "hint please", "can i have a hint"):
        _, effects = request_hint(g, now)
        return effects
    guess = scorer.extract_user_guess(text, r.word)
    if guess is None:
        return []
    _, effects = record_guess(g, "user", text, guess, now, source)
    return effects


def said_word_out_loud(g: Game, now: float) -> List[Effect]:
    """Player's round: the player said their own secret word, so Pip has heard it."""
    r = g.round()
    if r.word_swaps >= 1:  # second time this round: it was given away, Pip gets the point
        r.flags.append(f"player said the word out loud again ({r.word})")
        return end_round(g, now, reason="gave_away")
    old = r.word
    taken = {x.word for x in g.rounds} | set(r.retired_words)
    pool = [w for w in V1_WORDS if w not in taken] or [w for w in V1_WORDS if w != old]
    r.retired_words.append(old)
    r.word = random.Random(f"{g.id}:{r.index}:{now}").choice(pool)
    r.word_swaps += 1
    r.flags.append(f"player said the word out loud ({old}), replaced with a new word")
    r.notice = "You said your word out loud! Here's a new one. Say it again and Pip gets the point."
    r.deadline = now + ROUND_SECONDS  # fresh round on the new word
    r.guesses_used, r.wrong_guesses = 0, []
    r.look_nudges, r.last_look_nudge_at, r.started_at = 0, None, now
    for x in g.guesses:  # guesses on the old word no longer count (and leave the on-screen list)
        if x.round == r.index and x.counted:
            x.counted, x.note = False, f"void: word replaced ({x.note})"
    return [
        {"kind": "context", "text": prompts.user_draw_context(r.index, ROUNDS, g.score, MAX_GUESSES, ROUND_SECONDS)},
        {"kind": "say", "text": (
            "[game] The player said their secret word out loud, so the game gave them a NEW secret word. "
            "The old word does not count and you do not know the new one. Say one short playful line like "
            "\"No cheating! New word!\" and watch for the new drawing.")},
    ]


SECONDS_PER_WORD = 0.36  # ~165 words a minute, Tavus TTS pace


def speaking_time(text: str) -> float:
    return min(12.0, 0.4 + SECONDS_PER_WORD * len(text.split()))


def handle_pal_speech(g: Game, text: str, now: float) -> List[Effect]:
    if text.strip().startswith("[game]"):
        return []
    # Live finding (Nov 26): the PAL's sentence can reach us before Tavus's "started speaking" event, and
    # the reveal it triggered then cut "...is it a pair of glasses?" off before "glasses". A PAL sentence
    # itself means the PAL is talking for about this long; route_effects holds spoken lines until then.
    g.pal_speaking_until = max(g.pal_speaking_until or 0, now + speaking_time(text))
    if g.state not in ACTIVE_STATES:
        return []
    r = g.round()
    r.last_pal_speech_at = now
    if r.drawer == "pal":
        if scorer.matches_word(text, r.word) and "PAL said its own word" not in r.flags:
            r.flags.append("PAL said its own word")
        return []
    if scorer.is_unsure(text) and not scorer.extract_pal_guesses(text):
        g.guesses.append(Guess(round=r.index, guesser="pal", text=text, guess=None, correct=False,
                               counted=False, note="honesty fallback: asked to hold it closer",
                               source="transcript", at=now))
        return []
    guesses = scorer.extract_pal_guesses(text)
    # Live findings (Nov 26): a right guess in the sentence wins and the other guesses around it are not
    # extra tries; but the word in a mere description ("A heart and a cone... is it an ice cream?")
    # is not a guess. Only the extracted guesses count.
    right = [x for x in guesses if scorer.matches_word(x, r.word)]
    if right:
        guesses = right[:1]
    effects: List[Effect] = []
    for guess in guesses:
        if g.state not in ACTIVE_STATES:
            break
        _, fx = record_guess(g, "pal", text, guess, now, "transcript")
        effects += fx
    return effects


# ---------------------------------------------------------------- not talking over the PAL

MAX_HOLD_SECONDS = 8  # never hold a message longer than this (a missed "stopped speaking" event)


def pal_started_speaking(g: Game, now: float) -> None:
    g.pal_speaking, g.pal_speaking_since = True, now


def pal_stopped_speaking(g: Game, now: float) -> None:
    g.pal_speaking, g.pal_speaking_since, g.pal_speaking_until = False, None, None


def route_effects(g: Game, effects: List[Effect], now: float) -> List[Effect]:
    """Live finding (Nov 26): every "say" (conversation.respond) is a new turn, and Tavus interrupts
    whatever the PAL is saying to answer it, so a timer prompt or a reveal cut the PAL mid-sentence.
    While the PAL is talking, "say" effects wait here and go out when it stops (or after
    MAX_HOLD_SECONDS). A held prompt marked droppable (look again / encourage) is thrown away if the
    round has ended by the time it would go out. Silent effects (context, tool results) never wait."""
    talking = ((g.pal_speaking and now - (g.pal_speaking_since or now) < MAX_HOLD_SECONDS)
               or (g.pal_speaking_until is not None and now < g.pal_speaking_until))
    out: List[Effect] = []
    if not talking and g.pending_says:
        for e in g.pending_says:
            if e.get("droppable") and g.state not in ACTIVE_STATES:
                continue
            out.append(e)
        g.pending_says = []
    spoken = ("say", "speak")
    for e in effects:
        if e["kind"] in spoken and talking:
            g.pending_says.append(e)
        elif e["kind"] in spoken and e.get("droppable") and g.state not in ACTIVE_STATES:
            continue
        else:
            out.append(e)
    if any(e["kind"] in spoken for e in out):
        # Pip's next words answer the backend, not the player: don't count them as player->Pip latency.
        # (Live finding: two fake 6.7s / 7.5s "latencies" were Pip reading a stroke and a reveal.)
        g.last_user_stop_ts = None
    return out


# ---------------------------------------------------------------- views

def public_view(g: Game, now: float) -> Dict[str, Any]:
    """What the browser may see. NEVER includes the PAL's word during a PAL-draw round,
    or any stroke labels. tests/test_api.py checks this."""
    r = g.round()
    ended = r.status in ("guessed", "missed")
    view_round: Dict[str, Any] = {
        "index": r.index,
        "drawer": r.drawer,
        "status": r.status,
        "seconds_left": max(0, int(round(r.deadline - now))) if r.deadline and r.status == "active" else (ROUND_SECONDS if r.status == "pending" else 0),
        "guesses_left": MAX_GUESSES - r.guesses_used,
        "wrong_guesses": list(r.wrong_guesses),
        "your_word": r.word if (r.drawer == "user" and r.status != "pending") else None,
        # PAL rounds: strokes drawn so far; after the round ends, the whole sketch (safe, word is revealed).
        "strokes": [s["shapes"] for s in STROKES[r.word][: (len(STROKES[r.word]) if ended else r.strokes_drawn)]]
        if r.drawer == "pal" else [],
        "can_hint": hint_available(r, now),
        "hint": WORDS[r.word]["hint"] if r.hint_shown else None,
        "revealed_word": r.word if ended else None,
        "winner": r.winner,
        "end_reason": r.end_reason,
        "flags": list(r.flags) if ended else [],
        "notice": r.notice if r.status == "active" else None,
    }
    if r.drawer == "pal" and not ended:
        assert view_round["your_word"] is None and view_round["revealed_word"] is None
    return {
        "game_id": g.id,
        "state": g.state,
        "mock": g.mock,
        "conversation_url": g.conversation_url,
        "conversation_id": g.conversation_id,
        "rounds": ROUNDS,
        "round_seconds": ROUND_SECONDS,
        "max_guesses": MAX_GUESSES,
        "score": dict(g.score),
        "round": view_round,
        "history": [_round_summary(x) for x in g.rounds if x.status in ("guessed", "missed")],
        "guess_log": [_guess_view(x) for x in g.guesses],
    }


def scoreboard(g: Game) -> Dict[str, Any]:
    done = [x for x in g.rounds if x.status in ("guessed", "missed")]
    u, p = g.score["user"], g.score["pal"]
    result = "tie" if u == p else ("user" if u > p else "pal")
    return {
        "game_id": g.id,
        "state": g.state,
        "score": dict(g.score),
        "result": result,
        "rounds": [_round_summary(x) for x in done],
        "guess_log": [_guess_view(x) for x in g.guesses],
        "transcript_received": g.transcript is not None,
    }


def _round_summary(r: Round) -> Dict[str, Any]:
    return {"index": r.index, "drawer": r.drawer, "word": r.word, "winner": r.winner,
            "end_reason": r.end_reason, "guesses_used": r.guesses_used,
            "strokes_drawn": r.strokes_drawn, "flags": list(r.flags), "started_by": r.started_by}


def _guess_view(x: Guess) -> Dict[str, Any]:
    return {"round": x.round, "guesser": x.guesser, "text": x.text, "guess": x.guess,
            "correct": x.correct, "counted": x.counted, "note": x.note, "source": x.source, "at": x.at}


class GameError(Exception):
    pass
