import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ProvenanceBadge } from "@/components/ProvenanceBadge";
import { Empty } from "@/components/States";
import { Badge, Card, Note, Table, Td, Th } from "@/components/ui";
import type { SnapshotIndex } from "@/data/index";
import { useIndex } from "@/data/provider";
import { staleAssessmentIds, staleByChange } from "@/data/trail";
import { compareText } from "@/data/time";
import { ownersOf } from "@/data/views";
import { words } from "@/lib/utils";
import type { GraphEdge, GraphNode } from "./GraphCanvas";

const GraphCanvas = lazy(() => import("./GraphCanvas"));

const MAX_NODES = 120;

function NamedList({ index, ids, empty = "none" }: { index: SnapshotIndex; ids: string[]; empty?: string }) {
  if (ids.length === 0) return <>{empty}</>;
  return (
    <ul className="grid gap-1">
      {ids.map((id) => <li key={id}><Named index={index} id={id} /></li>)}
    </ul>
  );
}

function graphNode(index: SnapshotIndex, id: string): GraphNode {
  const node = index.node(id);
  return { id, label: index.label(id), type: node?.type ?? "", source: node?.source };
}

/** A name with the badge of its record, so synthetic and simulated records are labelled in every
 *  list, at phone width too (ADR 0031 "Every view shows provenance badges"). */
function Named({ index, id, link }: { index: SnapshotIndex; id: string; link?: string }) {
  const source = index.node(id)?.source;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {link ? <Link to={link}>{index.label(id)}</Link> : index.label(id)}
      {source ? <ProvenanceBadge source={source} /> : null}
    </span>
  );
}

/** The neighbourhood of a node, `depth` hops out. Control assessments are hidden by default:
 *  there are hundreds, and they bury the rest. */
export function neighbourhood(index: SnapshotIndex, start: string, depth: number, showAssessments: boolean) {
  const nodes = new Map<string, GraphNode>();
  const edges: GraphEdge[] = [];
  const hidden = (id: string) => !showAssessments && id !== start && index.node(id)?.type === "ControlAssessment";
  let frontier = [start];
  if (index.node(start)) nodes.set(start, graphNode(index, start));
  for (let hop = 0; hop < depth; hop++) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const edge of [...index.out(id), ...index.in(id)]) {
        const other = edge.src === id ? edge.dst : edge.src;
        if (hidden(other)) continue;
        if (!nodes.has(other)) {
          if (nodes.size >= MAX_NODES) continue;
          nodes.set(other, graphNode(index, other));
          next.push(other);
        }
        edges.push({ id: `${edge.src}|${edge.type}|${edge.dst}|${edge.type === "APPLIES_TO" ? edge.role : ""}`, source: edge.src, target: edge.dst, label: edge.type });
      }
    }
    frontier = next;
  }
  const unique = new Map(edges.filter((e) => nodes.has(e.source) && nodes.has(e.target)).map((e) => [e.id, e]));
  return { nodes: [...nodes.values()], edges: [...unique.values()], capped: nodes.size >= MAX_NODES };
}

function usePhone(): boolean {
  const query = "(max-width: 640px)";
  const get = () => (typeof window.matchMedia === "function" ? window.matchMedia(query).matches : true);
  const [phone, setPhone] = useState(get);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const on = () => setPhone(list.matches);
    list.addEventListener("change", on);
    return () => list.removeEventListener("change", on);
  }, []);
  return phone;
}

export function Graph() {
  const index = useIndex();
  const [params, setParams] = useSearchParams();
  const mode = params.get("mode") ?? "neighbourhood";
  const set = (key: string, value: string) => setParams((old) => { const next = new URLSearchParams(old); next.set(key, value); return next; });
  return (
    <div className="grid gap-3">
      <h1 className="text-xl font-semibold">Graph explorer</h1>
      <div role="tablist" aria-label="Graph mode" className="flex flex-wrap gap-2">
        {(
          [["neighbourhood", "Neighbourhood"], ["impact", "Impact of…"], ["stale", "Stale by change"]] as const
        ).map(([value, label]) => (
          <button key={value} role="tab" aria-selected={mode === value} onClick={() => set("mode", value)} className={`rounded border px-2 py-1 text-sm ${mode === value ? "border-[var(--accent)] font-semibold" : "border-[var(--border)]"}`}>{label}</button>
        ))}
      </div>
      {mode === "impact" ? <Impact index={index} /> : mode === "stale" ? <Stale index={index} /> : <Neighbourhood index={index} />}
    </div>
  );
}

