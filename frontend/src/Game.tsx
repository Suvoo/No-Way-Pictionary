import { motion } from "framer-motion";
import { FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { Api, GameView, NewGame } from "./api";
import Canvas from "./Canvas";
import CviEmbed, { Caption } from "./CviEmbed";
import { ScoreDetails, ScoreHeadline } from "./Scoreboard";

// The game page. It renders whatever state the backend says; it owns no game rules.
// Canvas is shown ONLY in PAL-draw rounds (and their reveal); in your rounds you draw on paper.

type Props = { api: Api; info: NewGame; onPlayAgain: () => void; onHome: () => void; onLost: () => void };

export default function Game({ api, info, onPlayAgain, onHome, onLost }: Props) {
  const [view, setView] = useState<GameView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [captions, setCaptions] = useState<{ user?: Caption; pal?: Caption }>({});
  const pal = info.pal_name;
  const live = info.mode === "live" && !!info.conversation_url;

  const refresh = useCallback(
    () =>
      api
        .get()
        .then(setView)
        .catch((e) => {
          const msg = String(e?.message ?? e);
          if (/not found|token/i.test(msg)) onLost(); // game no longer exists (e.g. server redeployed)
          else setError(msg);
        }),
    [api, onLost],
  );

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 1000);
    return () => clearInterval(t);
  }, [refresh]);

  async function act<T>(fn: () => Promise<T>) {
    setBusy(true);
    setError(null);
    try {
      const r = await fn();
      // Only a game view (it has "round") replaces the view; other replies (e.g. the scoreboard) just refresh.
      if (r && typeof r === "object" && "round" in (r as object)) setView(r as unknown as GameView);
      else await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const onRelay = useCallback(
    (event: unknown) => {
      api.relay(event).then(() => refresh()).catch(() => undefined);
    },
    [api, refresh],
  );
  const onCaption = useCallback((c: Caption) => setCaptions((prev) => ({ ...prev, [c.role]: c })), []);

  if (!view) {
    return <div className="flex min-h-screen items-center justify-center font-marker text-2xl">Setting up the table...</div>;
  }

  const r = view.round;
  // The round is decided but Pip is still finishing the sentence that decided it: the screen waits,
  // so the reveal lands with Pip's "Boom, it was ..." instead of spoiling it.
  const announcing = (view.state === "REVEAL" || view.state === "GAME_OVER") && view.reveal_ready === false;
  const over = view.state === "GAME_OVER" && !announcing;
  const showCanvas = r.drawer === "pal" && (view.state === "PAL_DRAW" || (view.state === "REVEAL" && r.strokes.length > 0));

  // Layout A: the live video is the stage (two thirds), the round's controls sit in a slim rail.
  // The stage stays mounted through GAME_OVER so the player hears Pip's goodbye.
  return (
    <div className="mx-auto max-w-7xl px-4 pt-4 pb-10 sm:px-6">
      <TopBar view={view} pal={pal} onQuit={onHome} />

      {error && <p className="sketch mt-3 bg-white px-4 py-2 text-sm font-semibold text-tomato">{error}</p>}

      <div className="mt-4 grid items-start gap-5 lg:grid-cols-[minmax(0,2.1fr)_minmax(0,1fr)]">
        {/* Stage: top on mobile, left on desktop */}
        <div className="min-w-0">
          {/* 4:3 on phones so Pip's canvas still fits on screen below it; 16:10 from tablet up */}
          <div className="sketch aspect-[4/3] w-full overflow-hidden bg-ink sm:aspect-[16/10]">
            {live ? (
              <CviEmbed
                url={info.conversation_url!}
                palName={pal}
                onRelay={onRelay}
                onCaption={onCaption}
                caption={captions.pal}
                gameOver={over}
              />
            ) : (
              <DemoVideo pal={pal} />
            )}
          </div>
          {captions.user && !over && (
            <p className="mt-2 text-sm text-ink-soft" aria-live="polite">
              <span className="font-bold">You:</span> {captions.user.text}
            </p>
          )}
        </div>

        {/* Rail: what this round needs */}
        <div className="min-w-0">
          {over ? (
            <ScoreHeadline view={view} pal={pal} onPlayAgain={onPlayAgain} onHome={onHome} />
          ) : (
            /* Keyed fade-in per state. No exit animation: AnimatePresence "wait" can stall
               while the 1s poll re-renders, leaving the old panel on screen. */
            <motion.div
                key={`${view.state}-${r.index}`}
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2 }}
                className="space-y-4"
              >
                {view.state === "ROUND_START" && (
                  <Card>
                    <h2 className="font-marker text-3xl">Round 1 is yours.</h2>
                    <p className="mt-2 text-ink-soft">
                      You draw first, {pal} guesses. {live ? `Wait until ${pal} has said hi, then` : "When you are ready,"} press Start. You will get your secret word and 45 seconds.
                    </p>
                    <BigButton onClick={() => act(api.startRound)} disabled={busy} color="bg-mint text-white">
                      Start round 1
                    </BigButton>
                  </Card>
                )}

                {view.state === "USER_DRAW" && (
                  <>
                    {r.notice && (
                      <motion.p
                        key={r.your_word ?? ""}
                        initial={{ scale: 0.9, rotate: -2 }}
                        animate={{ scale: 1, rotate: 0 }}
                        className="sketch bg-tomato px-4 py-3 font-bold text-white"
                        role="alert"
                      >
                        🙊 {r.notice}
                      </motion.p>
                    )}
                    <Card className="bg-marker">
                      <p className="text-sm font-bold tracking-wide uppercase">Your secret word</p>
                      <p className="font-marker mt-1 text-5xl leading-tight break-words">{r.your_word}</p>
                      <p className="mt-2 text-sm font-semibold">{pal} cannot see this. Draw it on paper, big and simple. No letters!</p>
                    </Card>
                    <Card>
                      <p className="font-semibold">Hold your paper up to the camera, steady, for 3 seconds.</p>
                      <BigButton onClick={() => act(api.look)} disabled={busy} color="bg-sky text-white">
                        👀 Look now
                      </BigButton>
                      <p className="mt-2 text-xs text-ink-soft">
                        {pal} watches your camera the whole time. "Look now" just tells it your drawing is up, so it guesses right away.
                      </p>
                    </Card>
                    <PalGuesses view={view} pal={pal} />
                    {view.mock && <DemoPalInput pal={pal} onSubmit={(t) => act(() => api.guess(t, "pal"))} />}
                  </>
                )}

                {showCanvas && (
                  <div className="mx-auto w-full max-w-[260px] sm:max-w-[300px] lg:max-w-none">
                    <Canvas strokes={r.strokes} />
                  </div>
                )}

                {view.state === "PAL_DRAW" && (
                  <Card>
                    <p className="font-marker text-2xl">Your turn to guess!</p>
                    <p className="text-ink-soft">{pal} has a word. You do not. Shout your guess out loud.</p>
                    <WrongGuesses words={r.wrong_guesses} />
                    {r.hint && <p className="mt-3 rounded-lg bg-marker/60 px-3 py-2 font-semibold">💡 Hint: {r.hint}</p>}
                    <TypedGuess disabled={busy} onSubmit={(t) => act(() => api.guess(t))} />
                    <div className="mt-3 flex flex-wrap gap-2">
                      <SmallButton onClick={() => act(api.nextStroke)} disabled={busy}>✏️ Draw more</SmallButton>
                      {r.can_hint && <SmallButton onClick={() => act(api.hint)} disabled={busy}>💡 Hint</SmallButton>}
                    </div>
                  </Card>
                )}

                {announcing && <Checking drawer={r.drawer} pal={pal} />}
                {view.state === "REVEAL" && !announcing && <Reveal view={view} pal={pal} busy={busy} onNext={() => act(api.startRound)} />}
            </motion.div>
          )}
        </div>
      </div>

      {over && (
        <div className="mt-6">
          <ScoreDetails view={view} pal={pal} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- pieces

// Quit asks first: one tap by mistake would end the game and the video call.
function QuitButton({ onQuit }: { onQuit: () => void }) {
  const [asking, setAsking] = useState(false);
  if (!asking)
    return (
      <button onClick={() => setAsking(true)} className="text-xs font-semibold text-ink-soft underline">
        Quit
      </button>
    );
  return (
    <span role="alertdialog" aria-label="Confirm quit" className="flex items-center gap-2 text-xs font-semibold">
      Are you sure you want to quit?
      <button onClick={onQuit} className="sketch-btn bg-tomato px-2 py-1 text-white">
        Yes, quit
      </button>
      <button onClick={() => setAsking(false)} className="sketch-btn bg-white px-2 py-1">
        No
      </button>
    </span>
  );
}

function TopBar({ view, pal, onQuit }: { view: GameView; pal: string; onQuit: () => void }) {
  const r = view.round;
  const active = view.state === "USER_DRAW" || view.state === "PAL_DRAW";
  const low = active && r.seconds_left <= 10;
  return (
    <div className="sketch flex flex-wrap items-center justify-between gap-3 bg-white px-4 py-3">
      <div className="flex items-center gap-4">
        <ScorePill label="You" value={view.score.user} color="bg-marker" />
        <span className="font-marker text-xl">vs</span>
        <ScorePill label={pal} value={view.score.pal} color="bg-sky text-white" />
      </div>
      <div className="flex items-center gap-4 text-sm font-bold">
        <span>
          Round {r.index} of {view.rounds}
          {active && <span className="ml-1 font-medium text-ink-soft">· {r.drawer === "user" ? "you draw" : `${pal} draws`}</span>}
        </span>
        {active && (
          <>
            <span className={`font-marker text-2xl tabular-nums ${low ? "text-tomato" : ""}`}>
              0:{String(r.seconds_left).padStart(2, "0")}
            </span>
            <span className="flex gap-1" aria-label={`${r.guesses_left} guesses left`}>
              {Array.from({ length: view.max_guesses }).map((_, i) => (
                <span key={i} className={`h-3 w-3 rounded-full border-2 border-ink ${i < r.guesses_left ? "bg-mint" : "bg-transparent"}`} />
              ))}
            </span>
          </>
        )}
        {view.state !== "GAME_OVER" && <QuitButton onQuit={onQuit} />}
      </div>
    </div>
  );
}

function ScorePill({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className={`sketch-btn flex items-center gap-2 px-3 py-1 ${color}`}>
      <span className="text-sm font-bold">{label}</span>
      <motion.span key={value} initial={{ scale: 1.6 }} animate={{ scale: 1 }} className="font-marker text-2xl">
        {value}
      </motion.span>
    </div>
  );
}

function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  const bg = /\bbg-/.test(className) ? "" : "bg-white";
  return <div className={`sketch p-5 ${bg} ${className}`}>{children}</div>;
}

function BigButton({ children, onClick, disabled, color }: { children: ReactNode; onClick: () => void; disabled?: boolean; color: string }) {
  return (
    <button onClick={onClick} disabled={disabled} className={`sketch-btn mt-4 w-full px-5 py-3 text-lg font-extrabold ${color}`}>
      {children}
    </button>
  );
}

function SmallButton({ children, onClick, disabled }: { children: ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled} className="sketch-btn bg-white px-3 py-1.5 text-sm font-bold">
      {children}
    </button>
  );
}

function WrongGuesses({ words }: { words: string[] }) {
  if (!words.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {words.map((w) => (
        <span key={w} className="rounded-full border-2 border-tomato px-3 py-0.5 text-sm font-semibold text-tomato line-through">
          {w}
        </span>
      ))}
    </div>
  );
}

function PalGuesses({ view, pal }: { view: GameView; pal: string }) {
  // Only Pip's real guesses (the word, right or wrong). "Hold it closer", repeats and the referee's
  // notes stay in the audit log, not on screen.
  const mine = view.guess_log.filter((g) => g.round === view.round.index && g.guesser === "pal" && g.counted && g.guess);
  return (
    <Card>
      <p className="text-sm font-bold tracking-wide uppercase">{pal}'s guesses</p>
      {mine.length === 0 ? (
        <p className="mt-1 text-ink-soft">Waiting for {pal} to guess...</p>
      ) : (
        <ul className="mt-2 space-y-1">
          {mine.map((g, i) => (
            <li key={i} className="flex items-center gap-2 text-lg">
              <span>{g.correct ? "✅" : "❌"}</span>
              <span className="font-semibold">{g.guess}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function TypedGuess({ onSubmit, disabled }: { onSubmit: (t: string) => void; disabled?: boolean }) {
  const [text, setText] = useState("");
  function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    onSubmit(text.trim());
    setText("");
  }
  return (
    <form onSubmit={submit} className="mt-4 flex gap-2">
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Noisy room? Type your guess"
        className="min-w-0 flex-1 rounded-xl border-2 border-ink bg-paper px-3 py-2 outline-none focus:bg-white"
      />
      <button disabled={disabled} className="sketch-btn bg-marker px-4 py-2 font-bold">
        Guess
      </button>
    </form>
  );
}

function DemoPalInput({ pal, onSubmit }: { pal: string; onSubmit: (t: string) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <form
      className="rounded-xl border-2 border-dashed border-ink/50 bg-paper-dark/60 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        const v = ref.current?.value.trim();
        if (v) onSubmit(v);
        if (ref.current) ref.current.value = "";
      }}
    >
      <p className="text-sm font-bold">Demo mode: type what {pal} would say</p>
      <p className="text-xs text-ink-soft">No Tavus key is configured, so there is no live video. Try "Is it a car?" or just "car".</p>
      <div className="mt-2 flex gap-2">
        <input ref={ref} className="min-w-0 flex-1 rounded-xl border-2 border-ink bg-white px-3 py-2" placeholder={`${pal} says...`} />
        <button className="sketch-btn bg-white px-3 py-2 text-sm font-bold">Send</button>
      </div>
    </form>
  );
}

function Checking({ drawer, pal }: { drawer: "user" | "pal"; pal: string }) {
  return (
    <Card>
      <p className="font-marker text-2xl">🥁 {drawer === "user" ? `Checking ${pal}'s guess...` : "Checking your guess..."}</p>
      <p className="mt-1 text-ink-soft">{pal} is about to tell you.</p>
    </Card>
  );
}

function Reveal({ view, pal, busy, onNext }: { view: GameView; pal: string; busy: boolean; onNext: () => void }) {
  const r = view.round;
  const youWon = r.winner === "user";
  const reason =
    r.end_reason === "correct"
      ? r.drawer === "user" ? `${pal} guessed your drawing.` : "You guessed it!"
      : r.end_reason === "gave_away" ? "You gave your word away again."
      : r.end_reason === "timeout" ? "Time ran out." : "No guesses left.";
  return (
    <Card className={youWon ? "bg-mint/20" : r.winner === "pal" ? "bg-sky/10" : "bg-white"}>
      <p className="text-sm font-bold tracking-wide uppercase">Round {r.index} reveal</p>
      <p className="mt-1">The word was</p>
      <motion.p initial={{ scale: 0.6, rotate: -4 }} animate={{ scale: 1, rotate: 0 }} className="font-marker text-5xl">
        {r.revealed_word}
      </motion.p>
      <p className="mt-3 text-lg font-bold">
        {reason} {r.winner === "user" ? "Point to you! 🎉" : r.winner === "pal" ? `Point to ${pal}.` : "No point this round."}
      </p>
      {r.flags.length > 0 && <p className="mt-1 text-sm text-ink-soft">Referee note: {r.flags.join(", ")}.</p>}
      <BigButton onClick={onNext} disabled={busy} color="bg-mint text-white">
        Next round: {r.index + 1 <= view.rounds && (r.index + 1) % 2 === 1 ? "you draw" : `${pal} draws`}
      </BigButton>
    </Card>
  );
}

function DemoVideo({ pal }: { pal: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 bg-gradient-to-br from-sky to-ink p-6 text-center text-white">
      <div className="sketch flex h-20 w-20 items-center justify-center bg-marker text-4xl">🤖</div>
      <p className="font-marker text-2xl">{pal} (demo mode)</p>
      <p className="max-w-xs text-sm text-white/80">
        No Tavus key on this server, so there is no live video. The game, referee and scoring all run for real. Set TAVUS_API_KEY and TAVUS_PAL_ID to play live.
      </p>
    </div>
  );
}
