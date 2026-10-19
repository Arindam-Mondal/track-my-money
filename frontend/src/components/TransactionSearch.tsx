import { useEffect, useMemo, useState } from 'react'
import {
  type Categories,
  type Direction,
  type SearchResult,
  type SearchRow,
  type Statement,
  searchTransactions,
  setCategoryForMany,
  type Transaction,
} from '../api'
import { formatAmount, formatDate, maskAccount } from '../format'
import CategoryCell from './CategoryCell'

type Props = {
  categories: Categories | null
  statements: Statement[]
  version: number // bumped when categories changed elsewhere (e.g. rules applied): search again
  onChanged: () => void // categories changed: refresh statement progress
}

const UNCATEGORISED = 'Uncategorised'

function directionOf(row: Transaction): Direction {
  return Number(row.debit) > 0 ? 'out' : 'in'
}

/** Search every transaction (any column), select the results and set one category for all of them. */
export default function TransactionSearch({ categories, statements, version: outsideVersion, onChanged }: Props) {
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('') // debounced
  const [direction, setDirection] = useState<Direction | ''>('')
  const [category, setCategory] = useState('')
  const [statementId, setStatementId] = useState('')
  const [result, setResult] = useState<SearchResult | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [bulkCategory, setBulkCategory] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: 'ok' | 'bad'; text: string } | null>(null)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    const timer = setTimeout(() => setQuery(q), 300)
    return () => clearTimeout(timer)
  }, [q])

  useEffect(() => {
    let current = true
    searchTransactions({
      q: query,
      direction: direction || undefined,
      category: category || undefined,
      statementId: statementId ? Number(statementId) : undefined,
    })
      .then((r) => {
        if (!current) return
        setResult(r)
        setSelected(new Set())
      })
      .catch((e: Error) => current && setMessage({ kind: 'bad', text: e.message }))
    return () => {
      current = false
    }
  }, [query, direction, category, statementId, version, outsideVersion])

  const rows = useMemo(() => result?.transactions ?? [], [result])
  const selectedRows = rows.filter((r) => selected.has(r.id))
  const selectedDirections = new Set(selectedRows.map(directionOf))
  const bulkDirection = selectedDirections.size === 1 ? [...selectedDirections][0] : null
  const allSelected = rows.length > 0 && selected.size === rows.length

  function toggle(id: number) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function applyBulk() {
    if (!bulkCategory || selected.size === 0) return
    setBusy(true)
    setMessage(null)
    try {
      const { updated } = await setCategoryForMany([...selected], bulkCategory)
      setMessage({ kind: 'ok', text: `Set "${bulkCategory}" on ${updated} transaction${updated === 1 ? '' : 's'}.` })
      setBulkCategory('')
      setVersion((v) => v + 1)
      onChanged()
    } catch (e) {
      setMessage({ kind: 'bad', text: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  function rowChanged(updated: Transaction) {
    setResult((r) => r && { ...r, transactions: r.transactions.map((t) => (t.id === updated.id ? { ...t, ...updated } : t)) })
    onChanged()
  }

  return (
    <section className="card">
      <h2>Search transactions</h2>
      <div className="search-bar">
        <input
          type="search"
          className="search-input"
          placeholder="Search any column: SBIMF, 1,000, 2026-05, 05-04-2026, State Bank…"
          aria-label="Search transactions"
          value={q}
          onChange={(event) => setQ(event.target.value)}
        />
        <select aria-label="Direction" value={direction} onChange={(e) => setDirection(e.target.value as Direction | '')}>
          <option value="">Money in and out</option>
          <option value="out">Money out</option>
          <option value="in">Money in</option>
        </select>
        <select aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          <option value={UNCATEGORISED}>Uncategorised</option>
          {categories &&
            (['out', 'in'] as const).map((d) => (
              <optgroup key={d} label={d === 'out' ? 'Money out' : 'Money in'}>
                {categories[d].map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </optgroup>
            ))}
        </select>
        <select aria-label="Statement" value={statementId} onChange={(e) => setStatementId(e.target.value)}>
          <option value="">All accounts</option>
          {statements.map((s) => (
            <option key={s.id} value={s.id}>
              {s.bank ?? 'Statement'} {maskAccount(s.account_number)}
            </option>
          ))}
        </select>
      </div>

      <div className="bulk-bar" aria-live="polite">
        <span>
          {result === null
            ? 'Searching…'
            : `${result.total} match${result.total === 1 ? '' : 'es'}${result.total > rows.length ? `, showing ${rows.length}` : ''}`}
          {selected.size > 0 && <strong> · {selected.size} selected</strong>}
        </span>
        {selected.size > 0 &&
          (bulkDirection ? (
            <span className="bulk-action">
              <select aria-label="Category for the selected transactions" value={bulkCategory} onChange={(e) => setBulkCategory(e.target.value)}>
                <option value="">Set category…</option>
                {categories?.[bulkDirection].map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
              <button type="button" className="primary" disabled={!bulkCategory || busy} onClick={() => void applyBulk()}>
                {busy ? 'Saving…' : `Apply to ${selected.size}`}
              </button>
            </span>
          ) : (
            <span className="warn-text">
              The selection has money in and money out, which use different categories. Filter by direction first.
            </span>
          ))}
        {message && <span className={message.kind === 'ok' ? 'ok' : 'bad'}>{message.text}</span>}
      </div>

      {rows.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th className="check">
                  <input
                    type="checkbox"
                    aria-label="Select all results"
                    checked={allSelected}
                    onChange={() => setSelected(allSelected ? new Set() : new Set(rows.map((r) => r.id)))}
                  />
                </th>
                <th>Date</th>
                <th>Account</th>
                <th>Particulars</th>
                <th>Category</th>
                <th className="num">Debit</th>
                <th className="num">Credit</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t: SearchRow) => (
                <tr key={t.id} className={selected.has(t.id) ? 'selected' : undefined}>
                  <td className="check">
                    <input type="checkbox" aria-label={`Select ${t.particulars}`} checked={selected.has(t.id)} onChange={() => toggle(t.id)} />
                  </td>
                  <td className="nowrap">{formatDate(t.date)}</td>
                  <td className="nowrap sub">
                    {t.bank ?? '—'} {t.account_last4 ? `•••• ${t.account_last4}` : ''}
                  </td>
                  <td>{t.particulars}</td>
                  <td>
                    <CategoryCell transaction={t} categories={categories} onChanged={rowChanged} />
                  </td>
                  <td className="num debit">{formatAmount(t.debit)}</td>
                  <td className="num credit">{formatAmount(t.credit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {result !== null && rows.length === 0 && <p className="empty">No transactions match.</p>}
    </section>
  )
}
