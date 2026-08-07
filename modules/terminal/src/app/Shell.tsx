import { Outlet } from "react-router";
import { TopBar } from "./TopBar";
import { TabBar } from "./TabBar";

export function Shell() {
  return (
    <div className="flex h-screen flex-col bg-canvas text-ink">
      <TopBar />
      <TabBar />
      <main className="min-h-0 flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
