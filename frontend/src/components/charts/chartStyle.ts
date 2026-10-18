// Shared chart styling. Colors are CSS variables from index.css, so light and dark mode swap in one place.
// Money in and money out keep the same color on every chart (in = slot 1 blue, out = slot 2 orange).

export const COLORS = {
  in: 'var(--series-in)',
  out: 'var(--series-out)',
  net: 'var(--series-net)',
  grid: 'var(--grid)',
  axis: 'var(--muted)',
  surface: 'var(--surface)',
} as const

export const BAR_SIZE = 24 // thin marks: never fill the slot

export const axisTick = { fill: COLORS.axis, fontSize: 12 }

export const tooltipStyle = {
  contentStyle: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text)',
    fontSize: 13,
  },
  labelStyle: { color: 'var(--text)', fontWeight: 600 },
  itemStyle: { color: 'var(--text)' },
  cursor: { fill: 'var(--row-hover)' },
} as const
