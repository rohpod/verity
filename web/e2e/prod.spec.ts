import { expect, test, type Page } from "@playwright/test";

/** The production build under a /verity/ subpath (ADR 0031, decision 10). It fails on any console
 *  error, uncaught exception, CSP violation, failed request or request to another origin. */
const ROUTES = [
  "#/",
  "#/registry",
  "#/systems/sys:support-assistant",
  "#/risks",
  "#/crosswalk",
  "#/controls",
  "#/controls?focus=req:euaia:art4&scope=org:kestrel",
  "#/graph",
  "#/graph?mode=impact&subject=prov:mock-bedrock",
  "#/graph?mode=stale",
  "#/about",
];

function watch(page: Page) {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(`console error: ${message.text()}`);
  });
  page.on("pageerror", (error) => problems.push(`uncaught: ${error.message}`));
  page.on("requestfailed", (request) => problems.push(`request failed: ${request.url()}`));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.protocol.startsWith("http") && url.origin !== "http://localhost:4174") problems.push(`other origin: ${url.origin}`);
  });
  return page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (event) => {
      console.error(`CSP violation: ${event.violatedDirective} ${event.blockedURI}`);
    });
  }).then(() => problems);
}

for (const [name, size] of [["phone", { width: 390, height: 844 }], ["desktop", { width: 1280, height: 800 }]] as const) {
  test.describe(`production build, ${name}`, () => {
    test.use({ viewport: size });
    for (const route of ROUTES) {
      test(`/verity/${route} loads clean`, async ({ page }) => {
        const problems = await watch(page);
        await page.goto(`/verity/${route}`);
        await expect(page.getByTestId("snapshot-time")).toBeVisible();
        await expect(page.getByTestId("fixture-banner")).toBeVisible();
        await page.waitForLoadState("networkidle");
        const overflow = await page.evaluate(() => (document.scrollingElement as HTMLElement).scrollWidth - window.innerWidth);
        expect(overflow).toBeLessThanOrEqual(0);
        expect(problems).toEqual([]);
      });
    }
  });
}

test("the graph canvas loads from the subpath without a violation", async ({ page }) => {
  const problems = await watch(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/verity/#/graph?node=sys:support-assistant");
  await expect(page.getByRole("img", { name: /Graph of the chosen node/ })).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(problems).toEqual([]);
});

test("the snapshot is read from under the subpath", async ({ page }) => {
  const urls: string[] = [];
  page.on("request", (request) => urls.push(new URL(request.url()).pathname));
  await page.goto("/verity/#/");
  await expect(page.getByTestId("snapshot-time")).toBeVisible();
  expect(urls).toContain("/verity/data/snapshot.json");
});

test("a refresh on a deep link still works, because routes are in the hash", async ({ page }) => {
  await page.goto("/verity/#/systems/sys:talent-screening");
  await page.reload();
  await expect(page.getByRole("heading", { name: /Talent Screening/ })).toBeVisible();
});

test("the watcher itself sees a CSP violation (so a clean run means something)", async ({ page }) => {
  const problems = await watch(page);
  await page.goto("/verity/#/about");
  await expect(page.getByTestId("snapshot-time")).toBeVisible();
  // The policy blocks this before any request leaves the browser.
  await page.evaluate(() => fetch("https://example.invalid/blocked").catch(() => undefined));
  await expect.poll(() => problems.some((p) => p.includes("CSP violation: connect-src"))).toBe(true);
});
