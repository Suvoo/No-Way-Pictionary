"""Unit tests for not talking over the PAL (game.route_effects). Run: pytest backend/tests -q"""
from __future__ import annotations

from backend import game

T0 = 1_000_000.0


def _live_round():
    g = game.new_game(T0, words=["star", "heart", "moon", "fish", "cup", "key"])
    game.start_round(g, T0)  # round 1, player draws
    return g


def test_say_waits_while_pal_talks_and_goes_out_when_it_stops():
    g = _live_round()
    game.pal_started_speaking(g, T0 + 10)
    out = game.route_effects(g, [{"kind": "say", "text": "reveal"}, {"kind": "context", "text": "ctx"}], T0 + 10.5)
    assert [e["kind"] for e in out] == ["context"]  # silent update goes now, the spoken line waits
    game.pal_stopped_speaking(g, T0 + 12)
    out = game.route_effects(g, [], T0 + 12)
    assert [e["text"] for e in out] == ["reveal"] and g.pending_says == []


def test_held_prompt_is_dropped_if_the_round_ended():
    g = _live_round()
    game.pal_started_speaking(g, T0 + 10)
    game.route_effects(g, [{"kind": "say", "droppable": True, "text": "look again"}], T0 + 10.2)
    game.end_round(g, T0 + 11, reason="correct")  # round ends while the prompt is held
    game.pal_stopped_speaking(g, T0 + 12)
    assert game.route_effects(g, [], T0 + 12) == []


def test_never_hold_longer_than_the_cap():
    g = _live_round()
    game.pal_started_speaking(g, T0 + 10)  # "stopped" event never arrives
    game.route_effects(g, [{"kind": "say", "text": "reveal"}], T0 + 11)
    out = game.route_effects(g, [], T0 + 10 + game.MAX_HOLD_SECONDS + 0.1)
    assert [e["text"] for e in out] == ["reveal"]


def test_no_look_prompt_while_pal_is_talking():
    g = _live_round()
    game.pal_started_speaking(g, T0 + 15)
    assert not [e for e in game.tick(g, T0 + 15.5) if e["kind"] == "say"]
