import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FIXTURE_BANNER } from "@/components/Shell";
import { SOURCE_BADGES } from "@/components/ProvenanceBadge";
import { fixture, mini, renderRoute, ROUTES } from "./helpers";
import { SIMULATED_SIGNOFF } from "@/lib/wording";

describe.each([
  ["fixture", fixture],
  ["mini snapshot", mini],
])("every route renders from the %s", (_name, load) => {
  it.each(ROUTES)("%s shows the snapshot timestamp, a provenance badge and a way to reach what is simulated", (route) => {
    const index = load();
    renderRoute(index, route);
    expect(screen.getByTestId("snapshot-time")).toHaveTextContent("Snapshot as of 2026-11-06");
    // The mini snapshot has no risk or crosswalk rows, so those pages show an empty state.
    const empty = load === mini && (route === "/risks" || route === "/crosswalk");
    if (route !== "/about" && route !== "/graph" && !empty) {
      expect(screen.getAllByTestId("provenance-badge").length).toBeGreaterThan(0);
    }
    const panel = screen.getByTestId("simulated-panel");
    for (const item of index.snapshot.header.simulated_components) {
      expect(panel).toHaveTextContent(item);
    }
    expect(panel).toHaveTextContent("Bedrock and OpenAI are mock-only");
  });

  it("shows the persistent banner because the data source is not live", () => {
    renderRoute(load(), "/");
    expect(screen.getByTestId("fixture-banner")).toHaveTextContent(FIXTURE_BANNER);
  });
});

describe("badges", () => {
  it("covers every Source value, with a distinct label", () => {
    const labels = Object.values(SOURCE_BADGES).map((b) => b.label);
    expect(Object.keys(SOURCE_BADGES).sort()).toEqual(["declared", "derived", "discovered", "seeded", "simulated", "synthetic"]);
    expect(new Set(labels).size).toBe(6);
    expect(labels).toEqual(expect.arrayContaining(["Live-discovered", "Declared", "Seeded", "Synthetic", "Derived", "Simulated"]));
  });

  it("shows a discovered record as Live-discovered on the mini snapshot", () => {
    renderRoute(mini(), "/registry");
    expect(screen.getByTestId("candidate")).toHaveTextContent("Live-discovered");
  });
});

describe("the live banner", () => {
  it("is absent when the data source is live", () => {
    const index = fixture();
    const live = { ...index.snapshot, header: { ...index.snapshot.header, data_source: "live" as const } };
    return import("@/data/index").then(({ SnapshotIndex }) => {
      renderRoute(new SnapshotIndex(live), "/");
      expect(screen.queryByTestId("fixture-banner")).toBeNull();
    });
  });
});

describe("search", () => {
  it("finds a system by name and goes to its profile", async () => {
    renderRoute(fixture(), "/");
    await userEvent.type(screen.getByLabelText("Search the snapshot"), "talent");
    const results = within(screen.getByLabelText("Search results"));
    await userEvent.click(results.getAllByRole("button")[0] as HTMLElement);
    expect(screen.queryByLabelText("Search results")).toBeNull();
  });
});

describe("the sign-off label", () => {
  it("is a literal in the wording", () => {
    expect(SIMULATED_SIGNOFF).toBe("simulated sign-off");
  });
});
