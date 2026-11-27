import { motion } from "framer-motion";
import { useEffect, useState } from "react";

const REPO_URL = (import.meta.env.VITE_REPO_URL as string | undefined) || "https://github.com/Suvoo/No-Way-Pictionary";

// Pip's think-aloud, cycling in the storyboard's video frame. Ends on the name joke.
const THINK_ALOUD = ["Two circles...", "Is that a car with ten wheels?", "Wait. A frame, a seat...", "No way. It's a bicycle!"];

function ThinkAloudCaption() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % THINK_ALOUD.length), 1800);
    return () => clearInterval(t);
  }, []);
  const last = i === THINK_ALOUD.length - 1;
  return (
    <span className={`absolute inset-x-2 bottom-2 rounded-lg px-2 py-1.5 text-center text-[13px] ${last ? "bg-marker text-ink" : "bg-black/70 text-white"}`}>
      <b className={last ? "" : "text-marker"}>Pip:</b>{" "}
      <motion.span key={i} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }} className="inline-block">
        {THINK_ALOUD[i]}
      </motion.span>
    </span>
  );
}

const INK = { stroke: "#161412", strokeWidth: 3.2, fill: "none", strokeLinecap: "round", strokeLinejoin: "round" } as const;

function BikeDoodle() {
  return (
    <svg viewBox="0 0 120 80" className="w-[74%]" role="img" aria-label="A hand-drawn bicycle on paper">
      <circle cx="28" cy="52" r="18" {...INK} />
      <circle cx="92" cy="52" r="18" {...INK} />
      <path d="M28 52 L52 52 L76 26 L46 26 L28 52 M46 26 L52 52 M76 26 L92 52 M72 18 L76 26 M66 16 L80 19 M40 22 L54 22" {...INK} />
    </svg>
  );
}

function BirdDoodle() {
  return (
    <svg viewBox="0 0 100 80" className="w-[58%]" role="img" aria-label="Pip's canvas sketch of a bird">
      <path d="M24 48 a22 15 0 1 0 44 0 a22 15 0 1 0 -44 0" {...INK} />
      <circle cx="70" cy="30" r="9" {...INK} />
      <path d="M78 27 L90 31 L78 35 M30 42 Q42 30 56 44" {...INK} />
    </svg>
  );
}

function PipSilhouette() {
  return (
    <svg viewBox="0 0 200 220" className="absolute bottom-0 left-1/2 h-[92%] -translate-x-1/2" aria-hidden>
      <ellipse cx="100" cy="230" rx="92" ry="70" fill="#3b4a6b" />
      <rect x="86" y="140" width="28" height="30" rx="10" fill="#d9a77f" />
      <ellipse cx="100" cy="98" rx="50" ry="58" fill="#e8b994" />
      <path d="M50 92c0-40 24-62 52-62s50 22 50 60c-10-18-30-26-52-26s-40 10-50 28z" fill="#2a1d16" />
      <circle cx="81" cy="100" r="5" fill="#161412" />
      <circle cx="119" cy="100" r="5" fill="#161412" />
      <path d="M84 126c8 8 24 8 32 0" stroke="#7a3b2c" strokeWidth="4" fill="none" strokeLinecap="round" />
    </svg>
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
    body: "6 rounds, 45 seconds each, 3 guesses per round. Guess it right and you score a point. Miss it and nobody does. Reveal after every round.",
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
      {/* Hero: storyboard. Name + Play, then three frames of one round. */}
      <header className="pt-10 pb-10 sm:pt-14">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="grid gap-3">
            <p className="inline-block w-fit rotate-[-2deg] rounded-full border-2 border-ink bg-white px-3 py-1 text-xs font-bold tracking-wider uppercase">
              A live video game
            </p>
            <h1 className="font-marker text-5xl leading-[1] sm:text-7xl">
              Doodle with <span className="highlight px-1">Pip</span>
            </h1>
            <p className="max-w-xl text-xl font-semibold sm:text-2xl">Pip guesses your doodles out loud. Then you guess Pip's.</p>
          </div>
          <div className="grid justify-items-start gap-2">
            <button onClick={onPlay} disabled={starting} className="sketch-btn bg-mint px-7 py-4 text-xl font-extrabold text-white">
              {starting ? "Starting the call..." : "Play: 6 rounds, about 6 minutes"}
            </button>
            <p className="text-sm text-ink-soft">Grab paper and a thick black pen. Allow camera and mic when asked.</p>
            {error && <p className="sketch max-w-md bg-white px-4 py-2 text-sm font-semibold text-tomato">{error}</p>}
          </div>
        </div>

        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          <div className="sketch grid content-start gap-2.5 bg-white p-3.5">
            <div className="flex aspect-[4/3] items-center justify-center rounded-[10px] border-2 border-ink bg-white">
              <BikeDoodle />
            </div>
            <p className="text-sm font-semibold">1. You draw on real paper and hold it up.</p>
          </div>
          <div className="sketch grid content-start gap-2.5 bg-white p-3.5">
            <div className="relative aspect-[4/3] overflow-hidden rounded-[10px] border-2 border-ink bg-[radial-gradient(120%_90%_at_50%_30%,#1d2a44,#0f1626)]">
              <PipSilhouette />
              <ThinkAloudCaption />
            </div>
            <p className="text-sm font-semibold">2. Pip guesses out loud, then draws back on a canvas.</p>
          </div>
          <div className="sketch grid content-start gap-2.5 bg-white p-3.5">
            <div className="flex aspect-[4/3] flex-col items-center justify-center gap-1 rounded-[10px] border-2 border-ink bg-white">
              <span className="font-marker text-3xl">You 3 : 2 Pip</span>
              <BirdDoodle />
            </div>
            <p className="text-sm font-semibold">3. Six rounds. Guess it right, get the point.</p>
          </div>
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
