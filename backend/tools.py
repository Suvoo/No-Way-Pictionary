"""Tools the PAL calls mid-conversation, and how the backend answers them.

Delivery path (verified against the Tavus OpenAPI spec, Nov 26 2026):
  PAL decides to call a tool
    -> Tavus sends `conversation.tool_call` over the Daily data channel to the browser
    -> browser POSTs the raw event to /api/games/{id}/events (frontend/src/CviEmbed.tsx)
    -> handle_tool_call() below runs it through the game referee
    -> backend sends `conversation.tool_result` to Tavus server-side (send-app-message)

Tools:
  draw_next_stroke()   PAL adds the next pre-made stroke to the canvas.
  submit_guess(guess)  retired (see RETIRED_TOOLS); PAL guesses are scored from its speech.
  (request_hint is a button for the player, see app.py; reveal_answer is game.end_round,
   backend-only, deliberately NOT exposed to the PAL so it cannot end a round early.)
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from backend import game, scorer

# Sent to POST /v2/tools by backend/setup_tavus.py.
# submit_guess was retired after two live games: the PAL never called it, and the referee scores what
# the PAL says out loud instead (scorer.extract_pal_guesses), which is what the player hears anyway.
# Its handler below stays, so a stray call is still scored the same way.
RETIRED_TOOLS = {"submit_guess"}

TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "draw_next_stroke",
        "description": (
            "Call this in rounds where YOU are drawing, to add the next line of your sketch to the canvas. "
            "The game server draws it and tells you what shape appeared, so you can describe it without "
            "saying the secret word. Call it again after each wrong guess."
        ),
        "parameters": {"type": "object", "properties": {}},
        "on_call": "silent",
        "on_resolve": "generate_response",
    },
]


def handle_tool_call(g: game.Game, name: str, arguments: Any, tool_call_id: str, now: float) -> Tuple[str, List[game.Effect]]:
    """Returns (output text for the PAL, effects). The caller adds the tool_result effect."""
    args = _parse_args(arguments)
    if name == "submit_guess":
        return _submit_guess(g, str(args.get("guess", "")), now)
    if name == "draw_next_stroke":
        return _draw_next_stroke(g, now)
    return f"Unknown tool {name}.", []


def _submit_guess(g: game.Game, raw: str, now: float) -> Tuple[str, List[game.Effect]]:
    if g.state not in game.ACTIVE_STATES:
        return "No round is active right now. Wait for the next round.", []
    r = g.round()
    if r.drawer == "pal":
        return "You are drawing this round, not guessing. Call draw_next_stroke instead.", []
    guess = scorer.strip_fillers(raw) or None
    entry, effects = game.record_guess(g, "pal", raw, guess, now, "tool")
    left = game.MAX_GUESSES - r.guesses_used
    if entry.note == "same guess, heard twice":
        out = "Correct!" if entry.correct else f"Already recorded: wrong. {left} guesses left."
    elif entry.note == "already tried":
        out = "You already guessed that. Try something different."
    elif entry.note == "correct":
        out = "Correct! You won the point. The round is over."
    elif entry.note == "wrong" and r.status == "active":
        out = f"Wrong. {left} guesses left. Look again and change your mind out loud."
    elif entry.note == "wrong":
        out = "Wrong, and that was your last guess. The round is over."
    else:
        out = f"Not counted ({entry.note})."
    return out, effects


def _draw_next_stroke(g: game.Game, now: float) -> Tuple[str, List[game.Effect]]:
    if g.state != "PAL_DRAW":
        return "You are not drawing right now. Do not draw.", []
    label, effects = game.draw_next_stroke(g, now, by="pal_tool")
    if not label:
        return "Every stroke is already on the canvas. Encourage the player to guess.", effects
    total = len(game.STROKES[g.round().word])
    return (f"Stroke {g.round().strokes_drawn} of {total} is on the canvas: {label}. "
            "Describe it in a few words without saying the word."), effects


def _parse_args(arguments: Any) -> Dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    try:
        parsed = json.loads(arguments or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}
