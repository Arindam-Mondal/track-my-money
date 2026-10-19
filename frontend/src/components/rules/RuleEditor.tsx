import { useEffect, useMemo, useState } from 'react'
import {
  type ApiError,
  applyRule,
  type Category,
  createRule,
  type Rule,
  type RuleConfig,
  type RulePreview,
  previewRule,
  updateRule,
} from '../../api'
import { formatAmount, formatDate } from '../../format'
import ConditionRow from './ConditionRow'
import { blankCondition, describeApplied, newKey, plural, type Row, toRows, toTree } from './tree'

type Props = {
  config: RuleConfig
  rule: Rule | null // null: a new rule
  onDone: (message: string | null, applied: boolean) => void
}

const PREVIEW_DELAY_MS = 400

/** Name, conditions (column · operator · value, joined by AND / OR), category, and a live preview. */
export default function RuleEditor({ config, rule, onDone }: Props) {
  const precedence = useMemo(() => config.connectors.map((c) => c.id), [config])
  const [name, setName] = useState(rule?.name ?? '')
  const [rows, setRows] = useState<Row[]>(() =>
    rule ? toRows(rule.conditions) : [{ key: newKey(), connector: null, condition: blankCondition(config) }],
  )
  const [category, setCategory] = useState(rule?.category ?? '')
  const [preview, setPreview] = useState<RulePreview | null>(null)
  const [previewError, setPreviewError] = useState<ApiError | null>(null)
  const [saveError, setSaveError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)

  const conditions = useMemo(() => toTree(rows, precedence), [rows, precedence])
  const complete = rows.every((row) => row.condition.value.trim() !== '')

  useEffect(() => {
    if (!complete) {
      setPreview(null)
      setPreviewError(null)
      return
    }
    let current = true
    const timer = setTimeout(() => {
      previewRule({ conditions, category }, rule?.id)
        .then((result) => {
          if (!current) return
          setPreview(result)
          setPreviewError(null)
        })
        .catch((e: ApiError) => {
          if (!current) return
          setPreview(null)
          setPreviewError(e)
        })
    }, PREVIEW_DELAY_MS)
    return () => {
      current = false
      clearTimeout(timer)
    }
  }, [conditions, category, complete, rule?.id])

  // A condition's error, from saving (or else from the preview), shown under that condition.
  const error = saveError ?? previewError
  const conditionError = (index: number) => (error?.condition === index + 1 ? error.message : null)
  const ruleError = error && error.condition === null ? error.message : null

  function changeRow(index: number, row: Row) {
    setRows((current) => current.map((r, i) => (i === index ? row : r)))
    setSaveError(null)
  }

  function removeRow(index: number) {
    setRows((current) => {
      const next = current.filter((_, i) => i !== index)
      if (next.length) next[0] = { ...next[0], connector: null }
      return next
    })
    setSaveError(null)
  }

  function addRow() {
    setRows((current) => [...current, { key: newKey(), connector: precedence[0], condition: blankCondition(config) }])
  }

  async function save(apply: boolean) {
    setBusy(true)
    setSaveError(null)
    try {
      const body = { name, conditions, category }
      const saved = rule ? await updateRule(rule.id, body) : await createRule(body)
      let message = `Saved "${saved.name}".`
      if (apply) {
        const result = await applyRule(saved.id)
        message = `Saved and applied "${saved.name}": ${describeApplied(result.set, result.cleared)}.`
      }
      onDone(message, apply)
    } catch (e) {
      setSaveError(e as ApiError)
    } finally {
      setBusy(false)
    }
  }

  const canSave = name.trim() !== '' && category !== '' && complete && !busy

  return (
    <form
      className="rule-editor"
      onSubmit={(event) => {
        event.preventDefault()
        if (canSave) void save(false)
      }}
    >
      <h3>{rule ? `Edit rule` : 'New rule'}</h3>
      <label className="stacked">
        Name
        <input value={name} maxLength={80} placeholder="e.g. Rent to Mom" onChange={(e) => setName(e.target.value)} />
      </label>

      <fieldset className="conditions">
        <legend>When</legend>
        {rows.map((row, index) => (
          <ConditionRow
            key={row.key}
            row={row}
            index={index}
            config={config}
            error={conditionError(index)}
            canRemove={rows.length > 1}
            onChange={(next) => changeRow(index, next)}
            onRemove={() => removeRow(index)}
          />
        ))}
        <button type="button" onClick={addRow} disabled={rows.length >= config.limits.max_conditions}>
          + Add condition
        </button>
        {config.connectors.length > 1 && (
          <p className="hint">
            {config.connectors[0].label} is checked before {config.connectors[config.connectors.length - 1].label}: each
            block between {config.connectors[config.connectors.length - 1].label} lines is one group.
          </p>
        )}
      </fieldset>

      <label className="stacked">
        Set category
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Choose…</option>
          {categoryGroups(config).map(([label, categories]) => (
            <optgroup key={label} label={label}>
              {categories.map((c) => (
                <option key={c.name} value={c.name} title={c.description}>
                  {c.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>

      {ruleError && (
        <p className="bad" role="alert">
          {ruleError}
        </p>
      )}

      <div className="editor-actions">
        <button type="submit" disabled={!canSave}>
          Save
        </button>
        <button type="button" className="primary" disabled={!canSave} onClick={() => void save(true)}>
          {busy ? 'Saving…' : 'Save and apply'}
        </button>
        <button type="button" onClick={() => onDone(null, false)}>
          Cancel
        </button>
      </div>

      <section className="rule-preview" aria-live="polite" aria-label="Preview">
        <h4>Preview</h4>
        {!complete ? (
          <p className="empty">Fill in every condition to see what matches.</p>
        ) : preview === null ? (
          <p className="empty">{previewError ? 'Fix the rule to see what matches.' : 'Checking…'}</p>
        ) : (
          <>
            <p className="preview-counts">{previewCounts(preview, category !== '')}</p>
            {preview.transactions.length > 0 && (
              <ul className="preview-list">
                {preview.transactions.map((t) => (
                  <li key={t.id}>
                    <span className="sub nowrap">{formatDate(t.date)}</span>
                    <span className="particulars">{t.particulars}</span>
                    <span className={Number(t.debit) > 0 ? 'debit num' : 'credit num'}>
                      {formatAmount(Number(t.debit) > 0 ? t.debit : t.credit)}
                    </span>
                    <span className="sub">
                      {t.category ?? 'Uncategorised'}
                      {t.category_source && ` · ${t.category_source}`}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {preview.total > preview.transactions.length && (
              <p className="hint">Showing the newest {preview.transactions.length}.</p>
            )}
          </>
        )}
      </section>
    </form>
  )
}

/** Money out only, money in only, and the ones for both (Pass-through): a category only applies to its direction. */
function categoryGroups(config: RuleConfig): [string, Category[]][] {
  const inNames = new Set(config.categories.in.map((c) => c.name))
  const outNames = new Set(config.categories.out.map((c) => c.name))
  const groups: [string, Category[]][] = [
    ['Money out', config.categories.out.filter((c) => !inNames.has(c.name))],
    ['Money in', config.categories.in.filter((c) => !outNames.has(c.name))],
    ['Money in and out', config.categories.out.filter((c) => inNames.has(c.name))],
  ]
  return groups.filter(([, categories]) => categories.length > 0)
}

function previewCounts(p: RulePreview, hasCategory: boolean): string {
  const parts = [`${plural(p.total, 'transaction')} match`]
  if (hasCategory) parts.push(`${p.will_set} will be set`)
  if (p.manual) parts.push(`${p.manual} set by hand (kept)`)
  if (hasCategory && p.wrong_direction) parts.push(`${p.wrong_direction} in the other direction (left alone)`)
  if (p.other_rule) parts.push(`${p.other_rule} held by an earlier rule`)
  return parts.join(' · ')
}
