import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { App } from "./App";
import { createEntraIdentity } from "./auth/entra";
import { noIdentity, type Identity } from "./auth/identity";
import { entraConfig } from "./data/config";

const container = document.getElementById("root");
if (!container) {
  throw new Error("#root element is missing from index.html");
}

/**
 * Sign-in is resolved before the app mounts: the answer comes back in the URL and only MSAL can read
 * it, while a token asked for mid-redirect belongs to nobody. Locally there is no session to resolve.
 */
async function start(): Promise<void> {
  const config = entraConfig();
  let identity: Identity = noIdentity;

  if (config !== null) {
    const entra = createEntraIdentity(config);
    identity = entra.identity;
    // A failure here renders signed-out rather than nothing: that is a state this app can say out
    // loud and recover from with one tap, and a blank page is neither.
    await entra.initialize().catch((cause: unknown) => {
      console.error("could not resolve the sign-in state", cause);
    });
  }

  createRoot(container!).render(
    <StrictMode>
      <App identity={identity} />
    </StrictMode>,
  );
}

void start();
