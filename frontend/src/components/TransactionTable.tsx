import { useState } from 'react'
import type { Categories, Statement, Transaction } from '../api'
import { formatAmount, formatDate } from '../format'
import CategoryCell from './CategoryCell'

type Props = {
  statement: Statement
  transactions: Transaction[] | null // null while loading
  categories: Categories | null
  onTransactionChanged: (updated: Transaction) => void
}

/** Wrap placeholders like [PERSON_7F3A] so they stand out in the masked text. */
function MaskedText({ text }: { text: string | null }) {
  if (text === null) return <span className="sub">not masked yet</span>
  return (
    <>
      {text.split(/(\[[^\]]+\])/).map((part, i) =>
        part.startsWith('[') ? (
          <mark key={i} className="placeholder">
            {part}
          </mark>
        ) : (
          part
        ),
      )}
    </>
  )
}

export default function TransactionTable({ statement, transactions, categories, onTransactionChanged }: Props) {
  const [showMasked, setShowMasked] = useState(false)
  const totals = (transactions ?? []).reduce(
    (sum, t) => ({ debit: sum.debit + Number(t.debit), credit: sum.credit + Number(t.credit) }),
    { debit: 0, credit: 0 },
  )
  const columns = showMasked ? 8 : 7

  return (
    <section className="card">
      <h2 className="with-control">
        <span>
          {statement.bank ?? 'Statement'} <span className="sub">{statement.period}</span>
        </span>
        <label className="toggle">
          <input type="checkbox" checked={showMasked} onChange={(event) => setShowMasked(event.target.checked)} />
          Show what Jev sees
        </label>
      </h2>
      {showMasked && (
        <p className="hint">
          The <strong>Masked</strong> column is the only narration text sent to Jev. People become{' '}
          <mark className="placeholder">[PERSON_…]</mark>, other names <mark className="placeholder">[NAME_…]</mark>, and
          numbers, UPI IDs, accounts and places are replaced. The same name always gets the same token.
        </p>
      )}
      {transactions === null ? (
        <p className="empty">Loading…</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Particulars</th>
                {showMasked && <th>Masked (sent to Jev)</th>}
                <th>Category</th>
                <th className="num">Debit</th>
                <th className="num">Credit</th>
                <th className="num">Balance</th>
                <th>Other</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr key={t.id}>
                  <td className="nowrap">{formatDate(t.date)}</td>
                  <td>{t.particulars}</td>
                  {showMasked && (
                    <td className="masked">
                      <MaskedText text={t.particulars_masked} />
                    </td>
                  )}
                  <td>
                    <CategoryCell transaction={t} categories={categories} onChanged={onTransactionChanged} />
                  </td>
                  <td className="num debit">{formatAmount(t.debit)}</td>
                  <td className="num credit">{formatAmount(t.credit)}</td>
                  <td className="num">{formatAmount(t.balance)}</td>
                  <td className="sub">
                    {Object.entries(t.extra)
                      .map(([key, value]) => `${key}: ${value}`)
                      .join(' · ')}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={showMasked ? 4 : 3}>{transactions.length} transactions</td>
                <td className="num debit">{formatAmount(totals.debit.toFixed(2))}</td>
                <td className="num credit">{formatAmount(totals.credit.toFixed(2))}</td>
                <td colSpan={columns - (showMasked ? 6 : 5)} />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  )
}
