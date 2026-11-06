// @vitest-environment node
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import type { UserConfig, UserConfigExport } from "vite";
import config from "../../vite.config";
import { checkSnapshot, snapshotUrl, SnapshotError } from "@/data/loader";

const src = path.resolve(__dirname, "..");

/** The Vite config as a build resolves it. */
async function resolve(): Promise<UserConfig> {
  const raw = config as unknown as UserConfigExport;
  return typeof raw === "function" ? await raw({ command: "build", mode: "production" }) : await raw;
}

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? files(full) : [full];
  });
}

const app = files(src).filter((f) => /\.(ts|tsx)$/.test(f) && !f.includes(`${path.sep}test${path.sep}`) && !/\.test\.tsx?$/.test(f));

describe("one data path (ADR 0031, decision 2)", () => {
  it("has no fetch outside the loader", () => {
    const offenders = app.filter((f) => !f.endsWith(path.join("data", "loader.ts")) && /\bfetch\s*\(/.test(readFileSync(f, "utf-8")));
    expect(offenders).toEqual([]);
  });

  it("imports no snapshot file, from the app or from outside it", () => {
    const offenders = app.filter((f) => /from\s+["'][^"']*(snapshot\.json|mini-snapshot|\.fixture)/.test(readFileSync(f, "utf-8")) || /import\(["'][^"']*snapshot\.json/.test(readFileSync(f, "utf-8")));
    expect(offenders).toEqual([]);
  });

  it("loads the snapshot from a path under the base URL", () => {
    expect(snapshotUrl()).toBe(`${import.meta.env.BASE_URL}data/snapshot.json`);
    expect(snapshotUrl().endsWith("data/snapshot.json")).toBe(true);
  });

  it("refuses a schema version other than 1", () => {
    expect(() => checkSnapshot({ header: { schema_version: 2 } })).toThrow(SnapshotError);
    expect(() => checkSnapshot({})).toThrow(SnapshotError);
    expect(() => checkSnapshot(null)).toThrow(SnapshotError);
    expect(checkSnapshot({ header: { schema_version: 1 } })).toBeTruthy();
  });

  it("sets a Content-Security-Policy that allows connections to the page's own origin only", () => {
    const html = readFileSync(path.resolve(src, "../index.html"), "utf-8");
    expect(html).toMatch(/Content-Security-Policy/);
    expect(html).toMatch(/connect-src 'self'/);
    expect(html).not.toMatch(/https?:\/\//);
  });

  it("loads no CDN, font host or analytics", () => {
    const text = [...app, path.resolve(src, "index.css")].map((f) => readFileSync(f, "utf-8")).join("\n");
    expect(text).not.toMatch(/https?:\/\/(fonts|cdn|www\.google|unpkg|cdnjs)/i);
  });
});

describe("the fixture cannot reach the publish path (ADR 0031, decision 3)", () => {
  it("serves the fixture in development only", async () => {
    const resolved = await resolve();
    const plugin = (resolved.plugins ?? []).flat().find((p) => p && typeof p === "object" && "name" in p && p.name === "verity-dev-fixture");
    expect(plugin).toBeTruthy();
    expect((plugin as { apply?: string }).apply).toBe("serve");
  });

  it("uses a relative base for Pages and preview", async () => {
    const resolved = await resolve();
    expect(resolved.base).toBe("./");
  });
});
