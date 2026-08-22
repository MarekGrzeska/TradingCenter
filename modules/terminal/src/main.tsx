import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { App } from "./App";
import { startSignInIfNeeded } from "./auth/autoSignIn";
import { identity, initializeIdentity } from "./data/marketData";

const container = document.getElementById("root");
if (!container) {
  throw new Error("#root element is missing from index.html");
}

/**
 * Sign-in is resolved before the app mounts, never alongside it. The operator returns
 * from Entra with the answer in the URL and only MSAL can read it, while the first
 * render is already asking for a token — one asked for mid-redirect belongs to nobody,
 * so the subscription is refused and the chart reports a signed-out operator who is in
 * the middle of signing in. In local mode there is no session to resolve.
 */
async function start(): Promise<void> {
  // A failure here renders signed-out rather than nothing: that is a state the terminal
  // can say out loud and recover from, and a blank page is neither.
  await initializeIdentity().catch((cause: unknown) => {
    console.error("could not resolve the sign-in state", cause);
  });

  // Before mounting, not from inside a view: a mounted terminal subscribes, is refused,
  // and flashes an error on the way to a sign-in page it was always going to.
  if (startSignInIfNeeded(identity)) return;

  createRoot(container!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void start();
