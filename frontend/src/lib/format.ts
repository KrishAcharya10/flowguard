// Display helpers. The API stores UTC; the UI displays Asia/Kolkata.
const IST = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
})

export function fmtTime(iso?: string | null): string {
  if (!iso) return '-'
  return IST.format(new Date(iso)) + ' IST'
}

/** ETAs are displayed rounded to 5 minutes (they are estimates, not measurements). */
export function fmtEta(iso?: string | null): string {
  if (!iso) return '-'
  const ms = 5 * 60 * 1000
  return IST.format(new Date(Math.round(new Date(iso).getTime() / ms) * ms)) + ' IST'
}

/** Probabilities are displayed as whole percent (Monte Carlo error is up to ~2.2 points at N=500). */
export function pct(x?: number | null): string {
  return x === null || x === undefined ? 'n/a' : `${Math.round(x * 100)}%`
}

export function rs(x?: number | null): string {
  return x === null || x === undefined ? '-' : `Rs ${Math.round(x).toLocaleString('en-IN')}`
}

export function hrs(x?: number | null, digits = 1): string {
  return x === null || x === undefined ? '-' : `${x.toFixed(digits)} h`
}

export function hoursBetween(a: string, b: string): number {
  return (new Date(a).getTime() - new Date(b).getTime()) / 3600000
}

export function signed(x: number, digits = 1): string {
  return `${x >= 0 ? '+' : ''}${x.toFixed(digits)}`
}
