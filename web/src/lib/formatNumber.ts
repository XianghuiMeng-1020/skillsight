/**
 * Uniform display: two decimal places (product requirement).
 * Use for scores, percentages, counts, and other numeric UI.
 */
export function fmt2(n: number): string {
  if (typeof n !== 'number' || Number.isNaN(n)) return '0.00';
  return n.toFixed(2);
}

export function fmtInt(n: number): string {
  if (typeof n !== 'number' || Number.isNaN(n)) return '0';
  return String(Math.round(n));
}
