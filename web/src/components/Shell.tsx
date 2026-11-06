import { useMemo, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import MiniSearch from "minisearch";
import { ErrorScreen, Loading } from "@/components/States";
import { Badge } from "@/components/ui";
import { useIndex, useSnapshotState } from "@/data/provider";
import type { SnapshotIndex } from "@/data/index";
import { formatTime } from "@/lib/utils";

export const FIXTURE_BANNER = "Recorded fixture: simulated, nothing read from AWS";

const NAV = [
  ["/", "Overview"],
  ["/registry", "AI Registry"],
  ["/risks", "Risk register"],
  ["/crosswalk", "Crosswalk"],
  ["/controls", "Controls & evidence"],
  ["/graph", "Graph"],
] as const;

export function Shell() {
  const state = useSnapshotState();
  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorScreen message={state.message} />;
  return <Ready />;
}

function Ready() {
  const index = useIndex();
  const { header } = index.snapshot;
  return (
    <div className="mx-auto max-w-6xl px-4 pb-8">
      {header.data_source !== "live" ? (
        <div role="status" data-testid="fixture-banner" className="my-2 rounded border border-amber-500 bg-[var(--warn-bg)] p-2 text-sm font-semibold text-[var(--warn-fg)]">
          {FIXTURE_BANNER}
        </div>
      ) : null}
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
        <Link to="/" className="text-lg font-bold no-underline">Verity</Link>
        <nav aria-label="Main" className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "font-semibold" : "")}>
              {label}
            </NavLink>
          ))}
        </nav>
        <Search index={index} />
      </header>
      <p className="text-sm text-[var(--muted-foreground)]" data-testid="snapshot-time">
        Snapshot as of <time dateTime={header.as_of}>{formatTime(header.as_of)}</time> · data source: {header.data_source}
      </p>
      <SimulatedPanel />
      <main className="mt-3">
        <Outlet />
      </main>
    </div>
  );
}

/** `header.simulated_components` and the redaction counts, one click away on every page. */
export function SimulatedPanel() {
  const { header } = useIndex().snapshot;
  return (
    <details className="my-2 rounded border border-[var(--border)] p-2 text-sm" data-testid="simulated-panel">
      <summary className="cursor-pointer font-medium">What in this snapshot is not real</summary>
      <ul className="ml-5 list-disc">
        {header.simulated_components.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <p className="mt-2">
        All people, companies and decisions are invented. Bedrock and OpenAI are mock-only: no real model was ever called. Redaction:{" "}
        {header.redaction.steps.join("; ")}.
      </p>
    </details>
  );
}

function route(index: SnapshotIndex, id: string): string {
  const node = index.node(id);
  switch (node?.type) {
    case "AISystem":
      return `/systems/${encodeURIComponent(id)}`;
    case "Candidate":
      return "/registry#candidates";
    case "Risk":
      return "/risks";
    case "Requirement":
    case "Control":
    case "ControlAssessment":
    case "Evidence":
      return `/controls?focus=${encodeURIComponent(id)}`;
    default:
      return `/graph?node=${encodeURIComponent(id)}`;
  }
}

function Search({ index }: { index: SnapshotIndex }) {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const engine = useMemo(() => {
    const mini = new MiniSearch<{ id: string; text: string; type: string }>({
      fields: ["text", "id"],
      storeFields: ["type"],
      searchOptions: { prefix: true, fuzzy: 0.15 },
    });
    mini.addAll(
      [...index.nodes.values()]
        .filter((n) => n.type !== "ControlAssessment")
        .map((n) => ({ id: n.id, type: n.type, text: [index.label(n.id), "purpose" in n ? n.purpose : "", "summary" in n && typeof n.summary === "string" ? n.summary : ""].join(" ") })),
    );
    return mini;
  }, [index]);
  const results = query.trim() ? engine.search(query.trim()).slice(0, 8) : [];
  return (
    <div className="relative ml-auto">
      <input
        type="search"
        aria-label="Search the snapshot"
        placeholder="Search systems, controls, requirements…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-64 max-w-full rounded border border-[var(--border)] bg-transparent px-2 py-1 text-sm"
      />
      {results.length ? (
        <ul className="absolute right-0 z-10 mt-1 w-72 max-w-[90vw] rounded border border-[var(--border)] bg-[var(--background)] p-1 text-sm shadow" aria-label="Search results">
          {results.map((r) => (
            <li key={r.id}>
              <button
                className="flex w-full items-center justify-between gap-2 px-2 py-1 text-left hover:bg-[var(--muted)]"
                onClick={() => {
                  navigate(route(index, r.id));
                  setQuery("");
                }}
              >
                <span>{index.label(r.id)}</span>
                <Badge>{String(r.type)}</Badge>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
