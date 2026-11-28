import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/router";
import { createRuntime, RuntimeProvider } from "./app/runtime";

const requested =
  import.meta.env.VITE_COMMERCE_MODE ??
  (import.meta.env.MODE === "demo" ? "demo" : "api");
if (requested && requested !== "api" && requested !== "demo")
  throw new Error("VITE_COMMERCE_MODE는 api 또는 demo여야 합니다.");
const runtime = createRuntime(requested === "demo" ? "demo" : "api");
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RuntimeProvider runtime={runtime}>
      <App />
    </RuntimeProvider>
  </StrictMode>,
);
