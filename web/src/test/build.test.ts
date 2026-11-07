// @vitest-environment node
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { build } from "vite";

const web = path.resolve(__dirname, "../..");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

describe("a build carries nothing from the public directory (ADR 0031, decision 3)", () => {
  it("leaves a snapshot in the public directory out of dist/", async () => {
    // The reviewed live snapshot lives in web/public/data/. If a build copied it, `check:dist`
    // would fail in CI and Pages once it is committed. This test never reads or writes the
    // repository's web/public/: the sample sits in a temporary public directory that is handed to
    // Vite, so the test gives the same result with or without a committed snapshot.
    const publicDir = mkdtempSync(path.join(os.tmpdir(), "verity-public-"));
    const outDir = mkdtempSync(path.join(os.tmpdir(), "verity-build-"));
    try {
      mkdirSync(path.join(publicDir, "data"));
      writeFileSync(path.join(publicDir, "data", "snapshot.json"), '{"header":{"schema_version":1,"data_source":"sample"}}\n');
      await build({ root: web, publicDir, logLevel: "silent", build: { outDir, emptyOutDir: true } });
      const files = walk(outDir).map((f) => path.relative(outDir, f));
      expect(files).toContain("index.html");
      expect(files.filter((f) => f.startsWith("data"))).toEqual([]);
      expect(existsSync(path.join(outDir, "data"))).toBe(false);
    } finally {
      rmSync(publicDir, { recursive: true, force: true });
      rmSync(outDir, { recursive: true, force: true });
    }
  }, 60_000);
});
