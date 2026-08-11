import { Outlet } from "react-router";
import { TopBar } from "./TopBar";
import { TabBar } from "./TabBar";
import { Toaster } from "../ui/Toaster";

export function Shell() {
  return (
    <div className="flex h-screen flex-col bg-canvas text-ink">
      <TopBar />
      <TabBar />
      <main className="min-h-0 flex-1 overflow-auto">
        <Outlet />
      </main>
      {/* Outside `main` and mounted once: a toast outlives the view that raised it —
          switching tabs while a refusal is on screen must not take the reason with it. */}
      <Toaster />
    </div>
  );
}
