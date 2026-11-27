"""Golden-set eval: replays scripted rounds against the real game engine, prints pass/fail.

    python backend/evals/run_evals.py          # all cases
    python backend/evals/run_evals.py -v       # also print each failing check

No Tavus key, no video call, no network. This proves the GAME LOGIC (referee, scoring,
timers, secret handling). It does not prove Raven can read a drawing; that was the
measured spike (5/5 easy words, Nov 26 2026), and live behaviour is checked by playing.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import game, prompts, tools  # noqa: E402
from backend.words import V1_WORDS, WORDS  # noqa: E402

T0 = 1_000_000.0


def _words_for(word: str, slot: int) -> List[str]:
    others = [w for w in V1_WORDS if w != word][:5]
    ws = others[:]
    ws.insert(slot, word)
    return ws


def run_round_case(case: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    mode, word = case["mode"], case["word"]
    g = game.new_game(T0, words=_words_for(word, 1 if mode == "pal_draw" else 0))
    now = T0
    if mode != "lobby":  # lobby = game created, round 1 not started yet
        game.start_round(g, now)
    if mode == "pal_draw":  # finish round 1 quickly, then start round 2
        game.end_round(g, now, reason="timeout")
        game.start_round(g, now)
    start = now
    effects: List[Dict[str, Any]] = []
    tool_outputs: List[str] = []
    views: List[Dict[str, Any]] = []
    for ev in case.get("events", []):
        t = start + ev["t"]
        effects += game.tick(g, t)
        if "pal" in ev:
            effects += game.handle_pal_speech(g, ev["pal"], t)
        elif "user" in ev:
            effects += game.handle_user_speech(g, ev["user"].replace("NEWWORD", g.round().word), t)
        elif "vision" in ev:  # Raven's written_word_on_paper tool fired with the text it read
            effects += game.handle_written_text(g, ev["vision"]["text"].replace("NEWWORD", g.round().word), t)
        elif "tool" in ev:
            out, fx = tools.handle_tool_call(g, ev["tool"], ev.get("args", {}), f"call{ev['t']}", t)
            tool_outputs.append(out)
            effects += fx
        views.append(game.public_view(g, t))
    r = g.round()
    exp = case["expect"]
    fails: List[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if not ok:
            fails.append(f"{name}: {detail}")

    if "winner" in exp:
        check("winner", r.winner == exp["winner"], f"got {r.winner}")
    if "end_reason" in exp:
        check("end_reason", r.end_reason == exp["end_reason"], f"got {r.end_reason}")
    if "guesses_used" in exp:
        check("guesses_used", r.guesses_used == exp["guesses_used"], f"got {r.guesses_used}")
    if "status" in exp:
        check("status", r.status == exp["status"], f"got {r.status}")
    if "state" in exp:
        check("state", g.state == exp["state"], f"got {g.state}")
    if "score" in exp:
        check("score", g.score == exp["score"], f"got {g.score}")
    if "started_by" in exp:
        check("started_by", r.started_by == exp["started_by"], f"got {r.started_by}")
    if "first_guess" in exp:
        counted = [x for x in g.guesses if x.round == r.index and x.counted]
        check("first_guess", bool(counted) and counted[0].guess == exp["first_guess"],
              f"got {[x.guess for x in counted]}")
    if "log_length" in exp:
        n = len([x for x in g.guesses if x.round == r.index])
        check("log_length", n == exp["log_length"], f"got {n}")
    if "log_contains_note" in exp:
        notes = [x.note for x in g.guesses]
        check("log_contains_note", any(exp["log_contains_note"] in n for n in notes), f"notes {notes}")
    if "strokes_drawn_min" in exp:
        check("strokes_drawn_min", r.strokes_drawn >= exp["strokes_drawn_min"], f"got {r.strokes_drawn}")
    if "revealed_word" in exp:
        check("revealed_word", game.public_view(g, now)["round"]["revealed_word"] == exp["revealed_word"])
    says = [e["text"] for e in effects if e["kind"] in ("say", "speak")]
    if "say_contains" in exp:
        check("say_contains", any(exp["say_contains"] in s for s in says), f"says {says}")
    if "say_count_contains" in exp:
        needle, n = exp["say_count_contains"]
        got = sum(needle in s for s in says)
        check("say_count", got == n, f"'{needle}' said {got} times")
    if "prompt_contains" in exp:
        check("prompt_contains", exp["prompt_contains"] in prompts.SYSTEM_PROMPT)
    if exp.get("word_changed"):
        check("word_changed", r.word != word and word in r.retired_words, f"word {r.word}, retired {r.retired_words}")
    if "flags_contains_text" in exp:
        check("flags_contains_text", any(exp["flags_contains_text"] in f for f in r.flags), f"flags {r.flags}")
    if "flags_contains" in exp:
        check("flags_contains", exp["flags_contains"] in r.flags, f"flags {r.flags}")
    if "tool_output_contains" in exp:
        check("tool_output", any(exp["tool_output_contains"] in o for o in tool_outputs), f"outputs {tool_outputs}")
    if exp.get("word_not_in_view"):
        leaked = [v for v in views if word in json.dumps(v).lower()]
        check("word_not_in_view", not leaked, "secret word found in a browser view")
    if exp.get("next_round_starts"):
        try:
            game.start_round(g, now + 60)
            check("next_round_starts", g.current == 2 and g.state == "PAL_DRAW", f"state {g.state}")
        except game.GameError as e:
            check("next_round_starts", False, str(e))
    return fails, {"guesses": [x.note for x in g.guesses]}


def run_case(case: Dict[str, Any]) -> List[str]:
    mode, exp = case["mode"], case["expect"]
    if mode in ("user_draw", "pal_draw", "lobby"):
        return run_round_case(case)[0]
    if mode == "word_bank":
        return [] if (case["word"] in WORDS) == exp["in_bank"] else [f"in_bank is {case['word'] in WORDS}"]
    if mode == "word_picks":
        dups = overlap = 0
        for seed in range(case["seeds"]):
            rng = random.Random(seed)
            first = game.pick_words(rng)
            second = game.pick_words(rng, exclude=first)
            dups += (len(set(first)) != 6) + (len(set(second)) != 6)
            overlap += len(set(first) & set(second))
        fails = []
        if dups != exp["duplicates"]:
            fails.append(f"duplicates: {dups}")
        if overlap != exp["overlap_with_previous"]:
            fails.append(f"overlap: {overlap}")
        return fails
    if mode == "templates":
        fails = []
        for w in V1_WORDS:
            n = len(game.STROKES.get(w, []))
            if not (exp["min_strokes"] <= n <= exp["max_strokes"]):
                fails.append(f"{w}: {n} strokes")
            if not WORDS[w]["hint"]:
                fails.append(f"{w}: no hint")
        return fails
    return [f"unknown mode {mode}"]


def main() -> int:
    verbose = "-v" in sys.argv
    cases = json.loads((Path(__file__).parent / "golden_set.json").read_text())["cases"]
    passed = 0
    for case in cases:
        fails = run_case(case)
        ok = not fails
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  #{case['id']:>2}  {case['title']}")
        if fails and verbose:
            for f in fails:
                print(f"        - {f}")
    print(f"\n{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
