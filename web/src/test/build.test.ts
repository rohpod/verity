// @vitest-environment node
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { build } from "vite";

const web = path.resolve(__dirname, "../..");
const publicData = path.join(web, "public", "data");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

describe("a build carries nothing from web/public/ (ADR 0031, decision 3)", () => {
  it("leaves a committed snapshot out of dist/", async () => {
    // The reviewed live snapshot lives in web/public/data/. If a build copied it, `check:dist`
    // would fail in CI and Pages once it is committed. Use a sample file, and remove it again.
    if (existsSync(publicData)) throw new Error("web/public/data already exists: not touching it");
    const publicDir = path.join(web, "public");
    const madePublic = !existsSync(publicDir);
    const outDir = mkdtempSync(path.join(os.tmpdir(), "verity-build-"));
    try {
      mkdirSync(publicData, { recursive: true });
      writeFileSync(path.join(publicData, "snapshot.json"), '{"header":{"schema_version":1,"data_source":"sample"}}\n');
      await build({ root: web, logLevel: "silent", build: { outDir, emptyOutDir: true } });
      const files = walk(outDir).map((f) => path.relative(outDir, f));
      expect(files).toContain("index.html");
      expect(files.filter((f) => f.startsWith("data"))).toEqual([]);
      expect(existsSync(path.join(outDir, "data"))).toBe(false);
    } finally {
      rmSync(publicData, { recursive: true, force: true });
      if (madePublic) rmSync(publicDir, { recursive: true, force: true });
      rmSync(outDir, { recursive: true, force: true });
    }
  }, 60_000);
});
