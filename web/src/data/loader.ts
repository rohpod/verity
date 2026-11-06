/** The only place the dashboard fetches data (ADR 0031, decision 2). A test fails if any other
 *  file calls `fetch`, or imports a snapshot. */
import type { Snapshot } from "./types";

export const SUPPORTED_SCHEMA_VERSION = 1;

export class SnapshotError extends Error {}

export function snapshotUrl(): string {
  return `${import.meta.env.BASE_URL}data/snapshot.json`;
}

/** Refuses a file that is not the snapshot this build understands, with a message a person can
 *  act on. Never shows a value from the file. */
export function checkSnapshot(data: unknown): Snapshot {
  const header = (data as { header?: { schema_version?: unknown } } | null)?.header;
  if (!header || typeof header !== "object") {
    throw new SnapshotError("The data file is not a Verity snapshot: it has no header.");
  }
  if (header.schema_version !== SUPPORTED_SCHEMA_VERSION) {
    throw new SnapshotError(
      `This dashboard reads snapshot schema version ${SUPPORTED_SCHEMA_VERSION}, ` +
        "and the data file is a different version. It was not loaded.",
    );
  }
  return data as Snapshot;
}

export async function loadSnapshot(signal?: AbortSignal): Promise<Snapshot> {
  let response: Response;
  try {
    response = await fetch(snapshotUrl(), { signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new SnapshotError("The snapshot could not be fetched.");
  }
  if (!response.ok) {
    throw new SnapshotError(`The snapshot could not be fetched (HTTP ${response.status}).`);
  }
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new SnapshotError("The data file is not valid JSON.");
  }
  return checkSnapshot(data);
}
