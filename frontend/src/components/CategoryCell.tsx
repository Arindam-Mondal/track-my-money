import { useState } from 'react'
import { type Categories, setCategory, type Transaction } from '../api'

type Props = {
  transaction: Transaction
  categories: Categories | null
  onChanged: (updated: Transaction) => void
}

/** A transaction's category: a dropdown limited to its direction, plus who set it (Laya or you). */
export default function CategoryCell({ transaction, categories, onChanged }: Props) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const direction = Number(transaction.debit) > 0 ? 'out' : 'in'
  const options = categories?.[direction] ?? []

  async function change(category: string) {
    setSaving(true)
    setError(null)
    try {
      onChanged(await setCategory(transaction.id, category))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="category-cell">
      <select
        aria-label={`Category for ${transaction.particulars}`}
        value={transaction.category ?? ''}
        disabled={saving || options.length === 0}
        onChange={(event) => void change(event.target.value)}
      >
        {transaction.category === null && <option value="">Uncategorised</option>}
        {options.map((option) => (
          <option key={option.name} value={option.name} title={option.description}>
            {option.name}
          </option>
        ))}
      </select>
      {transaction.category_source === 'manual' && <span className="tag">manual</span>}
      {transaction.category_source === 'laya' && transaction.category_confidence !== null && (
        <span className="tag" title="Laya's confidence. It runs high, so treat it as a rough guide.">
          Laya {Math.round(transaction.category_confidence * 100)}%
        </span>
      )}
      {error && <span className="tag bad">{error}</span>}
    </div>
  )
}
