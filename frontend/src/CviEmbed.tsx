import DailyIframe, { DailyCall } from "@daily-co/daily-js";
import { useEffect, useRef, useState } from "react";

// The video stage. Joins the Tavus conversation (a Daily room) with a Daily *call object* and
// draws the tracks ourselves: Pip's video fills the stage, your camera is a small corner preview
// (so you can aim your paper). No stock call UI, no "Are you ready to join?" screen.
//
// It also relays what Pip and the player say, plus Pip's tool calls, to the backend referee.
// Tavus sends these ONLY to the browser over the Daily data channel (verified in the Tavus
// OpenAPI spec), so the browser is the relay.

export type Caption = { role: "user" | "pal"; text: string; at: number };

type Props = {
  url: string;
  palName: string;
  onRelay: (event: unknown) => void; // POST to /api/games/{id}/events
  onCaption: (c: Caption) => void;
  caption?: Caption; // latest Pip line, shown on the video
  gameOver?: boolean;
  selfViewSize?: "sm" | "md";
};

type Status = "joining" | "joined" | "left" | "error" | "camera-blocked";
const RELAYED = new Set(["conversation.utterance", "conversation.tool_call"]);

function playable(t?: { state?: string; persistentTrack?: MediaStreamTrack }): MediaStreamTrack | null {
  return t && t.state === "playable" && t.persistentTrack ? t.persistentTrack : null;
}

function TrackVideo({ track, mirror, className }: { track: MediaStreamTrack | null; mirror?: boolean; className: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.srcObject = track ? new MediaStream([track]) : null;
  }, [track]);
  return <video ref={ref} autoPlay playsInline muted className={className} style={mirror ? { transform: "scaleX(-1)" } : undefined} />;
}

function TrackAudio({ track }: { track: MediaStreamTrack | null }) {
  const ref = useRef<HTMLAudioElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    ref.current.srcObject = track ? new MediaStream([track]) : null;
    if (track) ref.current.play().catch(() => undefined);
  }, [track]);
  return <audio ref={ref} autoPlay />;
}

export default function CviEmbed({ url, palName, onRelay, onCaption, caption, gameOver, selfViewSize = "sm" }: Props) {
  const [status, setStatus] = useState<Status>("joining");
  const [attempt, setAttempt] = useState(0);
  const [palVideo, setPalVideo] = useState<MediaStreamTrack | null>(null);
  const [palAudio, setPalAudio] = useState<MediaStreamTrack | null>(null);
  const [selfVideo, setSelfVideo] = useState<MediaStreamTrack | null>(null);
  const relayRef = useRef(onRelay);
  const captionRef = useRef(onCaption);
  relayRef.current = onRelay;
  captionRef.current = onCaption;

  useEffect(() => {
    DailyIframe.getCallInstance()?.destroy();
    const call: DailyCall = DailyIframe.createCallObject({ subscribeToTracksAutomatically: true });
    setStatus("joining");

    const sync = () => {
      const ps = call.participants();
      const remote = Object.values(ps).find((p) => !p.local);
      setSelfVideo(playable(ps.local?.tracks?.video));
      setPalVideo(playable(remote?.tracks?.video));
      setPalAudio(playable(remote?.tracks?.audio));
    };

    call.on("app-message", (ev) => {
      const data = ev?.data as { message_type?: string; event_type?: string; properties?: { role?: string; speech?: string } };
      if (!data || data.message_type !== "conversation" || !data.event_type || !RELAYED.has(data.event_type)) return;
      if (data.event_type === "conversation.utterance") {
        const role = data.properties?.role;
        if (role === "replica") return; // legacy duplicate of the "pal" utterance
        const text = data.properties?.speech ?? "";
        if ((role === "user" || role === "pal") && text && !text.startsWith("[game]")) {
          captionRef.current({ role, text, at: Date.now() });
        }
      }
      relayRef.current(data);
    });
    call.on("joined-meeting", () => { setStatus("joined"); sync(); });
    call.on("participant-joined", sync);
    call.on("participant-updated", sync);
    call.on("participant-left", sync);
    call.on("track-started", sync);
    call.on("track-stopped", sync);
    call.on("left-meeting", () => setStatus("left"));
    call.on("camera-error", () => setStatus("camera-blocked"));
    call.on("error", () => setStatus("error"));

    call.join({ url }).catch(() => setStatus("error"));
    return () => {
      call.leave().catch(() => undefined).finally(() => call.destroy());
    };
  }, [url, attempt]);

  const waitingForPal = status === "joined" && !palVideo;

  return (
    <div className="relative h-full w-full overflow-hidden bg-[radial-gradient(120%_90%_at_50%_30%,#1d2a44,#0f1626)]">
      <TrackVideo track={palVideo} className="absolute inset-0 h-full w-full object-cover" />
      <TrackAudio track={palAudio} />

      <span className="absolute top-3 left-3 flex items-center gap-1.5 rounded-full bg-black/55 px-2.5 py-1 text-xs font-bold text-white">
        <span className={`h-2 w-2 rounded-full ${palVideo ? "bg-tomato" : "bg-white/40"}`} />
        {palName} {palVideo ? "· live" : ""}
      </span>

      {caption && !gameOver && (
        <div className="absolute bottom-3 left-1/2 w-[min(86%,560px)] -translate-x-1/2 rounded-xl bg-black/65 px-3 py-2 text-center text-sm text-white sm:text-base" aria-live="polite">
          <span className="font-bold text-marker">{palName}:</span> {caption.text}
        </div>
      )}

      {/* Your camera: small corner preview to aim the paper */}
      <div
        className={`absolute top-3 right-3 aspect-[4/3] overflow-hidden rounded-xl border-[3px] border-white bg-ink shadow-lg ${
          selfViewSize === "md" ? "w-[30%] min-w-[110px]" : "w-[22%] min-w-[90px]"
        }`}
      >
        <TrackVideo track={selfVideo} mirror className="h-full w-full object-cover" />
        <span className="absolute bottom-1 left-1.5 rounded bg-black/50 px-1.5 text-[10px] font-bold text-white">You</span>
      </div>

      {(status === "joining" || waitingForPal) && (
        <Overlay>
          <p className="font-marker text-2xl">{status === "joining" ? "Connecting..." : `${palName} is joining...`}</p>
          <p className="text-sm text-white/80">Allow camera and mic if your browser asks.</p>
        </Overlay>
      )}
      {status === "camera-blocked" && (
        <Overlay>
          <p className="font-semibold">Your camera or mic is blocked.</p>
          <p className="text-sm text-white/80">Allow them in the address bar, then:</p>
          <OverlayButton onClick={() => setAttempt((a) => a + 1)}>Try again</OverlayButton>
        </Overlay>
      )}
      {(status === "left" || status === "error") && (
        <Overlay>
          {gameOver ? (
            <>
              <p className="font-marker text-2xl">Thanks for playing!</p>
              <p className="text-sm text-white/80">The call has ended.</p>
            </>
          ) : (
            <>
              <p className="font-semibold">{status === "error" ? "The video call dropped." : "You left the call."}</p>
              <p className="text-sm text-white/80">Your game and score are saved. Rejoin the same call:</p>
              <OverlayButton onClick={() => setAttempt((a) => a + 1)}>Reconnect</OverlayButton>
            </>
          )}
        </Overlay>
      )}
    </div>
  );
}

function Overlay({ children }: { children: React.ReactNode }) {
  return <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-ink/70 p-4 text-center text-white">{children}</div>;
}

function OverlayButton({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button className="sketch-btn bg-marker px-4 py-2 font-bold text-ink" onClick={onClick}>
      {children}
    </button>
  );
}
