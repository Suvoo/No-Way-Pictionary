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


def test_latency_not_counted_for_lines_the_backend_triggered():
    g = _live_round()
    g.last_user_stop_ts = 100.0  # player stopped talking...
    game.route_effects(g, [{"kind": "say", "text": "[game] stroke 2 appeared"}], T0 + 20)  # ...then we made Pip talk
    assert g.last_user_stop_ts is None  # so Pip's next start is not measured as a reply to the player


def test_saying_the_word_shows_a_notice_and_hides_the_old_word():
    g = _live_round()
    old = g.round().word
    game.handle_user_speech(g, f"the word is {old}", T0 + 5)
    view = game.public_view(g, T0 + 6)["round"]
    assert view["notice"] and view["your_word"] != old and view["seconds_left"] == game.ROUND_SECONDS - 1


def test_reveal_waits_for_pips_own_winning_sentence():
    """Live replay (Nov 26): the reveal cut "...is it a pair of glasses?" off before "glasses", because
    Pip's sentence reached the backend before Tavus's started_speaking event."""
    g = game.new_game(T0, words=["glasses", "heart", "moon", "fish", "cup", "key"])
    game.start_round(g, T0)
    line = "Two circles and a line... is it a pair of glasses?"
    fx = game.handle_pal_speech(g, line, T0 + 7)  # scored correct -> reveal effects
    assert g.state == "REVEAL"
    out = game.route_effects(g, fx, T0 + 7.6)
    assert not [e for e in out if e["kind"] in ("say", "speak")]  # not while Pip is still saying it
    later = game.route_effects(g, [], T0 + 7 + game.speaking_time(line) + 0.1)
    spoken = [e for e in later if e["kind"] in ("say", "speak")]
    assert [e["text"] for e in spoken] == ["Boom, it was glasses. Say next round when you're ready."]
    assert spoken[0]["kind"] == "speak"  # said word for word, not improvised


def test_screen_waits_for_pips_announcement_and_next_round_waits_too():
    """Live replay (Nov 27, deployed): the screen said "the word was chair" while Pip was still saying
    "...is it a chair?", and the player's reaction cut Pip off."""
    g = game.new_game(T0, words=["chair", "heart", "moon", "fish", "cup", "key"])
    game.start_round(g, T0)
    line = "Hmm, this, this, this... is it a chair?"
    fx = game.handle_pal_speech(g, line, T0 + 10)
    game.route_effects(g, fx, T0 + 10.2)  # Pip still talking: the "Boom" line is held
    view = game.public_view(g, T0 + 10.5)
    assert view["state"] == "REVEAL" and view["reveal_ready"] is False
    assert game.handle_user_speech(g, "yes! next round", T0 + 11) == [] and g.state == "REVEAL"  # ignored for now
    try:
        game.start_round(g, T0 + 11)
        raise AssertionError("start_round should wait for the announcement")
    except game.GameError:
        pass
    out = game.route_effects(g, [], T0 + 10 + game.speaking_time(line) + 0.1)  # Pip finished: announce
    assert [e["text"] for e in out if e["kind"] == "speak"][0].startswith("Boom, it was chair.")
    assert game.public_view(g, T0 + 14)["reveal_ready"] is True
    game.handle_user_speech(g, "next round", T0 + 16)
    assert g.state == "PAL_DRAW"
