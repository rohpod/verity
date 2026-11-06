import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vitest/config";

const here = path.dirname(fileURLToPath(import.meta.url));

/** Serves the recorded fixture at /data/snapshot.json while developing, and never in a build
 *  (`apply: 'serve'`). A fixture must not reach the publish path (ADR 0031, decision 3). */
function devFixture(): Plugin {
  return {
    name: "verity-dev-fixture",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/data/snapshot.json", async (_req, res) => {
        try {
          const body = await readFile(path.join(here, ".fixture", "snapshot.json"));
          res.setHeader("Content-Type", "application/json");
          res.end(body);
        } catch {
          res.statusCode = 404;
          res.end("Run `npm run fixture` first.");
        }
      });
    },
  };
}

export default defineConfig({
  // Relative, so the same build works on Pages and in `vite preview` (ADR 0031, decision 10).
  base: "./",
  // `web/public/` is where the reviewed live snapshot is committed. A build must not copy it:
  // the Pages workflow adds that file to dist/ itself, after `check:dist` and the scan.
  build: { copyPublicDir: false },
  plugins: [react(), tailwindcss(), devFixture()],
  resolve: { alias: { "@": path.join(here, "src") } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
