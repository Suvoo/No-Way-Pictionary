import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";

const REPO_URL = (import.meta.env.VITE_REPO_URL as string | undefined) || "";

const THINK_ALOUD = ["Two circles...", "Is that a car?", "Wait. Thin wheels, a frame...", "It's a bicycle!"];

function ThinkAloud() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % THINK_ALOUD.length), 1700);
    return () => clearInterval(t);
  }, []);
  const last = i === THINK_ALOUD.length - 1;
  return (
    <div className="relative inline-block" aria-hidden>
      <div className={`sketch min-w-[15rem] bg-white px-5 py-3 text-lg font-semibold ${last ? "bg-marker" : ""}`}>
        <AnimatePresence mode="wait">
          <motion.span
            key={i}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.25 }}
            className="block"
          >
            {THINK_ALOUD[i]}
          </motion.span>
        </AnimatePresence>
      </div>
      <svg className="absolute -bottom-4 left-8" width="28" height="20" viewBox="0 0 28 20">
        <path d="M2 0 L10 18 L22 0" fill="white" stroke="#161412" strokeWidth="3" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

const STEPS = [
  {
    n: "1",
    title: "You draw.",
    body: "You get a secret word. Draw it on paper and hold it up. The AI watches through your camera and guesses out loud.",
    color: "bg-marker",
  },
  {
    n: "2",
    title: "It draws.",
    body: "It gets a secret word you do not know. It sketches it one line at a time on the canvas next to its video. You shout your guess.",
    color: "bg-sky text-white",
  },
  {
    n: "3",
    title: "You take turns.",
    body: "6 rounds, 45 seconds each, 3 guesses per round. Guess it and you win the round. Stump them and you win it. Reveal after every round.",
    color: "bg-tomato text-white",
  },
];

const OTHERS = [
  { name: "Google Quick, Draw!", what: "You draw, a silent classifier guesses. No face, no voice, and you never get to guess." },
  { name: "Mattel Pictionary Vs. AI", what: "You draw, an AI guesses through a camera. Still one-sided. Nobody draws back." },
  { name: "Canvas \"Pictionary vs. AI\" games", what: "You draw on a screen, the AI guesses live. It never draws for you." },
  { name: "Chat and voice characters", what: "Someone to talk to, but no video, no shared canvas, no game." },
];

const WHY = [
  {
    title: "Turn-based, not one-sided.",
    body: "You draw 3 rounds, it draws 3 rounds. Both sides keep a secret and both sides guess. That is what makes it a game, not a demo.",
  },
  {
    title: "A companion, not a classifier.",
    body: "A live video human talks while it plays. It commits to a wrong guess, laughs, changes its mind when you add a line, and reacts when you get it.",
  },
  {
    title: "The camera and the canvas are the game.",
    body: "In your rounds it has to see your real paper. In its rounds it draws on the canvas with a tool it calls. Take away the video and there is no game.",
  },
];

