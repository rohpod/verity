import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ProvenanceBadge } from "@/components/ProvenanceBadge";
import { ResultCell } from "@/components/Result";
import { Empty } from "@/components/States";
import { Badge, Card, Note, Table, Td, Th } from "@/components/ui";
import type { SnapshotIndex } from "@/data/index";
import { useIndex } from "@/data/provider";
import { auditTrail, type AuditLink } from "@/data/trail";
import { compareText } from "@/data/time";
import { count, formatTime, words } from "@/lib/utils";
import { ASSURANCE_LEVELS, BOUNDARY_NOTE, INHERITED_ORG, ISO_NOTE, NO_SCORE_NOTE, REDACTED_NOTE, SIMULATED_SIGNOFF, STRENGTH_NOTE, showsBoundaryNote } from "@/lib/wording";

export function Controls() {
  const index = useIndex();
  const [params, setParams] = useSearchParams();
  const focus = params.get("focus") ?? "";
  const scopeParam = params.get("scope") ?? "";
  const controls = index.ofType("Control");
  const control = index.nodeOf(focus, "Control");
  const evidence = index.nodeOf(focus, "Evidence");
  const requirement = index.nodeOf(focus, "Requirement");
  const scopes = useMemo(() => scopeOptions(index), [index]);
  const scope = scopes.includes(scopeParam) ? scopeParam : (scopes[0] ?? "");
  const set = (key: string, value: string) => setParams((old) => { const next = new URLSearchParams(old); next.set(key, value); return next; });

  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">Controls & evidence</h1>
      <Note>{NO_SCORE_NOTE}</Note>
      <Card title="The assurance ladder">
        <ol className="grid gap-1 text-sm">
          {ASSURANCE_LEVELS.map((l) => <li key={l.level}><strong>{l.name}</strong>: {l.meaning} ({index.snapshot.control_results.filter((r) => r.level === l.level).length} results)</li>)}
        </ol>
      </Card>

      <Card title="Controls">
        <Table label="Controls">
          <thead><tr><Th>Control</Th><Th>Kind</Th><Th>Automatable</Th><Th>Results by status</Th></tr></thead>
          <tbody>
            {controls.map((c) => (
              <tr key={c.id} aria-current={c.id === focus || undefined}>
                <Td><button className="text-left underline" onClick={() => set("focus", c.id)}>{c.id}</button><div className="text-xs">{c.title}</div></Td>
                <Td>{words(c.kind)} · {c.scope_level}-level</Td>
                <Td>{c.automatable ? "yes" : "no: needs a person (L4)"}</Td>
                <Td className="text-xs">{count(index.snapshot.control_results.filter((r) => r.control_id === c.id), (r) => r.status).map(([s, n]) => `${n} ${words(s)}`).join(", ")}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      {control ? <ControlDetail index={index} controlId={control.id} /> : null}
      {evidence ? <EvidenceDetail index={index} id={evidence.id} /> : null}

      <Card title="Audit trail">
        <p className="mb-2 text-sm">Follow a requirement to its proof: requirement → control → assessment → evidence. This is computed in the browser by following the snapshot’s edges, and a test compares it with the Python answer.</p>
        <div className="mb-2 flex flex-wrap gap-2 text-sm">
          <label>Requirement{" "}
            <select value={requirement?.id ?? ""} onChange={(e) => set("focus", e.target.value)} className="max-w-[16rem] border border-[var(--border)] bg-transparent">
              <option value="">Choose…</option>
              {index.ofType("Requirement").map((r) => <option key={r.id} value={r.id}>{r.id}</option>)}
            </select>
          </label>
          <label>Scope{" "}
            <select value={scope} onChange={(e) => set("scope", e.target.value)} className="max-w-[16rem] border border-[var(--border)] bg-transparent">
              {scopes.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        </div>
        {requirement && scope ? <Trail index={index} requirementId={requirement.id} scopeId={scope} /> : <Empty>Choose a requirement to see its audit trail.</Empty>}
      </Card>

      <Card title="All evidence">
        <Table label="Evidence">
          <thead><tr><Th>Evidence</Th><Th>Kind</Th><Th>Collected</Th><Th>Source</Th></tr></thead>
          <tbody>
            {index.ofType("Evidence").map((e) => (
              <tr key={e.id}><Td><button className="underline" onClick={() => set("focus", e.id)}>{e.id}</button></Td><Td>{words(e.kind)}</Td><Td>{formatTime(e.collected_at)}</Td><Td><ProvenanceBadge source={e.source} /></Td></tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}

function scopeOptions(index: SnapshotIndex): string[] {
  const ids = [...index.ofType("Organisation"), ...index.ofType("AISystem"), ...index.ofType("Provider")].map((n) => n.id);
  return ids.sort(compareText);
}

function ControlDetail({ index, controlId }: { index: SnapshotIndex; controlId: string }) {
  const control = index.nodeOf(controlId, "Control");
  const results = index.snapshot.control_results.filter((r) => r.control_id === controlId);
  if (!control) return null;
  return (
    <Card title={`${control.id}: ${control.title}`}>
      <p className="text-sm">{control.summary}</p>
      <p className="my-1 text-sm">Scope level: {control.scope_level}. {control.automatable ? "Automated checks may raise this control." : "Organisational or legal: a person must verify it (L4) before it is fully implemented."}</p>
      <Table label={`Results for ${control.id}`}>
        <thead><tr><Th>Scope</Th><Th>Result</Th><Th>Method</Th><Th>Evidence</Th></tr></thead>
        <tbody>
          {results.map((r) => (
            <tr key={r.scope_id}>
              <Td>{index.label(r.scope_id)}{r.scope_id.startsWith("org:") ? <div className="text-xs">{INHERITED_ORG} by every system</div> : null}</Td>
              <Td><ResultCell result={r} />{showsBoundaryNote(r.control_id, r.scope_id, r.status) ? <Note tone="warn">{BOUNDARY_NOTE}</Note> : null}</Td><Td>{words(r.method)}</Td>
              <Td>{r.evidence_id ? <Link to={`/controls?focus=${encodeURIComponent(r.evidence_id)}`}>{r.evidence_id}</Link> : "none"}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

function EvidenceDetail({ index, id }: { index: SnapshotIndex; id: string }) {
  const e = index.nodeOf(id, "Evidence");
  if (!e) return null;
  return (
    <Card title={`Evidence ${e.id}`}>
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <Badge>{words(e.kind)}</Badge><ProvenanceBadge source={e.source} />
        <span>collected {formatTime(e.collected_at)} by {e.collector}</span><span>valid until {formatTime(e.valid_until)}</span>
      </p>
      <p className="break-all text-xs">sha256 {e.sha256}</p>
      {e.redacted ? <Note tone="warn" >{REDACTED_NOTE}</Note> : null}
      <p className="text-sm">About: <Link to={`/graph?node=${encodeURIComponent(e.subject)}`}>{index.label(e.subject)}</Link></p>
      <pre className="mt-2 max-h-72 overflow-auto rounded bg-[var(--muted)] p-2 text-xs">{JSON.stringify(e.content, null, 2)}</pre>
    </Card>
  );
}

function Trail({ index, requirementId, scopeId }: { index: SnapshotIndex; requirementId: string; scopeId: string }) {
  const requirement = index.nodeOf(requirementId, "Requirement");
  const trail = useMemo(() => {
    try { return auditTrail(index, requirementId, scopeId); } catch { return null; }
  }, [index, requirementId, scopeId]);
  if (!requirement || !trail) return <Empty>This requirement has no audit trail for that scope.</Empty>;
  const iso = requirement.id.startsWith("req:iso");
  return (
    <div className="grid gap-2" data-testid="audit-trail">
      <p className="text-sm"><strong>{requirement.ref}</strong>: {requirement.summary} <Badge>checked against: {words(requirement.verified_against)}</Badge> <a href={requirement.source_url} rel="noreferrer noopener">source</a></p>
      {iso ? <Note>{ISO_NOTE}</Note> : null}
      {trail.links.map((link, i) => <TrailLink key={i} index={index} link={link} />)}
    </div>
  );
}

function TrailLink({ index, link }: { index: SnapshotIndex; link: AuditLink }) {
  if (link.resolution === "unmapped") return <Empty>No usable control is mapped to this requirement, so there is nothing to prove it.</Empty>;
  const m = link.mapping;
  return (
    <div className="rounded border border-[var(--border)] p-2 text-sm" data-testid="trail-link">
      <p>
        <strong>{link.controlId}</strong> {link.controlId ? index.label(link.controlId) : ""} ·{" "}
        {link.resolution === "inherited_org" ? INHERITED_ORG : words(link.resolution)}
        {link.providerId ? ` (${index.label(link.providerId)})` : ""}
      </p>
      {m ? <p className="text-xs">Mapping: {words(m.strm)}, strength {m.strength}, sufficiency {m.sufficiency}. {m.rationale}</p> : null}
      {m ? <p className="text-xs">{STRENGTH_NOTE}</p> : null}
      {link.assessmentId ? (
        <p>
          Assessment {link.assessmentId}: {words(link.status ?? "")}, {ASSURANCE_LEVELS[link.assuranceLevel ?? 0]?.name}
          {link.assessedBy ? <> · signed off by {index.label(link.assessedBy)}{link.signoffSource === "simulated" ? <> <Badge tone="simulated">{SIMULATED_SIGNOFF}</Badge></> : null}</> : null}
        </p>
      ) : <p>No assessment answers this control for this scope.</p>}
      {link.evidence.length ? (
        <Table label="Evidence on this path">
          <thead><tr><Th>Evidence</Th><Th>Kind</Th><Th>Collector</Th><Th>Collected</Th><Th>sha256</Th></tr></thead>
          <tbody>
            {link.evidence.map((e) => (
              <tr key={e.evidenceId}>
                <Td><Link to={`/controls?focus=${encodeURIComponent(e.evidenceId)}`}>{e.evidenceId}</Link>{index.nodeOf(e.evidenceId, "Evidence")?.redacted ? <div className="text-xs">{REDACTED_NOTE}</div> : null}</Td>
                <Td>{words(e.kind)}</Td><Td>{e.collector}</Td><Td>{formatTime(e.collectedAt)}</Td><Td className="break-all text-xs">{e.sha256}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : null}
    </div>
  );
}
