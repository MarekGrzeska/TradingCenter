import { useMemo } from "react";
import { createPolymarketApi } from "./polymarket/api";
import { PolymarketScreen } from "./polymarket/PolymarketScreen";

/** One screen, and no router: this app is the prediction-market tab of the terminal, on a phone.
 *  A second surface here would be the terminal again, badly. */
export function App() {
  // Built once: the screen's effects take it as a dependency, and a client rebuilt on every render
  // would re-read the archive on every render with it.
  const api = useMemo(() => createPolymarketApi(), []);
  return <PolymarketScreen api={api} />;
}
