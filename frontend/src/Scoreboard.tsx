import { motion } from "framer-motion";
import { GameView } from "./api";

const REPO_URL = (import.meta.env.VITE_REPO_URL as string | undefined) || "https://github.com/Suvoo/No-Way-Pictionary";

// Final screen, in two parts so the video stage can stay up for Pip's goodbye:
//   ScoreHeadline: final score + buttons (sits in the rail next to the video)
//   ScoreDetails:  all 6 words and who scored each round. The full guess log (audit trail) is not
//                  shown to players; it stays in the API (GET /api/games/{id}/scoreboard) and the database.

export function ScoreHeadline({ view, pal, onPlayAgain, onHome }: { view: GameView; pal: string; onPlayAgain: () => void; onHome: () => void }) {
  const { user, pal: p } = view.score;
  const headline = user === p ? `It's a tie, ${user} to ${p}!` : user > p ? "You win! 🏆" : `${pal} wins this time.`;
  return (
    <div className="space-y-4">
      <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="sketch bg-marker p-6 text-center">
        <p className="text-sm font-bold tracking-wide uppercase">Final score</p>
        <p className="font-marker mt-1 text-4xl whitespace-nowrap xl:text-5xl">
          You {user} : {p} {pal}
        </p>
        <p className="mt-2 text-xl font-bold">{headline}</p>
      </motion.div>
      <div className="grid gap-3">
        <button onClick={onPlayAgain} className="sketch-btn bg-mint px-6 py-3 text-lg font-extrabold text-white">
          Play again
        </button>
        <div className="grid grid-cols-2 gap-3">
          <a href={REPO_URL} target="_blank" rel="noreferrer" className="sketch-btn bg-white px-4 py-2.5 text-center font-bold">
            See how it works
          </a>
          <button onClick={onHome} className="sketch-btn bg-white px-4 py-2.5 font-bold">
            Home
          </button>
        </div>
      </div>
    </div>
  );
}

export function ScoreDetails({ view, pal }: { view: GameView; pal: string }) {
  return (
    <div className="space-y-5">
      <div className="sketch overflow-x-auto bg-white p-4">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b-2 border-ink">
              <th className="py-2 pr-3">Round</th>
              <th className="pr-3">Drawer</th>
              <th className="pr-3">Word</th>
              <th className="pr-3">Guesses</th>
              <th className="pr-3">Point to</th>
              <th>How</th>
            </tr>
          </thead>
          <tbody>
            {view.history.map((r) => (
              <tr key={r.index} className="border-b border-ink/15">
                <td className="py-2 pr-3 font-bold">{r.index}</td>
                <td className="pr-3">{r.drawer === "user" ? "You (paper)" : `${pal} (canvas)`}</td>
                <td className="font-marker pr-3 text-lg">{r.word}</td>
                <td className="pr-3">{r.guesses_used}</td>
                <td className="pr-3 font-semibold">{r.winner === "user" ? "You" : r.winner === "pal" ? pal : "-"}</td>
                <td className="text-ink-soft">{r.end_reason?.replace(/_/g, " ")}{r.flags.length ? ` · ${r.flags.join(", ")}` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

    </div>
  );
}
