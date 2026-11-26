import { motion } from "framer-motion";
import { Shape } from "./api";

// The PAL's sketch. Shapes come from backend/strokes.json (100x100 box, y down) one stroke at a
// time; the newest stroke animates in like a pen. A small deterministic wobble makes it look
// hand drawn rather than perfect. Black on white only, by design.

function rand(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280 - 0.5;
  };
}

// Straight segments: only the corners move a little, so lines stay straight but not ruler-perfect.
function polylineD(pts: [number, number][], r: () => number): string {
  return pts.map(([x, y], i) => `${i ? "L" : "M"}${(x + r() * 1.2).toFixed(1)} ${(y + r() * 1.2).toFixed(1)}`).join(" ");
}

// Curves: a smooth, low-frequency bulge in the radius (not per-point noise), like a quick pen loop.
function curveD(cx: number, cy: number, rx: number, ry: number, a0: number, a1: number, r: () => number): string {
  const steps = Math.max(16, Math.round(Math.abs(a1 - a0) / 6));
  const amp = 0.05 + Math.abs(r()) * 0.04;
  const phase = r() * Math.PI * 2;
  const pts: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const deg = a0 + ((a1 - a0) * i) / steps;
    const a = (deg * Math.PI) / 180;
    const k = 1 + amp * Math.sin(2 * a + phase);
    pts.push([cx + rx * k * Math.cos(a), cy + ry * k * Math.sin(a)]);
  }
  return pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
}

export function shapeToPath(s: Shape, seed: number): string {
  const r = rand(seed);
  switch (s.type) {
    case "line":
      return polylineD(s.points, r);
    case "circle":
      return curveD(s.cx, s.cy, s.r, s.r, -80, 290, r); // slight overshoot, like a real pen
    case "ellipse":
      return curveD(s.cx, s.cy, s.rx, s.ry, -80, 290, r);
    case "arc":
      return curveD(s.cx, s.cy, s.r, s.r, s.start, s.end, r);
  }
}

export default function Canvas({ strokes }: { strokes: Shape[][] }) {
  return (
    <div className="sketch relative aspect-square w-full overflow-hidden bg-white">
      <svg viewBox="-4 -4 108 108" className="h-full w-full" role="img" aria-label={`The AI's sketch, ${strokes.length} strokes so far`}>
        {strokes.map((stroke, si) => {
          const newest = si === strokes.length - 1;
          return stroke.map((shape, hi) => (
            <motion.path
              key={`${si}-${hi}`}
              d={shapeToPath(shape, si * 31 + hi * 7 + 3)}
              fill="none"
              stroke="#161412"
              strokeWidth={2.6}
              strokeLinecap="round"
              strokeLinejoin="round"
              // eslint-disable-next-line @typescript-eslint/no-explicit-any -- framer-motion's SVG typings reject pathLength here; runtime is fine
              initial={(newest ? { pathLength: 0 } : false) as any}
              animate={{ pathLength: 1 } as any}
              transition={{ duration: 0.8, delay: hi * 0.35, ease: "easeInOut" }}
            />
          ));
        })}
      </svg>
      {strokes.length === 0 && (
        <p className="absolute inset-0 flex items-center justify-center text-ink-soft">The AI is picking up its pen...</p>
      )}
    </div>
  );
}