function Neighbourhood({ index }: { index: SnapshotIndex }) {
  const [params, setParams] = useSearchParams();
  const phone = usePhone();
  const [depth, setDepth] = useState(1);
  const [showAssessments, setShowAssessments] = useState(false);
  const start = index.node(params.get("node"))?.id ?? index.ofType("AISystem")[0]?.id ?? "";
  const options = useMemo(() => [...index.nodes.values()].filter((n) => n.type !== "ControlAssessment").map((n) => n.id).sort(compareText), [index]);
  const graph = useMemo(() => neighbourhood(index, start, depth, showAssessments), [index, start, depth, showAssessments]);
  if (!start) return <Empty>The snapshot holds no nodes to explore.</Empty>;
  return (
    <Card>
      <div className="mb-2 flex flex-wrap items-center gap-3 text-sm">
        <label>Start from{" "}
          <select value={start} onChange={(e) => setParams({ node: e.target.value })} className="max-w-[18rem] border border-[var(--border)] bg-transparent">
            {options.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
        </label>
        <label>Hops <select value={depth} onChange={(e) => setDepth(Number(e.target.value))} className="border border-[var(--border)] bg-transparent"><option value={1}>1</option><option value={2}>2</option></select></label>
        <label><input type="checkbox" checked={showAssessments} onChange={(e) => setShowAssessments(e.target.checked)} /> Show control assessments ({index.ofType("ControlAssessment").length})</label>
      </div>
      {graph.capped ? <Note tone="warn">Showing the first {MAX_NODES} nodes only. Pick a closer start node or one hop.</Note> : null}
      {phone ? (
        <p className="text-sm">At this width the graph is shown as a list.</p>
      ) : (
        <Suspense fallback={<p role="status">Loading the graph…</p>}>
          <GraphCanvas nodes={graph.nodes} edges={graph.edges} />
        </Suspense>
      )}
      <Table label="Neighbourhood as a list">
        <thead><tr><Th>From</Th><Th>Edge</Th><Th>To</Th></tr></thead>
        <tbody>
          {graph.edges.map((e) => (
            <tr key={e.id}><Td><Named index={index} id={e.source} link={`/graph?node=${encodeURIComponent(e.source)}`} /></Td><Td>{words(e.label)}</Td><Td><Named index={index} id={e.target} link={`/graph?node=${encodeURIComponent(e.target)}`} /></Td></tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

function Impact({ index }: { index: SnapshotIndex }) {
  const [params, setParams] = useSearchParams();
  const subjects = [...index.ofType("Provider"), ...index.ofType("Model")];
  const chosen = index.node(params.get("subject"))?.id ?? subjects[0]?.id ?? "";
  const model = index.nodeOf(chosen, "Model");
  const row = index.snapshot.provider_impact.find((p) => p.provider_id === chosen);
  return (
    <Card title="Impact of an incident at…">
      <label className="text-sm">Provider or model{" "}
        <select value={chosen} onChange={(e) => setParams({ mode: "impact", subject: e.target.value })} className="border border-[var(--border)] bg-transparent">
          {subjects.map((s) => <option key={s.id} value={s.id}>{index.label(s.id)} ({s.type.toLowerCase()})</option>)}
        </select>
      </label>
      {model?.origin === "in_house" ? <Empty>{model.name} is an in-house model. It has no provider, so an incident at a provider does not reach it. <ProvenanceBadge source={model.source} /></Empty> : null}
      {model && model.origin !== "in_house" ? <Empty>Choose its provider to see the impact. A model is reached through its provider. <ProvenanceBadge source={model.source} /></Empty> : null}
      {!model && row && row.systems.length === 0 ? <Empty>No system uses a model from this provider.</Empty> : null}
      {!model && row && row.systems.length > 0 ? (
        <>
          <p className="my-2 flex flex-wrap items-center gap-2 text-sm">
            <Named index={index} id={chosen} /> {row.systems.length} system(s) reached, and {row.assessment_ids.length} assessment(s) scoped to the provider itself. <ProvenanceBadge source={row.source} />
          </p>
          <Table label="Systems reached">
            <thead><tr><Th>System</Th><Th>Models</Th><Th>Owners</Th><Th>Risks</Th><Th>Requirements aimed at it</Th></tr></thead>
            <tbody>
              {row.systems.map((s) => (
                <tr key={s.system_id}>
                  <Td><Named index={index} id={s.system_id} link={`/systems/${encodeURIComponent(s.system_id)}`} /></Td>
                  <Td><NamedList index={index} ids={s.model_ids} /></Td>
                  <Td><NamedList index={index} ids={s.owner_ids.length ? s.owner_ids : ownersOf(index, s.system_id).map((p) => p.id)} /></Td>
                  <Td><NamedList index={index} ids={s.risk_ids} /></Td>
                  <Td>{s.requirement_ids.length}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      ) : null}
    </Card>
  );
}

function Stale({ index }: { index: SnapshotIndex }) {
  const [params, setParams] = useSearchParams();
  const changes = index.ofType("ChangeEvent");
  const chosen = index.node(params.get("change"))?.id ?? changes[0]?.id ?? "";
  const impact = chosen ? staleByChange(index, chosen) : null;
  return (
    <Card title="Evidence made stale by a change">
      <p className="mb-2 text-sm">Only evidence collected from the changed resource <em>before</em> the change was detected is stale. Evidence collected afterwards, and signed documents or attestations, are not touched.</p>
      {changes.length === 0 ? <Empty>This snapshot holds no change event, so nothing is stale by change.</Empty> : null}
      {impact ? (
        <>
          <label className="text-sm">Change event{" "}
            <select value={chosen} onChange={(e) => setParams({ mode: "stale", change: e.target.value })} className="border border-[var(--border)] bg-transparent">
              {changes.map((c) => <option key={c.id} value={c.id}>{c.id}</option>)}
            </select>
          </label>
          {impact.evidence.length === 0 ? <Empty>No evidence is stale because of this change.</Empty> : (
            <Table label="Stale evidence">
              <thead><tr><Th>Evidence</Th><Th>Collected from</Th><Th>Supports assessments</Th></tr></thead>
              <tbody>{impact.evidence.map((e) => <tr key={e.evidenceId} data-testid="stale-evidence"><Td><Named index={index} id={e.evidenceId} /></Td><Td><Named index={index} id={e.resourceId} /></Td><Td><NamedList index={index} ids={e.assessmentIds} /></Td></tr>)}</tbody>
            </Table>
          )}
          <p className="mt-2 text-sm" data-testid="stale-assessments">Assessments affected: {staleAssessmentIds(impact).join(", ") || "none"} <Badge>derived in the browser</Badge></p>
        </>
      ) : null}
    </Card>
  );
}
