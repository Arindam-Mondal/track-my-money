import { useState } from 'react'
import type { Categoriser, Statement } from '../api'
import { maskAccount } from '../format'

type Props = {
  statements: Statement[]
  selectedId: number | null
  onSelect: (id: number) => void
  onDelete: (id: number) => void
  onCategorise: (id: number, redo: boolean) => void
  categoriser: Categoriser
}

export default function StatementList({ statements, selectedId, onSelect, onDelete, onCategorise, categoriser }: Props) {
  const [confirming, setConfirming] = useState<number | null>(null)

  if (statements.length === 0) {
    return (
      <section className="card">
        <h2>Statements</h2>
        <p className="empty">No statements yet. Upload a PDF to get started.</p>
      </section>
    )
  }

  return (
    <section className="card">
      <h2>Statements</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Bank</th>
              <th>Account</th>
              <th>Period</th>
              <th className="num">Transactions</th>
              <th>Categories</th>
              <th>Columns by</th>
              <th>Balance check</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {statements.map((statement) => (
              <tr
                key={statement.id}
                className={statement.id === selectedId ? 'selected' : undefined}
                onClick={() => onSelect(statement.id)}
              >
                <td>
                  <div>{statement.bank ?? 'Unknown bank'}</div>
                  <div className="sub" title={statement.filename}>
                    {statement.filename}
                  </div>
                </td>
                <td>{maskAccount(statement.account_number)}</td>
                <td>{statement.period ?? '—'}</td>
                <td className="num">{statement.transaction_count}</td>
                <td className="nowrap" onClick={(event) => event.stopPropagation()}>
                  <CategoryProgress
                    statement={statement}
                    categoriser={categoriser}
                    onCategorise={(redo) => onCategorise(statement.id, redo)}
                  />
                </td>
                <td>{statement.header_mapping ?? '—'}</td>
                <td className={statement.balance_check.startsWith('OK') ? 'ok' : 'warn'}>{statement.balance_check}</td>
                <td className="actions" onClick={(event) => event.stopPropagation()}>
                  {confirming === statement.id ? (
                    <>
                      <button type="button" className="danger" onClick={() => onDelete(statement.id)}>
                        Delete
                      </button>
                      <button type="button" onClick={() => setConfirming(null)}>
                        Keep
                      </button>
                    </>
                  ) : (
                    <button type="button" onClick={() => setConfirming(statement.id)}>
                      Delete…
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

const MODEL_NAME: Record<Categoriser, string> = { laya: 'Laya', jev: 'Jev' }

type ProgressProps = { statement: Statement; categoriser: Categoriser; onCategorise: (redo: boolean) => void }

/** Progress, and the only way to start categorising: a button for the model chosen in the switch. */
function CategoryProgress({ statement, categoriser, onCategorise }: ProgressProps) {
  const { categorised_count: done, transaction_count: total } = statement
  if (statement.categorising) {
    return (
      <span className="progress" role="status">
        <progress max={total} value={done} aria-label="Categorising" /> {done}/{total}
      </span>
    )
  }
  const model = MODEL_NAME[categoriser]
  return (
    <span className="progress">
      <span className={done === total ? 'ok' : done === 0 ? 'muted' : 'warn'}>
        {done === 0 ? 'not categorised' : `${done}/${total}`}
      </span>
      {done < total ? (
        <button type="button" onClick={() => onCategorise(false)}>
          Categorise with {model}
        </button>
      ) : (
        <button type="button" title="Categorise again; your manual choices are kept" onClick={() => onCategorise(true)}>
          Redo with {model}
        </button>
      )}
    </span>
  )
}
