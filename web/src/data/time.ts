/** Orders two ISO-8601 timestamps as Python orders the datetimes. Plain string comparison is not
 *  enough: the snapshot omits a zero fraction, so `…:00Z` and `…:00.5Z` would sort wrongly. */
export function timeKey(iso: string): [number, string] {
  const match = /\.(\d+)/.exec(iso);
  const fraction = (match?.[1] ?? "").padEnd(9, "0");
  return [Date.parse(iso.replace(/\.\d+/, "")), fraction];
}

export function compareTime(a: string, b: string): number {
  const [ma, fa] = timeKey(a);
  const [mb, fb] = timeKey(b);
  return ma - mb || (fa < fb ? -1 : fa > fb ? 1 : 0);
}

export function compareText(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}
