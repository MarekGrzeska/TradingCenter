import { Outlet } from "react-router";
import { TopBar } from "./TopBar";
import { TabBar } from "./TabBar";
import { AgentChat } from "../agent/AgentChat";
import { Toaster } from "../ui/Toaster";

export function Shell() {
  return (
    <div className="flex h-screen bg-canvas text-ink">
      {/* `min-w-0`, or the grid's charts refuse to give width back when the agent panel
          opens: a flex item's default `min-width: auto` is its content, and a canvas that
          has been sized once counts as content. */}
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <TabBar />
        <main className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>

      {/* A column of the shell rather than an overlay, and outside the outlet: the panel
          spans the full height beside the bars, pushes the tab content aside instead of
          covering it, and survives every tab switch. Its own expansion is the only thing
          deciding whether it is open. */}
      <AgentChat />

      {/* Outside `main` and mounted once: a toast outlives the view that raised it —
          switching tabs while a refusal is on screen must not take the reason with it. */}
      <Toaster />
    </div>
  );
}
