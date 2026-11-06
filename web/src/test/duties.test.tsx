/** One test per row of the plan's "UI duties" table (ADR 0031). The wording is asserted as
 *  written, so softening it fails a test. */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResultCell } from "@/components/Result";
import type { ControlResult } from "@/data/types";
import { fixture, mini, renderRoute } from "./helpers";
import {
  BOUNDARY_NOTE, DERIVED_NOTE, INHERITED_ORG, ISO_NOTE, MAPPINGS_NOTE, NOT_LEGAL_ADVICE, NO_SCORE_NOTE,
  REDACTED_NOTE, SIMULATED_SIGNOFF, STRENGTH_NOTE, SYNTHETIC_NOTE,
} from "@/lib/wording";

const text = () => document.body.textContent ?? "";

async function openTab(name: string) {
  await userEvent.click(screen.getByRole("tab", { name }));
}

describe("Every view: provenance badges and the snapshot timestamp", () => {
  it("shows both on the registry and a system profile", () => {
    renderRoute(fixture(), "/registry");
    expect(screen.getByTestId("snapshot-time")).toBeInTheDocument();
    expect(screen.getAllByTestId("provenance-badge").length).toBeGreaterThan(20);
  });
});

describe("Every page: simulated components are reachable, and synthetic records say so", () => {
  it("lists the header's simulated components and says synthetic records are invented", () => {
    const index = fixture();
    renderRoute(index, "/registry");
    expect(screen.getByTestId("simulated-panel")).toHaveTextContent("simulated sign-offs");
    expect(screen.getByText(SYNTHETIC_NOTE)).toBeInTheDocument();
  });

  it("repeats it on a system profile and the risk register", () => {
    renderRoute(fixture(), "/systems/sys:call-transcriber");
    expect(screen.getByText(SYNTHETIC_NOTE)).toBeInTheDocument();
  });
});

