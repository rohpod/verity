import type { ReactNode } from "react";
import { Note } from "@/components/ui";

export function ErrorScreen({ message }: { message: string }) {
  return (
    <main className="mx-auto max-w-xl p-4" role="alert">
      <h1 className="text-xl font-semibold">The snapshot could not be shown</h1>
      <Note tone="warn">{message}</Note>
    </main>
  );
}

export function Loading() {
  return <p className="p-4" role="status">Loading the snapshot…</p>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="my-2 rounded border border-dashed border-[var(--border)] p-3 text-sm text-[var(--muted-foreground)]">{children}</p>;
}

export function NotFound({ what }: { what: string }) {
  return <Empty>{what} is not in this snapshot.</Empty>;
}
