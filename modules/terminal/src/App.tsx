import { Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { Shell } from "./app/Shell";
import { NotFound } from "./app/NotFound";
import { ViewErrorBoundary } from "./app/ViewErrorBoundary";
import { DEFAULT_TAB_PATH, TABS } from "./app/tabs";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Shell />}>
          <Route index element={<Navigate to={`/${DEFAULT_TAB_PATH}`} replace />} />
          {TABS.map((tab) => (
            <Route
              key={tab.id}
              path={tab.path}
              element={
                <ViewErrorBoundary>
                  <Suspense fallback={<p className="p-4 text-sm text-ink-muted">Wczytuję…</p>}>
                    <tab.Component />
                  </Suspense>
                </ViewErrorBoundary>
              }
            />
          ))}
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
