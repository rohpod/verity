import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ProvenanceBadge } from "@/components/ProvenanceBadge";
import { Badge, Card, Note, Table, Td, Th } from "@/components/ui";
import { useIndex } from "@/data/provider";
import { frameworksOf } from "@/data/views";
import { count, words } from "@/lib/utils";
import { ASSURANCE_LEVELS, NO_SCORE_NOTE } from "@/lib/wording";
import type { Source } from "@/data/types";

const STATES = ["satisfied", "partially_addressed", "not_met", "not_addressed", "not_applicable"] as const;

export function Overview() {
  const index = useIndex();
  const { snapshot } = index;
  const systems = index.ofType("AISystem");
  const bySource = count(systems, (s) => s.source);
  const bySeverity = count(snapshot.findings, (f) => f.severity);
  const byCode = count(snapshot.findings, (f) => `${f.severity}|${f.code}`);
  const candidates = index.ofType("Candidate");

  const perFramework = new Map<string, Record<string, number>>();
  for (const status of snapshot.requirement_statuses) {
    for (const framework of frameworksOf(index, status.requirement_id)) {
      const row = perFramework.get(framework) ?? {};
      row[status.state] = (row[status.state] ?? 0) + 1;
      perFramework.set(framework, row);
    }
  }
  const chart = [...perFramework].map(([framework, row]) => ({ framework: index.label(framework), ...Object.fromEntries(STATES.map((s) => [s, row[s] ?? 0])) }));
  const ladder = ASSURANCE_LEVELS.map((l) => ({ ...l, total: snapshot.control_results.filter((r) => r.level === l.level).length }));
  const hasWithoutEvidence = snapshot.findings.some((f) => f.code === "no_evidence");

  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">Overview</h1>
      <Note>{NO_SCORE_NOTE}</Note>
      {hasWithoutEvidence ? (
        <Note tone="warn">
          Many requirements show “not met” because no evidence has been collected for the control behind them, not because a check failed. The findings below are counted by code, so you can tell the two apart.
        </Note>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Systems by source">
          <ul className="grid gap-1">
            {bySource.map(([source, total]) => (
              <li key={source} className="flex items-center gap-2">
                <ProvenanceBadge source={source as Source} /> <span>{total} system{total === 1 ? "" : "s"}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-sm"><Link to="/registry">Open the AI Registry</Link></p>
        </Card>
        <Card title="Candidates">
          <p data-testid="candidate-count">{candidates.length} unregistered candidate{candidates.length === 1 ? "" : "s"} found by discovery.</p>
          <p className="mt-2 text-sm"><Link to="/registry#candidates">See the Candidates inbox</Link></p>
        </Card>
      </div>

      <Card title="Findings by severity and code">
        <p className="mb-2 flex flex-wrap gap-2">
          {bySeverity.map(([severity, total]) => (
            <Badge key={severity} tone={severity === "high" ? "bad" : severity === "medium" ? "warn" : "neutral"}>{severity}: {total}</Badge>
          ))}
        </p>
        <Table label="Findings by code">
          <thead><tr><Th>Severity</Th><Th>Code</Th><Th>Findings</Th></tr></thead>
          <tbody>
            {byCode.map(([key, total]) => {
              const [severity, code] = key.split("|") as [string, string];
              return <tr key={key}><Td>{severity}</Td><Td>{words(code)}</Td><Td>{total}</Td></tr>;
            })}
          </tbody>
        </Table>
      </Card>

      <Card title="Requirement states by framework">
        <div className="h-64 w-full" aria-hidden="true">
          <ResponsiveContainer>
            <BarChart data={chart} layout="vertical" margin={{ left: 16 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="framework" width={110} />
              <Tooltip />
              {STATES.map((state, i) => (
                <Bar key={state} dataKey={state} stackId="s" fill={["#15803d", "#ca8a04", "#b91c1c", "#6b7280", "#9ca3af"][i]} name={words(state)} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
        <Table label="Requirement states by framework">
          <thead><tr><Th>Framework</Th>{STATES.map((s) => <Th key={s}>{words(s)}</Th>)}</tr></thead>
          <tbody>
            {chart.map((row) => (
              <tr key={row.framework}><Td>{row.framework}</Td>{STATES.map((s) => <Td key={s}>{(row as Record<string, number | string>)[s]}</Td>)}</tr>
            ))}
          </tbody>
        </Table>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">A requirement under a nested clause is counted once per framework it belongs to. The states are read from the snapshot.</p>
      </Card>

      <Card title="Assurance ladder">
        <Table label="Control results by assurance level">
          <thead><tr><Th>Level</Th><Th>Meaning</Th><Th>Control results</Th></tr></thead>
          <tbody>
            {ladder.map((l) => <tr key={l.level}><Td>{l.name}</Td><Td>{l.meaning}</Td><Td>{l.total}</Td></tr>)}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}
