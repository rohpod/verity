/** Slice 1 to 3 results from the plan's "Done when" lines. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { neighbourhood } from "@/pages/Graph";
import { fixture, mini, renderRoute } from "./helpers";

const text = () => document.body.textContent ?? "";

/** The row of the controls table that this system answers itself. */
function ownRow(control: string): HTMLElement {
  const rows = within(screen.getByRole("table", { name: "Controls and evidence" })).getAllByRole("row");
  const row = rows.find((r) => r.textContent?.includes(control) && r.textContent.includes("this system"));
  if (!row) throw new Error(`no row for ${control} answered by this system`);
  return row;
}

describe("Overview", () => {
  it("counts systems by source, findings by severity and code, requirement states and candidates", () => {
    const index = fixture();
    renderRoute(index, "/");
    expect(screen.getByTestId("candidate-count")).toHaveTextContent("1 unregistered candidate");
    expect(screen.getByRole("table", { name: "Requirement states by framework" })).toHaveTextContent("EU AI Act");
    expect(screen.getByRole("table", { name: "Control results by assurance level" })).toBeInTheDocument();
    const high = index.snapshot.findings.filter((f) => f.severity === "high").length;
    expect(text()).toContain(`high: ${high}`);
  });

  it("shows requirement counts that equal the snapshot's own rows", () => {
    const index = fixture();
    renderRoute(index, "/");
    const table = screen.getByRole("table", { name: "Requirement states by framework" });
    const euaia = index.snapshot.requirement_statuses.filter((s) => s.requirement_id.startsWith("req:euaia"));
    const notMet = euaia.filter((s) => s.state === "not_met").length;
    const row = within(table).getByText("EU AI Act").closest("tr") as HTMLElement;
    expect(row).toHaveTextContent(String(notMet));
  });
});

describe("AI Registry and Candidates", () => {
  it("shows shadow-summariser as a high candidate with its signals", () => {
    renderRoute(fixture(), "/registry");
    const card = screen.getByTestId("candidate");
    expect(card).toHaveTextContent("shadow-summariser");
    expect(card).toHaveTextContent("high: shadow ai candidate");
    expect(card).toHaveTextContent("env ai name");
    expect(card).toHaveTextContent("name ai token");
  });

  it("lists every system and sorts by a column", async () => {
    const index = fixture();
    renderRoute(index, "/registry");
    const table = screen.getByRole("table", { name: "AI systems" });
    expect(within(table).getAllByRole("row")).toHaveLength(index.ofType("AISystem").length + 1);
    await userEvent.click(within(table).getByRole("button", { name: "Kind" }));
    expect(within(table).getByRole("columnheader", { name: "Kind" })).toHaveAttribute("aria-sort", "ascending");
  });
});

describe("System profile", () => {
  it("has seven tabs", () => {
    renderRoute(fixture(), "/systems/sys:talent-screening");
    const tabs = within(screen.getByRole("tablist", { name: "System profile" })).getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["summary", "components", "data", "risks", "obligations", "controls & evidence", "history"]);
  });

  it("shows the VC-060 failure for support-assistant", async () => {
    renderRoute(fixture(), "/systems/sys:support-assistant");
    expect(text()).toMatch(/ctl:VC-060 for sys:support-assistant is not implemented/);
    await userEvent.click(screen.getByRole("tab", { name: "controls & evidence" }));
    const row = ownRow("ctl:VC-060");
    expect(row).toHaveTextContent("not implemented");
  });

  it("shows the bias-test gap for Talent Screening", async () => {
    renderRoute(fixture(), "/systems/sys:talent-screening");
    expect(text()).toMatch(/ctl:VC-014 for sys:talent-screening has no usable evidence/);
    await userEvent.click(screen.getByRole("tab", { name: "controls & evidence" }));
    const row = ownRow("ctl:VC-014");
    expect(row).toHaveTextContent("Bias testing");
    expect(row).toHaveTextContent("not assessed");
    expect(row).toHaveTextContent("no evidence to age");
  });

  it("shows an unknown system as not in the snapshot", () => {
    renderRoute(fixture(), "/systems/sys:nope");
    expect(text()).toMatch(/is not in this snapshot/);
  });

  it("shows env var names and never values", async () => {
    renderRoute(fixture(), "/systems/sys:contract-insights");
    await userEvent.click(screen.getByRole("tab", { name: "components" }));
    expect(text()).toContain("(names only, never values)");
  });
});

