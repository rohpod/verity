import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { SnapshotIndex } from "./index";
import { SnapshotError, loadSnapshot } from "./loader";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; index: SnapshotIndex };

const Context = createContext<State>({ status: "loading" });

/** Loads the snapshot once and builds the indexes once. Tests can pass a ready index. */
export function SnapshotProvider({ children, index }: { children: ReactNode; index?: SnapshotIndex }) {
  const [state, setState] = useState<State>(index ? { status: "ready", index } : { status: "loading" });
  useEffect(() => {
    if (index) return;
    const controller = new AbortController();
    loadSnapshot(controller.signal)
      .then((snapshot) => setState({ status: "ready", index: new SnapshotIndex(snapshot) }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof SnapshotError ? error.message : "The snapshot could not be loaded.";
        setState({ status: "error", message });
      });
    return () => controller.abort();
  }, [index]);
  const value = useMemo(() => state, [state]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useSnapshotState(): State {
  return useContext(Context);
}

/** For pages under the shell, which renders only once the snapshot is ready. */
export function useIndex(): SnapshotIndex {
  const state = useContext(Context);
  if (state.status !== "ready") throw new Error("useIndex needs a loaded snapshot");
  return state.index;
}
