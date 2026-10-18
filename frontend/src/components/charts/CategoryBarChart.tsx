import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CategoryTotal, Direction } from '../../api'
import { formatRupees } from '../../format'
import { BAR_SIZE, COLORS, axisTick, tooltipStyle } from './chartStyle'

type Props = {
  totals: CategoryTotal[]
  direction: Direction
  onSelect: (category: string) => void
}

/** Totals by category, largest first: one series, so one color (the direction's) and no legend. */
export default function CategoryBarChart({ totals, direction, onSelect }: Props) {
  const sum = totals.reduce((acc, t) => acc + Number(t.total), 0)
  const data = totals.map((t) => ({
    category: t.category,
    total: Number(t.total),
    count: t.count,
    label: `${formatRupees(Number(t.total))} · ${sum ? Math.round((Number(t.total) / sum) * 100) : 0}%`,
  }))

  if (data.length === 0) return <p className="empty">Nothing in this period.</p>

  return (
    <figure className="chart">
      <ResponsiveContainer width="100%" height={data.length * 34 + 16}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 128, bottom: 4, left: 8 }}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="category"
            width={190}
            tick={axisTick}
            tickLine={false}
            axisLine={{ stroke: COLORS.grid }}
            interval={0}
          />
          <Tooltip
            {...tooltipStyle}
            formatter={(value, _name, item) => [
              `${formatRupees(Number(value))} in ${item.payload.count} transaction${item.payload.count === 1 ? '' : 's'}`,
              'Total',
            ]}
          />
          <Bar
            dataKey="total"
            fill={COLORS[direction]}
            maxBarSize={BAR_SIZE}
            radius={[0, 4, 4, 0]}
            cursor="pointer"
            onClick={(entry) => onSelect(String(entry.payload?.category ?? ''))}
          >
            <LabelList dataKey="label" position="right" className="bar-label" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </figure>
  )
}
