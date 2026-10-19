import { useEffect, useState } from 'react'
import {
  type Categories,
  type CategoryTotal,
  type Direction,
  type FlowFilters,
  getCategoryTotals,
  getMonthlyFlow,
  getTrend,
  type MonthlyFlow,
  type TrendPoint,
} from '../api'
import { formatRupees } from '../format'
import CategoryBarChart from './charts/CategoryBarChart'
import MonthlyFlowChart from './charts/MonthlyFlowChart'
import TrendChart from './charts/TrendChart'

type Props = { categories: Categories | null; version: number } // version: bumped when categories change

const PASS_THROUGH = 'Pass-through' // manual-only category, never counted in Money flow

/** How money moves: totals for the period, monthly in vs out, totals by category, one category's trend. */
export default function MoneyFlow({ categories, version }: Props) {
  const [filters, setFilters] = useState<FlowFilters>({ excludeSelf: true })
  const [monthly, setMonthly] = useState<MonthlyFlow[]>([])
  const [spending, setSpending] = useState<CategoryTotal[]>([])
  const [income, setIncome] = useState<CategoryTotal[]>([])
  const [trendCategory, setTrendCategory] = useState('Food & Dining')
  const [trend, setTrend] = useState<TrendPoint[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let current = true
    Promise.all([getMonthlyFlow(filters), getCategoryTotals('out', filters), getCategoryTotals('in', filters)])
      .then(([m, out, inc]) => {
        if (!current) return
        setMonthly(m)
        setSpending(out)
        setIncome(inc)
        setError(null)
      })
      .catch((e: Error) => current && setError(e.message))
    return () => {
      current = false
    }
  }, [filters, version])

  useEffect(() => {
    let current = true
    getTrend(trendCategory, filters)
      .then((points) => current && setTrend(points))
      .catch((e: Error) => current && setError(e.message))
    return () => {
      current = false
    }
  }, [trendCategory, filters, version])

  const totalIn = monthly.reduce((sum, m) => sum + Number(m.money_in), 0)
  const totalOut = monthly.reduce((sum, m) => sum + Number(m.money_out), 0)
  const trendDirection: Direction = categories?.in.some((c) => c.name === trendCategory) ? 'in' : 'out'
  const uncategorised = [...spending, ...income].find((t) => t.category === 'Uncategorised')

  function selectTrend(category: string) {
    if (category && category !== 'Uncategorised') {
      setTrendCategory(category)
      document.getElementById('trend')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  return (
    <div className="flow">
      <section className="card filters" aria-label="Period and filters">
        <label>
          From
          <input
            type="month"
            value={filters.from ?? ''}
            onChange={(event) => setFilters({ ...filters, from: event.target.value || undefined })}
          />
        </label>
        <label>
          To
          <input
            type="month"
            value={filters.to ?? ''}
            onChange={(event) => setFilters({ ...filters, to: event.target.value || undefined })}
          />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={filters.excludeSelf}
            onChange={(event) => setFilters({ ...filters, excludeSelf: event.target.checked })}
          />
          Leave out transfers between my own accounts
        </label>
        <span className="hint">Pass-through is never counted.</span>
      </section>

      {error && (
        <p className="banner" role="alert">
          {error}
        </p>
      )}

      <section className="tiles">
        <Tile label="Money in" value={totalIn} swatch="in" />
        <Tile label="Money out" value={totalOut} swatch="out" />
        <Tile label="Net" value={totalIn - totalOut} swatch="net" />
      </section>

      {uncategorised && (
        <p className="note">
          {uncategorised.count} transactions are not categorised yet. Categorise them on the Statements tab to complete
          these figures.
        </p>
      )}

      <section className="card">
        <h2>Money in vs out by month</h2>
        {monthly.length ? <MonthlyFlowChart flows={monthly} /> : <p className="empty">No transactions in this period.</p>}
      </section>

      <div className="pair">
        <section className="card">
          <h2>
            Spending by category <span className="sub">click a bar to see its trend</span>
          </h2>
          <CategoryBarChart totals={spending} direction="out" onSelect={selectTrend} />
        </section>
        <section className="card">
          <h2>
            Income by category <span className="sub">click a bar to see its trend</span>
          </h2>
          <CategoryBarChart totals={income} direction="in" onSelect={selectTrend} />
        </section>
      </div>

      <section className="card" id="trend">
        <h2 className="with-control">
          Trend
          <select aria-label="Category" value={trendCategory} onChange={(event) => setTrendCategory(event.target.value)}>
            {categories &&
              (['out', 'in'] as const).map((direction) => (
                <optgroup key={direction} label={direction === 'out' ? 'Money out' : 'Money in'}>
                  {categories[direction]
                    .filter((c) => c.name !== PASS_THROUGH)
                    .map((c) => (
                      <option key={c.name} value={c.name}>
                        {c.name}
                      </option>
                    ))}
                </optgroup>
              ))}
          </select>
        </h2>
        <TrendChart points={trend} direction={trendDirection} />
      </section>
    </div>
  )
}

function Tile({ label, value, swatch }: { label: string; value: number; swatch: 'in' | 'out' | 'net' }) {
  return (
    <div className="card tile">
      <div className="tile-label">
        <span className={`swatch ${swatch}`} aria-hidden="true" />
        {label}
      </div>
      <div className="tile-value">{formatRupees(value)}</div>
    </div>
  )
}
