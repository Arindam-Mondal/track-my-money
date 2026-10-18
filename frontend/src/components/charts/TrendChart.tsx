import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Direction, TrendPoint } from '../../api'
import { formatCompactRupees, formatMonth, formatRupees } from '../../format'
import { BAR_SIZE, COLORS, axisTick, tooltipStyle } from './chartStyle'

/** One category's monthly totals: a single series in its direction's color. */
export default function TrendChart({ points, direction }: { points: TrendPoint[]; direction: Direction }) {
  const data = points.map((p) => ({ month: formatMonth(p.month), total: Number(p.total) }))
  if (data.length === 0) return <p className="empty">No transactions in this category yet.</p>

  return (
    <figure className="chart">
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid vertical={false} stroke={COLORS.grid} />
          <XAxis dataKey="month" tick={axisTick} tickLine={false} axisLine={{ stroke: COLORS.grid }} />
          <YAxis tick={axisTick} tickLine={false} axisLine={false} tickFormatter={formatCompactRupees} width={64} />
          <Tooltip {...tooltipStyle} formatter={(value) => [formatRupees(Number(value)), 'Total']} />
          <Bar dataKey="total" fill={COLORS[direction]} maxBarSize={BAR_SIZE} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  )
}
