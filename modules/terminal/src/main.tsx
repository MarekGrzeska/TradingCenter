import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { App } from "./App";
import { identity } from "./data/marketData";

const container = document.getElementById("root");
if (!container) {
  throw new Error("#root element is missing from index.html");
}

/**
 * Sign-in is resolved before the app mounts, never alongside it.
 *
 * The operator comes back from Entra to this page with the answer in the URL,
 * and MSAL is the only thing that can read it. Meanwhile the first render
 * subscribes to candles, which asks for a token — and a token asked for while
 * the redirect is still unresolved belongs to nobody, so the subscription is
 * refused and the chart shows a signed-out operator who is in the middle of
 * signing in.
 *
 * Nothing to do in the local mode: `identity` is then the one with no session
 * to resolve, and this resolves immediately.
 */
async function start(): Promise<void> {
  const initialize = (identity as { initialize?: () => Promise<void> }).initialize;
  // A failure here is not a reason to show nothing. The terminal renders
  // signed-out, which is a state it can already say out loud and recover from
  // by sending the operator through sign-in — a blank page says nothing and
  // recovers from nothing.
  await initialize?.().catch((cause: unknown) => {
    console.error("could not resolve the sign-in state", cause);
  });

  createRoot(container!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void start();
