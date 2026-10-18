const amountFormat = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const rupeeFormat = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const compactFormat = new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 })
const monthFormat = new Intl.DateTimeFormat('en-IN', { month: 'short', year: '2-digit' })

/** 25000 -> "₹25,000" (whole rupees, for totals). */
export function formatRupees(value: number): string {
  return rupeeFormat.format(value)
}

/** 2500000 -> "₹25L" (axis ticks). */
export function formatCompactRupees(value: number): string {
  return `₹${compactFormat.format(value)}`
}

/** "2026-04" -> "Apr 26". */
export function formatMonth(month: string): string {
  const [year, number] = month.split('-').map(Number)
  return monthFormat.format(new Date(year, number - 1, 1))
}
const dateFormat = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })

/** "85000.00" -> "85,000.00"; zero or missing -> "" so empty debit/credit cells stay blank. */
export function formatAmount(value: string | null): string {
  if (value === null) return ''
  const number = Number(value)
  return number === 0 ? '' : amountFormat.format(number)
}

/** "2024-04-01" -> "01 Apr 2024" (parsed as a calendar date, not shifted by time zone). */
export function formatDate(value: string): string {
  const [year, month, day] = value.split('-').map(Number)
  return dateFormat.format(new Date(year, month - 1, day))
}

/** "923010012345678" -> "•••• 5678". */
export function maskAccount(value: string | null): string {
  if (!value) return '—'
  return value.length > 4 ? `•••• ${value.slice(-4)}` : value
}
