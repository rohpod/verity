import { screen } from "@testing-library/react";
import { fixture, mini, renderRoute } from "./helpers";

const text = () => document.body.textContent ?? "";

describe("the stale-by-change view", () => {
  it("lists only the evidence collected before the change, on the mini snapshot", () => {
    renderRoute(mini(), "/graph?mode=stale");
    expect(screen.getAllByTestId("stale-evidence")).toHaveLength(1);
    expect(screen.getByTestId("stale-assessments")).toHaveTextContent("ca:VC-900:sys:mini-bot");
  });

  it("says there is nothing when the snapshot holds no change event", () => {
    renderRoute(fixture(), "/graph?mode=stale");
    expect(text()).toContain("holds no change event");
  });
});
