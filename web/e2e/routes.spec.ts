import { expect, test, type Page } from "@playwright/test";

/** Every route at phone width and at desktop width, plus deep links (ADR 0031, decision 11).
 *  The dev server serves the recorded fixture, so the banner shows. */
const ROUTES = [
  "/#/",
  "/#/registry",
  "/#/systems/sys:support-assistant",
  "/#/risks",
  "/#/crosswalk",
  "/#/controls",
  "/#/controls?focus=req:euaia:art4&scope=org:kestrel",
  "/#/graph",
  "/#/graph?mode=impact&subject=prov:mock-bedrock",
  "/#/graph?mode=stale",
  "/#/about",
];

async function noSidewaysScroll(page: Page) {
  const overflow = await page.evaluate(() => {
    const root = document.scrollingElement as HTMLElement;
    return root.scrollWidth - window.innerWidth;
  });
  expect(overflow).toBeLessThanOrEqual(0);
}

for (const [name, size] of [["phone", { width: 390, height: 844 }], ["desktop", { width: 1280, height: 800 }]] as const) {
  test.describe(name, () => {
    test.use({ viewport: size });
    for (const route of ROUTES) {
      test(`${route} fits the width and shows its timestamp`, async ({ page }) => {
        await page.goto(route);
        await expect(page.getByTestId("snapshot-time")).toBeVisible();
        await expect(page.getByTestId("fixture-banner")).toBeVisible();
        await page.waitForLoadState("networkidle");
        await noSidewaysScroll(page);
      });
    }
  });
}

test("a deep link to a system opens it, and a tab can be chosen", async ({ page }) => {
  await page.goto("/#/systems/sys:talent-screening");
  await expect(page.getByRole("heading", { name: /Talent Screening/ })).toBeVisible();
  await page.getByRole("tab", { name: "controls & evidence" }).click();
  await expect(page.getByRole("table", { name: "Controls and evidence" })).toBeVisible();
});

test("the graph is a canvas at desktop width and a list at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/#/graph?node=sys:support-assistant");
  await expect(page.getByRole("img", { name: /Graph of the chosen node/ })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByText("At this width the graph is shown as a list.")).toBeVisible();
  await expect(page.getByRole("img", { name: /Graph of the chosen node/ })).toHaveCount(0);
});

test.describe("a long option in a Graph selector does not widen the page at phone width", () => {
  // The live snapshot has 240 start nodes with ids up to 47 characters, and a select takes the
  // width of its widest option. The fixture has shorter ids, so the option is added here. The
  // stale view is left out: the fixture holds no ChangeEvent, so that view has no selector.
  test.use({ viewport: { width: 390, height: 844 } });
  for (const route of ["/#/graph?node=sys:support-assistant", "/#/graph?mode=impact&subject=prov:mock-bedrock"]) {
    test(`${route}`, async ({ page }) => {
      await page.goto(route);
      await expect(page.getByTestId("snapshot-time")).toBeVisible();
      await page.waitForLoadState("networkidle");
      await page.evaluate(() => {
        // The first select is the node, subject or change chooser. "Hops" never holds long ids.
        const select = document.querySelector("main select") as HTMLSelectElement;
        const option = document.createElement("option");
        option.value = option.textContent = "cand:shadow-summariser-a-very-long-identifier-0123456789";
        select.append(option);
        select.selectedIndex = select.options.length - 1;
      });
      await noSidewaysScroll(page);
    });
  }
});

test("the page makes no request outside its own origin", async ({ page }) => {
  const foreign: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!["localhost", "127.0.0.1"].includes(url.hostname) && url.protocol.startsWith("http")) foreign.push(url.hostname);
  });
  await page.goto("/#/");
  await page.waitForLoadState("networkidle");
  expect(foreign).toEqual([]);
});
