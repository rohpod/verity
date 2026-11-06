import { defineConfig } from "@playwright/test";

// The production build, served under /verity/, with the generated fixture copied beside it.
// `npm run smoke:build` builds and stages it first (see package.json `e2e:prod`).
export default defineConfig({
  testDir: "e2e",
  testMatch: "prod.spec.ts",
  webServer: {
    command: "node e2e/serve-prod.mjs 4174",
    url: "http://localhost:4174/verity/",
    reuseExistingServer: false,
  },
  use: { baseURL: "http://localhost:4174" },
});
