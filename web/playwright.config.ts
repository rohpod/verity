import { defineConfig } from "@playwright/test";

// Runs against the dev server, which serves the recorded fixture (`npm run fixture` first).
export default defineConfig({
  testDir: "e2e",
  webServer: {
    command: "npm run dev -- --port 4173 --strictPort",
    url: "http://localhost:4173",
    reuseExistingServer: false,
  },
  use: { baseURL: "http://localhost:4173" },
});
