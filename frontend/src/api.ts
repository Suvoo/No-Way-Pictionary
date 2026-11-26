// Thin client for the FastAPI backend. The Tavus API key never reaches the browser:
// the backend creates the conversation and returns only the Daily room URL.

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export type Shape =
  | { type: "line"; points: [number, number][] }
  | { type: "circle"; cx: number; cy: number; r: number }
  | { type: "ellipse"; cx: number; cy: number; rx: number; ry: number }
  | { type: "arc"; cx: number; cy: number; r: number; start: number; end: number };

export type GuessEntry = {
  round: number;
  guesser: "user" | "pal";
  text: string;
  guess: string | null;
  correct: boolean;
  counted: boolean;
  note: string;
  source: string;
  at: number;
};

export type RoundSummary = {
  index: number;
  drawer: "user" | "pal";
  word: string;
  winner: "user" | "pal" | null;
  end_reason: string | null;
  guesses_used: number;
  strokes_drawn: number;
  flags: string[];
};

export type GameState = "ROUND_START" | "USER_DRAW" | "PAL_DRAW" | "REVEAL" | "GAME_OVER";

export type GameView = {
  game_id: string;
  state: GameState;
  mock: boolean;
  conversation_url: string | null;
  conversation_id: string | null;
  rounds: number;
  round_seconds: number;
  max_guesses: number;
  score: { user: number; pal: number };
  round: {
    index: number;
    drawer: "user" | "pal";
    status: "pending" | "active" | "guessed" | "missed";
    seconds_left: number;
    guesses_left: number;
    wrong_guesses: string[];
    your_word: string | null;
    strokes: Shape[][];
    can_hint: boolean;
    hint: string | null;
    revealed_word: string | null;
    winner: "user" | "pal" | null;
    end_reason: string | null;
    flags: string[];
  };
  history: RoundSummary[];
  guess_log: GuessEntry[];
};

export type NewGame = {
  game_id: string;
  player_token: string;
  conversation_id: string | null;
  conversation_url: string | null;
  mode: "demo" | "live";
  pal_name: string;
};

export class Api {
  constructor(public gameId: string, private token: string) {}

  static async create(previousGameId?: string): Promise<NewGame> {
    const r = await fetch(`${BASE}/api/games`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ previous_game_id: previousGameId ?? null }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `Could not start a game (${r.status})`);
    return r.json();
  }

  private async call<T>(path: string, method = "POST", body?: unknown): Promise<T> {
    const r = await fetch(`${BASE}/api/games/${this.gameId}${path}`, {
      method,
      headers: { "Content-Type": "application/json", "X-Player-Token": this.token },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `Request failed (${r.status})`);
    return r.json();
  }

  get = () => this.call<GameView>("", "GET");
  startRound = () => this.call<GameView>("/start-round");
  look = () => this.call<{ ok: boolean }>("/look");
  hint = () => this.call<{ hint: string }>("/hint");
  nextStroke = () => this.call<GameView>("/next-stroke");
  guess = (text: string, guesser: "user" | "pal" = "user") => this.call<GameView>("/guesses", "POST", { text, guesser });
  complete = () => this.call<unknown>("/complete");
  // Relay a raw Tavus app-message (utterance / tool_call) for the backend referee.
  relay = (event: unknown) => this.call<unknown>("/events", "POST", event);
}
