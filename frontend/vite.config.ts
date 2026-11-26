import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, /api, /health and /webhooks go to the FastAPI backend on :8000.
// In production FastAPI serves this built app itself, so the browser uses the same origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { chunkSizeWarningLimit: 700 }, // daily-js is ~350 kB on its own
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000", "/health": "http://localhost:8000" },
  },
});
