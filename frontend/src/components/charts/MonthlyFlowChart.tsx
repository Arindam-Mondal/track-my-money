import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { MonthlyFlow } from '../../api'
import { formatCompactRupees, formatMonth, formatRupees } from '../../format'
import { axisTick, BAR_SIZE, COLORS, tooltipStyle } from './chartStyle'

const LABELS: Record<string, string> = { money_in: 'Money in', money_out: 'Money out', net: 'Net' }

/** Money in vs out per month (grouped columns) with the net as a line, all on one rupee axis. */
export default function MonthlyFlowChart({ flows }: { flows: MonthlyFlow[] }) {
  const data = flows.map((f) => ({
    month: formatMonth(f.month),
    money_in: Number(f.money_in),
    money_out: Number(f.money_out),
    net: Number(f.net),
  }))

  return (
    <figure className="chart">
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }} barGap={2}>
          <CartesianGrid vertical={false} stroke={COLORS.grid} />
          <XAxis dataKey="month" tick={axisTick} tickLine={false} axisLine={{ stroke: COLORS.grid }} />
          <YAxis tick={axisTick} tickLine={false} axisLine={false} tickFormatter={formatCompactRupees} width={64} />
          <ReferenceLine y={0} stroke={COLORS.axis} />
          <Tooltip
            {...tooltipStyle}
            formatter={(value, name) => [formatRupees(Number(value)), LABELS[String(name)] ?? name]}
          />
          <Legend formatter={(name) => <span className="legend-text">{LABELS[name] ?? name}</span>} />
          <Bar dataKey="money_in" fill={COLORS.in} maxBarSize={BAR_SIZE} radius={[4, 4, 0, 0]} />
          <Bar dataKey="money_out" fill={COLORS.out} maxBarSize={BAR_SIZE} radius={[4, 4, 0, 0]} />
          <Line
            dataKey="net"
            stroke={COLORS.net}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            dot={{ r: 4, fill: COLORS.net, stroke: COLORS.surface, strokeWidth: 2 }}
            activeDot={{ r: 5, fill: COLORS.net, stroke: COLORS.surface, strokeWidth: 2 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
      <details className="table-view">
        <summary>Show as a table</summary>
        <table>
          <thead>
            <tr>
              <th>Month</th>
              <th className="num">Money in</th>
              <th className="num">Money out</th>
              <th className="num">Net</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.month}>
                <td>{row.month}</td>
                <td className="num">{formatRupees(row.money_in)}</td>
                <td className="num">{formatRupees(row.money_out)}</td>
                <td className="num">{formatRupees(row.net)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  )
}