export default function Landing({ onPlay, starting, error }: { onPlay: () => void; starting: boolean; error: string | null }) {
  return (
    <div className="mx-auto max-w-5xl px-4 pb-16 sm:px-6">
      {/* Hero */}
      <header className="pt-10 pb-12 text-center sm:pt-16">
        <p className="mb-4 inline-block rotate-[-2deg] rounded-full border-2 border-ink bg-white px-3 py-1 text-xs font-bold tracking-wider uppercase">
          Reverse Pictionary
        </p>
        <h1 className="font-marker text-5xl leading-[1.05] sm:text-7xl">
          You vs the <span className="highlight px-1">AI</span>
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-xl font-semibold sm:text-2xl">You draw, it guesses. It draws, you guess.</p>
        <p className="mx-auto mt-2 max-w-xl text-ink-soft">
          A live video human plays Pictionary with you, turn by turn. Nothing to install, no login.
        </p>

        <div className="mt-8">
          <ThinkAloud />
        </div>

        <div className="mt-12 flex flex-col items-center gap-3">
          <button
            onClick={onPlay}
            disabled={starting}
            className="sketch-btn bg-mint px-8 py-4 text-xl font-extrabold text-white sm:text-2xl"
          >
            {starting ? "Starting the call..." : "Play: 6 rounds, about 6 minutes"}
          </button>
          <p className="text-sm text-ink-soft">Grab paper and a thick black pen. Allow camera and mic when asked.</p>
          {error && <p className="sketch max-w-md bg-white px-4 py-2 text-sm font-semibold text-tomato">{error}</p>}
        </div>
      </header>

      {/* How it works */}
      <section className="py-8">
        <h2 className="font-marker mb-6 text-center text-3xl">How it works</h2>
        <div className="grid gap-5 sm:grid-cols-3">
          {STEPS.map((s, i) => (
            <motion.div
              key={s.n}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.08 }}
              className="sketch bg-white p-5"
            >
              <div className={`sketch-btn mb-3 flex h-11 w-11 items-center justify-center text-xl font-extrabold ${s.color}`}>{s.n}</div>
              <h3 className="text-xl font-extrabold">{s.title}</h3>
              <p className="mt-1 text-ink-soft">{s.body}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Why it's different */}
      <section className="py-10">
        <h2 className="font-marker mb-2 text-center text-3xl">Why this is not like other Pictionary games</h2>
        <p className="mb-8 text-center text-ink-soft">Today's drawing games are one-sided, and most are not a companion at all.</p>
        <div className="grid gap-8 lg:grid-cols-2">
          <ul className="space-y-3">
            {OTHERS.map((o) => (
              <li key={o.name} className="rounded-xl border-2 border-dashed border-ink/40 bg-paper-dark/60 px-4 py-3">
                <span className="font-bold">{o.name}.</span> <span className="text-ink-soft">{o.what}</span>
              </li>
            ))}
          </ul>
          <div className="sketch space-y-4 bg-white p-5">
            <p className="font-marker text-xl">This one is different:</p>
            {WHY.map((w, i) => (
              <div key={w.title} className="flex gap-3">
                <span className="font-marker text-2xl text-sky">{i + 1}</span>
                <p>
                  <span className="font-bold">{w.title}</span> <span className="text-ink-soft">{w.body}</span>
                </p>
              </div>
            ))}
          </div>
        </div>
        <p className="mt-6 text-center text-sm text-ink-soft">
          Built with Tavus CVI: a live video human, not a chatbot. Word bank from Google's Quick, Draw! dataset (345
          categories, 50 million sketches), curated to 28 easy words for v1.
        </p>
      </section>

      {/* Before you press Play */}
      <section className="py-8">
        <div className="sketch mx-auto max-w-2xl bg-marker/70 p-6">
          <h2 className="font-marker mb-3 text-2xl">Before you press Play</h2>
          <ul className="space-y-2 font-medium">
            <li>✏️ Grab paper and a thick black pen. Pencil is too faint.</li>
            <li>📄 Draw big. Hold it up steady for 3 seconds, close to the camera, in good light.</li>
            <li>🚫 Draw only, do not write the word. Writing the word is cheating, and it will call you out.</li>
            <li>🎤 Allow camera and mic. No login, no account.</li>
            <li>⏱️ One game is 6 rounds, about 6 minutes.</li>
          </ul>
          <button onClick={onPlay} disabled={starting} className="sketch-btn mt-5 w-full bg-mint px-6 py-3 text-lg font-extrabold text-white">
            {starting ? "Starting the call..." : "I have my pen. Play!"}
          </button>
        </div>
      </section>

      <footer className="pt-10 text-center text-sm text-ink-soft">
        Built by Suvodeep Sinha as a Tavus take-home.{" "}
        {REPO_URL ? (
          <a className="font-semibold underline" href={REPO_URL} target="_blank" rel="noreferrer">
            How it works: README on GitHub
          </a>
        ) : (
          <span>How it works: see the README in the repo.</span>
        )}
      </footer>
    </div>
  );
}
