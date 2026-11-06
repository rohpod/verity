import { Link } from "react-router-dom";
import { ProvenanceBadge } from "@/components/ProvenanceBadge";
import { ResultCell } from "@/components/Result";
import { Empty } from "@/components/States";
import { Card, Note } from "@/components/ui";
import { useIndex } from "@/data/provider";
import { ownersOf } from "@/data/views";
import { SYNTHETIC_NOTE } from "@/lib/wording";

export function Risks() {
  const index = useIndex();
  const risks = index.ofType("Risk");
  return (
    <div className="grid gap-3">
      <h1 className="text-xl font-semibold">Risk register</h1>
      {risks.some((r) => r.source === "synthetic") ? <Note>{SYNTHETIC_NOTE}</Note> : null}
      {risks.length === 0 ? <Empty>No risk is recorded in this snapshot.</Empty> : null}
      {risks.map((risk) => {
        const systems = index.in(risk.id, "HAS_RISK").map((e) => e.src);
        const mitigations = index.out(risk.id, "MITIGATED_BY").map((e) => e.dst);
        return (
          <Card key={risk.id} title={<span className="flex flex-wrap items-center gap-2">{risk.title} <ProvenanceBadge source={risk.source} /></span>}>
            <p className="text-sm">{risk.description}</p>
            <p className="mt-1 text-sm">Owner: {ownersOf(index, risk.id).map((p) => p.name).join(", ") || "none recorded"}</p>
            <p className="text-sm">Systems: {systems.length ? systems.map((s) => <Link key={s} className="mr-2" to={`/systems/${encodeURIComponent(s)}`}>{index.label(s)}</Link>) : "none"}</p>
            <h3 className="mt-2 text-sm font-semibold">Mitigated by</h3>
            {mitigations.length === 0 ? <Empty>No control is recorded against this risk.</Empty> : (
              <ul className="grid gap-1 text-sm">
                {mitigations.map((c) => {
                  const results = index.snapshot.control_results.filter((r) => r.control_id === c && r.scope_id.startsWith("org:"));
                  return (
                    <li key={c}>
                      <Link to={`/controls?focus=${encodeURIComponent(c)}`}>{c}</Link> {index.label(c)}{" "}
                      {results.map((r) => <ResultCell key={r.scope_id} result={r} />)}
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        );
      })}
    </div>
  );
}
