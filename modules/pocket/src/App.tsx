import { useMemo, useState, useSyncExternalStore } from "react";
import { noIdentity, type Identity } from "./auth/identity";
import { createAgentApi } from "./agent/agentApi";
import { AgentScreen } from "./agent/AgentScreen";
import { archiveBase, workbenchBase } from "./data/config";
import { createPolymarketApi } from "./polymarket/api";
import { PolymarketScreen } from "./polymarket/PolymarketScreen";
import { SignInScreen } from "./SignInScreen";
import { TabBar } from "./app/TabBar";
import { loadTab, saveTab, type Tab } from "./app/tabs";
import styles from "./App.module.css";

export interface AppProps {
  /** The archive's identity, which is also the app's sign-in state: it is the audience sign-in names. */
  archive?: Identity;
  /** The conversation's. A different audience, because a token minted for one module is never sent
   *  to another. */
  workbench?: Identity;
}

export function App({ archive = noIdentity, workbench = noIdentity }: AppProps) {
  const state = useSyncExternalStore(archive.subscribe, archive.state);
  const [tab, setTab] = useState<Tab>(() => loadTab());

  // Built once per identity: the screens' effects take these as dependencies, and a client rebuilt on
  // every render would re-read its back end on every render with it.
  const polymarket = useMemo(() => createPolymarketApi(archiveBase(), archive), [archive]);
  const agent = useMemo(() => createAgentApi(workbenchBase(), workbench), [workbench]);

  // `unconfigured` is the local stack and renders the screens bare — only a deployment that has an
  // identity to lose can be signed out of one.
  if (state === "signed-out") {
    return <SignInScreen onSignIn={archive.signIn} />;
  }

  return (
    <div className={styles.app}>
      {/* Both mounted, one hidden: switching tabs must not throw away a half-typed question or
          restart the archive's poll, and a phone switches tabs constantly. */}
      <div className={tab === "markets" ? styles.pane : styles.hidden}>
        <PolymarketScreen api={polymarket} />
      </div>
      <div className={tab === "agent" ? styles.pane : styles.hidden}>
        <AgentScreen api={agent} />
      </div>

      <TabBar
        current={tab}
        onChange={(next) => {
          setTab(next);
          saveTab(next);
        }}
      />
    </div>
  );
}
