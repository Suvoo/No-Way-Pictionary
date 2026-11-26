import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

// No <StrictMode>: it double-mounts effects in dev, and Daily allows only one call frame per page.
createRoot(document.getElementById("root")!).render(<App />);
