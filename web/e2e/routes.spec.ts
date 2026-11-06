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
