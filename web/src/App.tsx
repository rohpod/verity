import { HashRouter, Link, Route, Routes } from "react-router-dom";
import { Shell } from "@/components/Shell";
import { SnapshotProvider } from "@/data/provider";
import type { SnapshotIndex } from "@/data/index";
import { About } from "@/pages/About";
import { Controls } from "@/pages/Controls";
import { Crosswalk } from "@/pages/Crosswalk";
import { Graph } from "@/pages/Graph";
import { Overview } from "@/pages/Overview";
import { Registry } from "@/pages/Registry";
import { Risks } from "@/pages/Risks";
import { SystemProfile } from "@/pages/SystemProfile";
import { NOT_LEGAL_ADVICE } from "@/lib/wording";

/** Hash routes work on Pages and in preview with no 404 page (ADR 0031, decision 10). */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Overview />} />
        <Route path="registry" element={<Registry />} />
        <Route path="systems/:id" element={<SystemProfile />} />
        <Route path="risks" element={<Risks />} />
        <Route path="crosswalk" element={<Crosswalk />} />
        <Route path="controls" element={<Controls />} />
        <Route path="graph" element={<Graph />} />
        <Route path="about" element={<About />} />
        <Route path="*" element={<p>That page does not exist. <Link to="/">Back to the Overview</Link>.</p>} />
      </Route>
    </Routes>
  );
}

export function App({ index }: { index?: SnapshotIndex }) {
  return (
    <SnapshotProvider index={index}>
      <HashRouter>
        <AppRoutes />
        <footer className="mx-auto max-w-6xl px-4 py-4 text-xs text-[var(--muted-foreground)]">
          {NOT_LEGAL_ADVICE} <Link to="/about">About</Link>
        </footer>
      </HashRouter>
    </SnapshotProvider>
  );
}
