import DailyIframe, { DailyCall } from "@daily-co/daily-js";
import { useEffect, useRef, useState } from "react";

// Joins the Tavus conversation (a Daily room) and relays what the PAL and player say, plus the
// PAL's tool calls, to the backend referee. Tavus sends these ONLY to the browser over the
// Daily data channel (verified in the Tavus OpenAPI spec), so the browser is the relay.

export type Caption = { role: "user" | "pal"; text: string; at: number };

type Props = {
  url: string;
  onRelay: (event: unknown) => void; // POST to /api/games/{id}/events
  onCaption: (c: Caption) => void;
};

const RELAYED = new Set(["conversation.utterance", "conversation.tool_call"]);

export default function CviEmbed({ url, onRelay, onCaption }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const call = useRef<DailyCall | null>(null);
  const [status, setStatus] = useState<"joining" | "joined" | "left" | "error">("joining");
  const [attempt, setAttempt] = useState(0);
  const relayRef = useRef(onRelay);
  const captionRef = useRef(onCaption);
  relayRef.current = onRelay;
  captionRef.current = onCaption;

  useEffect(() => {
    if (!box.current) return;
    DailyIframe.getCallInstance()?.destroy();
    const frame = DailyIframe.createFrame(box.current, {
      showLeaveButton: false,
      showFullscreenButton: false,
      iframeStyle: { width: "100%", height: "100%", border: "0", borderRadius: "14px" },
    });
    call.current = frame;
    setStatus("joining");

    frame.on("app-message", (ev) => {
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
    frame.on("joined-meeting", () => setStatus("joined"));
    frame.on("left-meeting", () => setStatus("left"));
    frame.on("error", () => setStatus("error"));

    frame.join({ url }).catch(() => setStatus("error"));
    return () => {
      call.current = null;
      frame.destroy();
    };
  }, [url, attempt]);

  return (
    <div className="relative h-full w-full">
      <div ref={box} className="h-full w-full" />
      {(status === "left" || status === "error") && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 rounded-[14px] bg-ink/80 p-4 text-center text-white">
          <p className="font-semibold">{status === "error" ? "The video call dropped." : "You left the call."}</p>
          <p className="text-sm text-white/80">Your game and score are saved. Rejoin the same call:</p>
          <button className="sketch-btn bg-marker px-4 py-2 font-bold text-ink" onClick={() => setAttempt((a) => a + 1)}>
            Reconnect
          </button>
        </div>
      )}
    </div>
  );
}
