import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "@/App";
import { SnapshotIndex } from "@/data/index";
import { SnapshotProvider } from "@/data/provider";
import type { Snapshot } from "@/data/types";

const root = path.resolve(__dirname, "../..");

/** Test files read snapshots from disk. The app never does (ADR 0031, decision 2). */
export function readJson<T>(file: string): T {
  return JSON.parse(readFileSync(file, "utf-8")) as T;
}

export const MINI_FILE = path.join(root, "src/test/mini-snapshot.json");
export const EXPECTED_FILE = path.join(root, "src/test/mini-expected.json");
export const MINI_AUDIT_FILE = path.join(root, "src/test/mini-audit.json");
export const FIXTURE_FILE = path.join(root, ".fixture/snapshot.json");
export const PARITY_FILE = path.join(root, ".fixture/audit-parity.json");

let fixtureIndex: SnapshotIndex | undefined;
let miniIndex: SnapshotIndex | undefined;

export function fixture(): SnapshotIndex {
  if (!existsSync(FIXTURE_FILE)) throw new Error("web/.fixture/snapshot.json is missing: run `npm run fixture` first.");
  fixtureIndex ??= new SnapshotIndex(readJson<Snapshot>(FIXTURE_FILE));
  return fixtureIndex;
}

export function mini(): SnapshotIndex {
  miniIndex ??= new SnapshotIndex(readJson<Snapshot>(MINI_FILE));
  return miniIndex;
}

export function renderRoute(index: SnapshotIndex, url: string) {
  return render(
    <SnapshotProvider index={index}>
      <MemoryRouter initialEntries={[url]}>
        <AppRoutes />
      </MemoryRouter>
    </SnapshotProvider>,
  );
}

export const ROUTES = ["/", "/registry", "/risks", "/crosswalk", "/controls", "/graph", "/about"] as const;
