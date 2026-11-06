/** shadcn/ui-style primitives, written out in the repository so there is no generator to run.
 *  Plain Tailwind on the theme tokens in index.css. */
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const badge = cva("inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap", {
  variants: {
    tone: {
      neutral: "border-[var(--border)] bg-[var(--muted)] text-[var(--foreground)]",
      info: "border-blue-400 bg-blue-50 text-blue-900 dark:bg-blue-950 dark:text-blue-200",
      good: "border-green-500 bg-green-50 text-green-900 dark:bg-green-950 dark:text-green-200",
      warn: "border-amber-500 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
      bad: "border-red-500 bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-200",
      simulated: "border-purple-500 bg-purple-50 text-purple-900 dark:bg-purple-950 dark:text-purple-200",
    },
  },
  defaultVariants: { tone: "neutral" },
});
export type Tone = NonNullable<VariantProps<typeof badge>["tone"]>;

export function Badge({ tone, className, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return <span className={cn(badge({ tone }), className)} {...props} />;
}

export function Card({ title, children, className, id }: { title?: ReactNode; children: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={cn("rounded-lg border border-[var(--border)] p-4", className)}>
      {title ? <h2 className="mb-2 text-base font-semibold">{title}</h2> : null}
      {children}
    </section>
  );
}

export function Note({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "warn" }) {
  return (
    <p
      className={cn(
        "my-2 rounded border border-[var(--border)] p-2 text-sm",
        tone === "warn" ? "bg-[var(--warn-bg)] text-[var(--warn-fg)]" : "bg-[var(--muted)]",
      )}
    >
      {children}
    </p>
  );
}

export function Table({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="max-w-full overflow-x-auto">
      <table aria-label={label} className="w-full border-collapse text-left text-sm">
        {children}
      </table>
    </div>
  );
}
export function Th(props: ThHTMLAttributes<HTMLTableCellElement>) {
  return <th {...props} className={cn("border-b border-[var(--border)] px-2 py-1 font-semibold", props.className)} />;
}
export function Td(props: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td {...props} className={cn("border-b border-[var(--border)] px-2 py-1 align-top", props.className)} />;
}

export const Tabs = TabsPrimitive.Root;
export function TabsList(props: TabsPrimitive.TabsListProps) {
  return <TabsPrimitive.List {...props} className={cn("mb-3 flex flex-wrap gap-1 border-b border-[var(--border)]", props.className)} />;
}
export function TabsTrigger(props: TabsPrimitive.TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger
      {...props}
      className={cn("px-3 py-1.5 text-sm data-[state=active]:border-b-2 data-[state=active]:border-[var(--accent)] data-[state=active]:font-semibold", props.className)}
    />
  );
}
export const TabsContent = TabsPrimitive.Content;