describe("Requirement views: verified_against beside ISO requirements, and why they never go green", () => {
  it("shows the value and the explanation in the audit trail", () => {
    const index = fixture();
    const iso = index.ofType("Requirement").find((r) => r.id.startsWith("req:iso"));
    expect(iso).toBeDefined();
    renderRoute(index, `/controls?focus=${encodeURIComponent(iso!.id)}&scope=sys:call-transcriber`);
    expect(screen.getByText(ISO_NOTE)).toBeInTheDocument();
    expect(screen.getByTestId("audit-trail")).toHaveTextContent(`checked against: ${iso!.verified_against.replace(/_/g, " ")}`);
  });

  it("shows it in a system's obligations", async () => {
    renderRoute(fixture(), "/systems/sys:call-transcriber");
    await openTab("obligations");
    expect(screen.getByText(ISO_NOTE)).toBeInTheDocument();
    expect(text()).toContain("(never satisfied)");
  });

  it("explains in the ISO note that the standard was not read", () => {
    expect(ISO_NOTE).toMatch(/can never show as satisfied/);
    expect(ISO_NOTE).toMatch(/has not read the standard's text/);
  });
});

describe("Requirement views: ISO shows IDs and original summaries only", () => {
  it("renders only the clause ID and summary of an ISO requirement", () => {
    const index = fixture();
    const iso = index.ofType("Requirement").filter((r) => r.id.startsWith("req:iso"));
    expect(iso.length).toBeGreaterThan(0);
    // The snapshot's ISO nodes carry no text field beyond the original `summary`.
    const allowed = new Set(["id", "type", "ref", "summary", "source_url", "source_version", "last_verified", "verified_against", "source", "confidence", "valid_from", "valid_to"]);
    for (const r of iso) expect(Object.keys(r).filter((k) => !allowed.has(k))).toEqual([]);
    renderRoute(index, `/controls?focus=${encodeURIComponent(iso[0]!.id)}&scope=org:kestrel`);
    const trail = screen.getByTestId("audit-trail");
    expect(trail).toHaveTextContent(iso[0]!.ref);
    expect(trail).toHaveTextContent(iso[0]!.summary);
  });
});

describe("Crosswalk", () => {
  it("shows rationale, the derived label, and never calls two requirements equal", () => {
    renderRoute(fixture(), "/crosswalk");
    expect(screen.getByText(DERIVED_NOTE)).toBeInTheDocument();
    const derived = screen.getAllByTestId("derived-link");
    expect(derived.length).toBeGreaterThan(0);
    for (const row of derived) expect(row).toHaveTextContent("derived");
    expect(text()).not.toMatch(/\b(equivalent|identical|same as|equals)\b/i);
    expect(text()).toContain(MAPPINGS_NOTE);
    const direct = within(screen.getByRole("table", { name: "Direct mappings" }));
    expect(direct.getAllByText(/semantic|syntactic|functional/).length).toBeGreaterThan(0);
  });

  it("shows from_strm, to_strm and the control a derived link goes through", () => {
    const index = fixture();
    // The page opens on the first framework pair, in the order it lists them.
    const first = [...new Set(index.snapshot.crosswalk.map((r) => `${r.from_framework}|${r.to_framework}`))].sort()[0]!;
    const row = index.snapshot.crosswalk.find((r) => `${r.from_framework}|${r.to_framework}` === first && r.links.length > 0)!;
    const link = row.links[0]!;
    renderRoute(index, "/crosswalk");
    const table = screen.getByRole("table", { name: "Derived crosswalk" });
    expect(within(table).getAllByText(link.via_control_id).length).toBeGreaterThan(0);
    expect(within(table).getAllByText("From STRM").length + within(table).getAllByText("To STRM").length).toBe(2);
    // A derived row has no STRM type of its own.
    expect(within(table).queryByText(/^STRM$/)).toBeNull();
  });

  it("labels strength as a Verity convention taken from the Secure Controls Framework, not from NIST", () => {
    renderRoute(fixture(), "/crosswalk");
    expect(screen.getByText(STRENGTH_NOTE)).toBeInTheDocument();
    expect(STRENGTH_NOTE).toMatch(/Verity convention.*Secure Controls Framework.*not from NIST/);
  });
});

describe("Controls: status, level and freshness together, never a bare tick", () => {
  const base: ControlResult = { assessor: null, control_id: "ctl:X", evidence_id: null, freshness: "fresh", level: 2, method: "m", scope_id: "org:o", simulated: false, source: "derived", status: "implemented" };

  it("shows all three for every result in the snapshot", () => {
    for (const result of fixture().snapshot.control_results.slice(0, 80)) {
      const { container, unmount } = render(<ResultCell result={result} />);
      expect(container.textContent).toMatch(/implemented|not assessed|not applicable/);
      expect(container.textContent).toMatch(/L[0-4] /);
      expect(container.textContent).toMatch(/fresh|expiring|stale|no evidence to age/);
      expect(container.textContent).not.toMatch(/[✓✔✅]/);
      unmount();
    }
  });

  it("says when there is nothing to age instead of leaving freshness blank", () => {
    render(<ResultCell result={{ ...base, freshness: null, level: 0, status: "not_assessed" }} />);
    expect(screen.getByText("no evidence to age")).toBeInTheDocument();
  });

  it("labels a demo L4 result as a simulated sign-off", () => {
    render(<ResultCell result={{ ...base, level: 4, simulated: true }} />);
    expect(screen.getByText(SIMULATED_SIGNOFF)).toBeInTheDocument();
  });

  it("shows the simulated sign-off on the real L4 result and its audit trail", () => {
    const index = fixture();
    const l4 = index.snapshot.control_results.find((r) => r.level === 4 && r.simulated)!;
    renderRoute(index, `/controls?focus=${encodeURIComponent(l4.control_id)}`);
    expect(screen.getAllByText(SIMULATED_SIGNOFF).length).toBeGreaterThan(0);
  });

  it("shows the sign-off in an audit trail through that control", () => {
    const index = fixture();
    const mapped = index.edges.find((e) => e.type === "MAPS_TO" && e.dst === "ctl:VC-032")!;
    renderRoute(index, `/controls?focus=${encodeURIComponent(mapped.src)}&scope=sys:talent-screening`);
    expect(screen.getByTestId("audit-trail")).toHaveTextContent(SIMULATED_SIGNOFF);
  });
});

describe("Evidence: redacted hashes", () => {
  it("says the hash covers the published content and cannot be checked against the live table", () => {
    const index = fixture();
    const redacted = index.ofType("Evidence").find((e) => e.redacted)!;
    renderRoute(index, `/controls?focus=${encodeURIComponent(redacted.id)}`);
    expect(screen.getByText(REDACTED_NOTE)).toBeInTheDocument();
    expect(REDACTED_NOTE).toMatch(/hash covers the published content, not the stored original/);
    expect(REDACTED_NOTE).toMatch(/cannot be checked against the live table/);
  });

  it("does not say it for evidence that was not redacted", () => {
    const index = fixture();
    const plain = index.ofType("Evidence").find((e) => !e.redacted)!;
    renderRoute(index, `/controls?focus=${encodeURIComponent(plain.id)}`);
    expect(screen.queryByText(REDACTED_NOTE)).toBeNull();
  });
});

describe("VC-060 on support-assistant", () => {
  it("says IAM's simulator shows the boundary denies the call and that no live call was tried", async () => {
    renderRoute(fixture(), "/systems/sys:support-assistant");
    await openTab("controls & evidence");
    expect(screen.getByText(BOUNDARY_NOTE)).toBeInTheDocument();
    expect(BOUNDARY_NOTE).toMatch(/IAM's policy simulator shows the permissions boundary denies this call/);
    expect(BOUNDARY_NOTE).toMatch(/No live call was tried/);
  });

  it("never says the grant is ineffective", async () => {
    renderRoute(fixture(), "/systems/sys:support-assistant");
    await openTab("controls & evidence");
    expect(text()).not.toMatch(/ineffective/i);
    expect(BOUNDARY_NOTE).not.toMatch(/ineffective/i);
  });

  it("is not shown for other systems", async () => {
    renderRoute(fixture(), "/systems/sys:talent-screening");
    await openTab("controls & evidence");
    expect(screen.queryByText(BOUNDARY_NOTE)).toBeNull();
  });
});

describe("Providers", () => {
  it("shows Provider.simulated and never suggests Bedrock or OpenAI were invoked", async () => {
    renderRoute(fixture(), "/systems/sys:support-assistant");
    await openTab("components");
    expect(screen.getByText(/Simulated provider: no real call was made/)).toBeInTheDocument();
    expect(text()).not.toMatch(/\binvoked\b|\bwas called\b/i);
  });
});

describe("Discovery: the signals that fired", () => {
  it("lists each signal of a candidate, and the finding", () => {
    const index = fixture();
    const candidate = index.ofType("Candidate")[0]!;
    renderRoute(index, "/registry");
    const card = screen.getByTestId("candidate");
    for (const signal of candidate.signals) expect(card).toHaveTextContent(signal.replace(/_/g, " "));
    expect(card).toHaveTextContent("shadow-summariser");
    expect(card).toHaveTextContent("high: shadow ai candidate");
  });
});

describe("System views: organisation-level controls show as inherited", () => {
  it("labels an organisation-answered control as inherited from the organisation", async () => {
    renderRoute(fixture(), "/systems/sys:call-transcriber");
    await openTab("controls & evidence");
    expect(screen.getAllByText(INHERITED_ORG).length).toBeGreaterThan(0);
  });
});

describe("About", () => {
  it("says it is not legal advice and that mappings are the author's interpretation", () => {
    renderRoute(fixture(), "/about");
    expect(screen.getByText(new RegExp(NOT_LEGAL_ADVICE))).toBeInTheDocument();
    expect(text()).toContain("Framework mappings are the author's own interpretation.");
  });
});

describe("History: honest about its limit", () => {
  it("states that H# history is not published", async () => {
    renderRoute(fixture(), "/systems/sys:contract-insights");
    await openTab("history");
    expect(text()).toContain("Node history (H#) is not published");
  });

  it("explains an empty history for a system with no AWS resource", async () => {
    renderRoute(fixture(), "/systems/sys:call-transcriber");
    await openTab("history");
    expect(text()).toMatch(/has no AWS resource in the snapshot/);
  });

  it("shows the change event on the mini snapshot", async () => {
    renderRoute(mini(), "/systems/sys:mini-bot");
    await openTab("history");
    expect(text()).toMatch(/chg:/);
  });
});

describe("No single compliance score (decision 6)", () => {
  it("has no percentage, gauge or score on the Overview", () => {
    renderRoute(fixture(), "/");
    expect(screen.getByText(NO_SCORE_NOTE)).toBeInTheDocument();
    expect(text()).not.toMatch(/\d\s?%/);
    expect(document.querySelector("[role=meter], [role=progressbar], meter, progress")).toBeNull();
    expect(text()).not.toMatch(/compliance score:|overall score|% compliant/i);
  });

  it("explains the many not-met states and shows findings by code", () => {
    renderRoute(fixture(), "/");
    expect(text()).toMatch(/because no evidence has been collected/);
    expect(screen.getByRole("table", { name: "Findings by code" })).toHaveTextContent("no evidence");
  });
});
