import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** `not_met` -> `not met` */
export function words(value: string): string {
  return value.replace(/_/g, " ");
}

export function formatTime(iso: string): string {
  return iso.replace("T", " ").replace(/\.\d+/, "").replace("Z", " UTC");
}

export function count<T>(items: Iterable<T>, key: (item: T) => string): [string, number][] {
  const totals = new Map<string, number>();
  for (const item of items) totals.set(key(item), (totals.get(key(item)) ?? 0) + 1);
  return [...totals].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1));
}