describe("Controls and the audit trail", () => {
  it("lists the controls and the assurance ladder", () => {
    renderRoute(fixture(), "/controls");
    expect(screen.getByRole("table", { name: "Controls" })).toBeInTheDocument();
    expect(text()).toContain("L4 Verified");
  });

  it("shows an empty prompt until a requirement is chosen", () => {
    renderRoute(fixture(), "/controls");
    expect(text()).toContain("Choose a requirement to see its audit trail.");
  });

  it("shows the audit trail of a requirement with its evidence", () => {
    renderRoute(fixture(), "/controls?focus=req:euaia:art4&scope=org:kestrel");
    expect(screen.getByTestId("audit-trail")).toHaveTextContent("ctl:VC-001");
    expect(screen.getAllByTestId("trail-link").length).toBeGreaterThan(0);
  });
});

describe("Risk register", () => {
  it("shows risks with owners, systems and mitigating controls", () => {
    renderRoute(fixture(), "/risks");
    expect(text()).toContain("Ranking is biased");
    expect(text()).toContain("Mitigated by");
  });

  it("shows an empty state on a snapshot with no risks", () => {
    renderRoute(mini(), "/risks");
    expect(text()).toContain("No risk is recorded in this snapshot.");
  });
});

describe("Graph explorer", () => {
  it("hides the control assessments by default and shows them on request", async () => {
    const index = fixture();
    const hidden = neighbourhood(index, "ctl:VC-001", 1, false);
    const shown = neighbourhood(index, "ctl:VC-001", 1, true);
    expect(hidden.nodes.some((n) => n.type === "ControlAssessment")).toBe(false);
    expect(shown.nodes.some((n) => n.type === "ControlAssessment")).toBe(true);
    expect(index.ofType("ControlAssessment")).toHaveLength(433);
  });

  it("shows the list at phone width", () => {
    renderRoute(fixture(), "/graph?node=sys:support-assistant");
    expect(text()).toContain("At this width the graph is shown as a list.");
    expect(screen.getByRole("table", { name: "Neighbourhood as a list" })).toBeInTheDocument();
  });

  it("shows the impact of a provider, and the systems it reaches", () => {
    const index = fixture();
    renderRoute(index, "/graph?mode=impact&subject=prov:mock-bedrock");
    const row = index.snapshot.provider_impact.find((p) => p.provider_id === "prov:mock-bedrock")!;
    expect(row.systems.length).toBeGreaterThan(0);
    const table = screen.getByRole("table", { name: "Systems reached" });
    expect(within(table).getAllByRole("row")).toHaveLength(row.systems.length + 1);
  });

  it("gives the empty case for an in-house model", () => {
    renderRoute(fixture(), "/graph?mode=impact&subject=model:anomaly-ae");
    expect(text()).toMatch(/in-house model\. It has no provider/);
  });

  it("gives the empty case for a provider no system uses", () => {
    const index = fixture();
    const snapshot = { ...index.snapshot, provider_impact: index.snapshot.provider_impact.map((p) => (p.provider_id === "prov:mock-bedrock" ? { ...p, systems: [] } : p)) };
    return import("@/data/index").then(({ SnapshotIndex }) => {
      renderRoute(new SnapshotIndex(snapshot), "/graph?mode=impact&subject=prov:mock-bedrock");
      expect(text()).toContain("No system uses a model from this provider.");
    });
  });
});
