import type { Statement, Transaction } from '../api'
import { formatAmount, formatDate } from '../format'

type Props = {
  statement: Statement
  transactions: Transaction[] | null // null while loading
}

export default function TransactionTable({ statement, transactions }: Props) {
  const totals = (transactions ?? []).reduce(
    (sum, t) => ({ debit: sum.debit + Number(t.debit), credit: sum.credit + Number(t.credit) }),
    { debit: 0, credit: 0 },
  )

  return (
    <section className="card">
      <h2>
        {statement.bank ?? 'Statement'} <span className="sub">{statement.period}</span>
      </h2>
      {transactions === null ? (
        <p className="empty">Loading…</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Particulars</th>
                <th className="num">Debit</th>
                <th className="num">Credit</th>
                <th className="num">Balance</th>
                <th>Other</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr key={t.row_index}>
                  <td className="nowrap">{formatDate(t.date)}</td>
                  <td>{t.particulars}</td>
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
                <td colSpan={2}>{transactions.length} transactions</td>
                <td className="num debit">{formatAmount(totals.debit.toFixed(2))}</td>
                <td className="num credit">{formatAmount(totals.credit.toFixed(2))}</td>
                <td colSpan={2} />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  )
}
