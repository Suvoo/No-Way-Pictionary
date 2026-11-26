import { useCallback, useMemo, useState } from "react";
import { Api, NewGame } from "./api";
import Game from "./Game";
import Landing from "./Landing";

// One page, three views: landing -> game -> scoreboard (the scoreboard lives inside Game).
// The current game is remembered in sessionStorage so a page refresh resumes it
// (the backend has the state; this only remembers which game and its player token).

const KEY = "reverse-pictionary-session";

function loadSaved(): NewGame | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as NewGame) : null;
  } catch {
    return null;
  }
}

function save(info: NewGame | null) {
  try {
    if (info) sessionStorage.setItem(KEY, JSON.stringify(info));
    else sessionStorage.removeItem(KEY);
  } catch {
    /* private mode or blocked storage: refresh just won't resume */
  }
}

export default function App() {
  const [info, setInfo] = useState<NewGame | null>(loadSaved);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function play(previousGameId?: string) {
    setStarting(true);
    setError(null);
    try {
      const created = await Api.create(previousGameId);
      save(created);
      setInfo(created);
      window.scrollTo(0, 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  }

  const api = useMemo(() => (info ? new Api(info.game_id, info.player_token) : null), [info]);

  const home = useCallback(() => {
    save(null);
    setInfo(null);
  }, []);

  if (!info || !api) return <Landing onPlay={() => play()} starting={starting} error={error} />;
  return (
    <Game
      key={info.game_id}
      api={api}
      info={info}
      onPlayAgain={() => play(info.game_id)}
      onHome={home}
      onLost={home}
    />
  );
}
