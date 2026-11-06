import { Link, useParams } from "react-router-dom";
import { ProvenanceBadge, SimulatedFlag } from "@/components/ProvenanceBadge";
import { ResultCell } from "@/components/Result";
import { Empty, NotFound } from "@/components/States";
import { Badge, Card, Note, Table, Tabs, TabsContent, TabsList, TabsTrigger, Td, Th } from "@/components/ui";
import type { SnapshotIndex } from "@/data/index";
import { useIndex } from "@/data/provider";
import { compareTime } from "@/data/time";
import type { NodeOf, Obligation } from "@/data/types";
import { findingsFor, obligationsFor, ownersOf, resourcesOf, resultFor, severityRank, statusesFor } from "@/data/views";
import { count, formatTime, words } from "@/lib/utils";
import { BOUNDARY_NOTE, HISTORY_LIMIT, INHERITED_ORG, ISO_NOTE, SYNTHETIC_NOTE } from "@/lib/wording";

export function SystemProfile() {
  const index = useIndex();
  const id = decodeURIComponent(useParams().id ?? "");
  const system = index.nodeOf(id, "AISystem");
  if (!system) return <NotFound what={`The system ${id}`} />;
  return (
    <div className="grid gap-3">
      <p className="text-sm"><Link to="/registry">← AI Registry</Link></p>
      <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold">
        {system.name} <ProvenanceBadge source={system.source} />
      </h1>
      {system.source === "synthetic" ? <Note>{SYNTHETIC_NOTE}</Note> : null}
      <Tabs defaultValue="summary">
        <TabsList aria-label="System profile">
          {["summary", "components", "data", "risks", "obligations", "controls & evidence", "history"].map((tab) => (
            <TabsTrigger key={tab} value={tab}>{tab}</TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="summary"><Summary index={index} system={system} /></TabsContent>
        <TabsContent value="components"><Components index={index} system={system} /></TabsContent>
        <TabsContent value="data"><DataTab index={index} system={system} /></TabsContent>
        <TabsContent value="risks"><RisksTab index={index} system={system} /></TabsContent>
        <TabsContent value="obligations"><Obligations index={index} system={system} /></TabsContent>
        <TabsContent value="controls & evidence"><ControlsTab index={index} system={system} /></TabsContent>
        <TabsContent value="history"><History index={index} system={system} /></TabsContent>
      </Tabs>
    </div>
  );
}

type Props = { index: SnapshotIndex; system: NodeOf<"AISystem"> };

function Summary({ index, system }: Props) {
  const findings = findingsFor(index, system.id).sort((a, b) => severityRank(a.severity) - severityRank(b.severity));
  const owners = ownersOf(index, system.id);
  return (
    <Card>
      <dl className="grid gap-1 text-sm">
        <div><dt className="inline font-semibold">Purpose: </dt><dd className="inline">{system.purpose}</dd></div>
        <div><dt className="inline font-semibold">Kind: </dt><dd className="inline">{words(system.kind)}</dd></div>
        <div><dt className="inline font-semibold">Roles: </dt><dd className="inline">{system.roles.join(", ")}</dd></div>
        <div><dt className="inline font-semibold">Use domains: </dt><dd className="inline">{system.use_domains.join(", ") || "none recorded"}</dd></div>
        <div><dt className="inline font-semibold">Owner: </dt><dd className="inline">{owners.map((p) => p.name).join(", ") || "none recorded"}</dd></div>
      </dl>
      <h2 className="mt-3 font-semibold">Findings</h2>
      {findings.length === 0 ? <Empty>No findings for this system.</Empty> : (
        <ul className="ml-5 list-disc text-sm">
          {findings.map((f) => (
            <li key={`${f.code}${f.control_id}`}>
              <Badge tone={f.severity === "high" ? "bad" : f.severity === "medium" ? "warn" : "neutral"}>{f.severity}</Badge> {f.message} <SimulatedFlag simulated={f.simulated} />
            </li>
          ))}
        </ul>
      )}
      <h2 className="mt-3 font-semibold">Requirement states</h2>
      <p className="text-sm">{count(statusesFor(index, system.id), (s) => s.state).map(([s, n]) => `${n} ${words(s)}`).join(" · ") || "none"}</p>
    </Card>
  );
}

function Components({ index, system }: Props) {
  const models = index.out(system.id, "USES_MODEL").map((e) => index.nodeOf(e.dst, "Model")).filter((m): m is NodeOf<"Model"> => !!m);
  const resources = resourcesOf(index, system.id);
  return (
    <div className="grid gap-3">
      <Card title="Models">
        {models.length === 0 ? <Empty>No model is recorded for this system.</Empty> : (
          <Table label="Models">
            <thead><tr><Th>Model</Th><Th>Origin</Th><Th>Provider</Th><Th>Source</Th></tr></thead>
            <tbody>
              {models.map((m) => {
                const providers = index.out(m.id, "PROVIDED_BY").map((e) => index.nodeOf(e.dst, "Provider")).filter((p): p is NodeOf<"Provider"> => !!p);
                return (
                  <tr key={m.id}>
                    <Td>{m.name}</Td><Td>{words(m.origin)}</Td>
                    <Td>{providers.length ? providers.map((p) => (
                      <span key={p.id} className="mr-1">{p.name}{p.simulated ? <> <Badge tone="simulated">Simulated provider: no real call was made</Badge></> : null}</span>
                    )) : m.origin === "in_house" ? "in-house, no provider" : "provider not recorded"}</Td>
                    <Td><ProvenanceBadge source={m.source} /></Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>
      <Card title="AWS resources">
        {resources.length === 0 ? <Empty>This system has no AWS resource in the snapshot: it was declared, not discovered, so there is nothing for the crawler to read.</Empty> : (
          <Table label="AWS resources">
            <thead><tr><Th>Resource</Th><Th>Type</Th><Th>Environment variable names</Th><Th>Source</Th></tr></thead>
            <tbody>
              {resources.map((r) => (
                <tr key={r.id}><Td>{r.name}</Td><Td>{r.resource_type}</Td><Td>{r.env_var_names.join(", ") || "none"} <span className="text-xs">(names only, never values)</span></Td><Td><ProvenanceBadge source={r.source} /></Td></tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}

function DataTab({ index, system }: Props) {
  const processed = index.out(system.id, "PROCESSES").map((e) => ({ dataset: index.nodeOf(e.dst, "Dataset"), purpose: e.type === "PROCESSES" ? e.purpose : "" })).filter((d) => d.dataset);
  const trained = index.out(system.id, "USES_MODEL").flatMap((u) => index.out(u.dst, "TRAINED_ON").map((e) => ({ model: u.dst, dataset: index.nodeOf(e.dst, "Dataset") }))).filter((d) => d.dataset);
  if (!processed.length && !trained.length) return <Empty>No dataset is recorded for this system.</Empty>;
  return (
    <Table label="Datasets">
      <thead><tr><Th>Dataset</Th><Th>How</Th><Th>Classification</Th><Th>Personal data</Th><Th>Source</Th></tr></thead>
      <tbody>
        {processed.map(({ dataset, purpose }) => dataset && (
          <tr key={`p${dataset.id}${purpose}`}><Td>{dataset.name}</Td><Td>processed for {purpose}</Td><Td>{dataset.classification}</Td><Td>{dataset.personal_data ? "yes" : "no"}</Td><Td><ProvenanceBadge source={dataset.source} /></Td></tr>
        ))}
        {trained.map(({ model, dataset }) => dataset && (
          <tr key={`t${dataset.id}${model}`}><Td>{dataset.name}</Td><Td>trained {index.label(model)}</Td><Td>{dataset.classification}</Td><Td>{dataset.personal_data ? "yes" : "no"}</Td><Td><ProvenanceBadge source={dataset.source} /></Td></tr>
        ))}
      </tbody>
    </Table>
  );
}

function RisksTab({ index, system }: Props) {
  const risks = index.out(system.id, "HAS_RISK").map((e) => index.nodeOf(e.dst, "Risk")).filter((r): r is NodeOf<"Risk"> => !!r);
  const approvers = index.in(system.id, "APPROVES_RISK_FOR").map((e) => index.label(e.src));
  if (!risks.length) return <Empty>No risk is recorded for this system.</Empty>;
  return (
    <div className="grid gap-2">
      {approvers.length ? <p className="text-sm">Risk approved for this system by: {approvers.join(", ")}.</p> : null}
      {risks.map((risk) => (
        <Card key={risk.id} title={risk.title}>
          <p className="text-sm">{risk.description}</p>
          <p className="mt-1 text-sm">Owner: {ownersOf(index, risk.id).map((p) => p.name).join(", ") || "none recorded"} · mitigated by: {index.out(risk.id, "MITIGATED_BY").map((e) => <Link key={e.dst} className="mr-2" to={`/controls?focus=${encodeURIComponent(e.dst)}`}>{index.label(e.dst)}</Link>)}</p>
          <ProvenanceBadge source={risk.source} />
        </Card>
      ))}
    </div>
  );
}

function Obligations({ index, system }: Props) {
  const statuses = statusesFor(index, system.id);
  const rows = obligationsFor(index, system.id);
  const byRequirement = new Map<string, Obligation[]>();
  for (const row of rows) byRequirement.set(row.requirement_id, [...(byRequirement.get(row.requirement_id) ?? []), row]);
  const isoShown = statuses.some((s) => index.nodeOf(s.requirement_id, "Requirement")?.id.startsWith("req:iso"));
  if (!statuses.length) return <Empty>No requirement applies to this system in the snapshot.</Empty>;
  return (
    <div className="grid gap-2">
      {isoShown ? <Note>{ISO_NOTE}</Note> : null}
      <Table label="Obligations">
        <thead><tr><Th>Requirement</Th><Th>State</Th><Th>Applicability</Th><Th>Checked against</Th><Th>Through</Th></tr></thead>
        <tbody>
          {statuses.map((status) => {
            const requirement = index.nodeOf(status.requirement_id, "Requirement");
            const through = byRequirement.get(status.requirement_id) ?? [];
            const iso = status.requirement_id.startsWith("req:iso");
            return (
              <tr key={status.requirement_id}>
                <Td>
                  <Link to={`/controls?focus=${encodeURIComponent(status.requirement_id)}&scope=${encodeURIComponent(system.id)}`}>{requirement?.ref ?? status.requirement_id}</Link>
                  {requirement ? <div className="text-xs">{requirement.summary}</div> : null}
                </Td>
                <Td>{words(status.state)} <SimulatedFlag simulated={status.simulated} /></Td>
                <Td>{status.applicability ? words(status.applicability) : "—"}</Td>
                <Td>{requirement ? words(requirement.verified_against) : "—"}{iso ? " (never satisfied)" : ""}</Td>
                <Td>
                  {through.length === 0 ? "no control" : through.map((o, i) => (
                    <div key={i} className="text-xs">
                      {o.control_id ?? "—"}: {o.resolution === "inherited_org" ? INHERITED_ORG : words(o.resolution)}
                    </div>
                  ))}
                </Td>
              </tr>
            );
          })}
        </tbody>
      </Table>
    </div>
  );
}

function ControlsTab({ index, system }: Props) {
  const seen = new Set<string>();
  const pairs: { control: string; scope: string; resolution: string }[] = [];
  const add = (control: string | null, scope: string, resolution: string) => {
    const key = `${control}|${scope}`;
    if (!control || seen.has(key)) return;
    seen.add(key);
    pairs.push({ control, scope, resolution });
  };
  // Whose assessment answers each control is the status's `targets`, not an obligation's
  // `applies_to`, which says where the requirement applies.
  for (const status of statusesFor(index, system.id)) {
    for (const target of status.targets) if (target.scope_id) add(target.control_id, target.scope_id, target.resolution);
  }
  // Results scoped to the system itself, even for a control no requirement maps to.
  for (const r of index.snapshot.control_results) if (r.scope_id === system.id) add(r.control_id, r.scope_id, "direct");
  if (!pairs.length) return <Empty>No control result applies to this system in the snapshot.</Empty>;
  return (
    <Table label="Controls and evidence">
      <thead><tr><Th>Control</Th><Th>Answered by</Th><Th>Result</Th><Th>Evidence</Th></tr></thead>
      <tbody>
        {pairs.sort((a, b) => (a.control < b.control ? -1 : a.control > b.control ? 1 : 0)).map(({ control, scope, resolution }) => {
          const result = resultFor(index, control, scope);
          const boundary = control === "ctl:VC-060" && system.id === "sys:support-assistant" && result?.status === "not_implemented";
          return (
            <tr key={`${control}${scope}`}>
              <Td><Link to={`/controls?focus=${encodeURIComponent(control)}`}>{control}</Link><div className="text-xs">{index.label(control)}</div></Td>
              <Td>{resolution === "inherited_org" ? <Badge>{INHERITED_ORG}</Badge> : resolution === "direct" ? "this system" : words(resolution)} <span className="text-xs">({index.label(scope)})</span></Td>
              <Td>{result ? <ResultCell result={result} /> : <Badge>no result</Badge>}{boundary ? <Note tone="warn">{BOUNDARY_NOTE}</Note> : null}</Td>
              <Td>{result?.evidence_id ? <Link to={`/controls?focus=${encodeURIComponent(result.evidence_id)}`}>{result.evidence_id}</Link> : "none"}</Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

function History({ index, system }: Props) {
  const resources = resourcesOf(index, system.id);
  const resourceIds = new Set(resources.map((r) => r.id));
  const changes = index.ofType("ChangeEvent").filter((c) => index.out(c.id, "AFFECTS").some((e) => resourceIds.has(e.dst)));
  const runs = index.ofType("DiscoveryRun").filter((run) => index.out(run.id, "OBSERVED").some((e) => resourceIds.has(e.dst)));
  return (
    <div className="grid gap-2">
      <Note>{HISTORY_LIMIT}</Note>
      {resources.length === 0 ? <Empty>This system has no AWS resource in the snapshot, so no change event or discovery run can be tied to it.</Empty> : null}
      {resources.length > 0 && !changes.length && !runs.length ? <Empty>No change event or discovery run is recorded for this system’s resources.</Empty> : null}
      {changes.length > 0 ? (
        <Table label="Change events">
          <thead><tr><Th>Change event</Th><Th>Detected</Th></tr></thead>
          <tbody>{changes.sort((a, b) => compareTime(a.detected_at, b.detected_at)).map((c) => <tr key={c.id}><Td>{c.id}</Td><Td>{formatTime(c.detected_at)}</Td></tr>)}</tbody>
        </Table>
      ) : null}
      {runs.length > 0 ? (
        <Table label="Discovery runs">
          <thead><tr><Th>Run</Th><Th>Mode</Th><Th>Started</Th><Th>Source</Th></tr></thead>
          <tbody>{runs.map((r) => <tr key={r.id}><Td>{r.id}</Td><Td>{r.mode}</Td><Td>{formatTime(r.started_at)}</Td><Td><ProvenanceBadge source={r.source} /></Td></tr>)}</tbody>
        </Table>
      ) : null}
    </div>
  );
}
