import type { Condition, RuleConfig } from '../../api'
import type { Row } from './tree'

type Props = {
  row: Row
  index: number
  config: RuleConfig
  error: string | null
  canRemove: boolean
  onChange: (row: Row) => void
  onRemove: () => void
}

/** connector · column · operator · value — every option comes from the rule config. */
export default function ConditionRow({ row, index, config, error, canRemove, onChange, onRemove }: Props) {
  const { condition } = row
  const field = config.fields.find((f) => f.id === condition.field) ?? config.fields[0]
  const type = config.types[field.type]
  const operator = type.operators.find((o) => o.id === condition.operator)
  const loosest = config.connectors[config.connectors.length - 1]?.id
  const number = index + 1

  function setCondition(change: Partial<Condition>) {
    onChange({ ...row, condition: { ...condition, ...change } })
  }

  function setField(id: string) {
    const next = config.fields.find((f) => f.id === id)
    if (!next) return
    const operators = config.types[next.type].operators
    const keep = operators.some((o) => o.id === condition.operator)
    const sameKind = config.types[next.type].input === type.input
    setCondition({ field: id, operator: keep ? condition.operator : operators[0].id, value: sameKind ? condition.value : '' })
  }

  return (
    <div className={`condition${row.connector === loosest ? ' starts-block' : ''}${error ? ' has-error' : ''}`}>
      {row.connector === null ? (
        <span className="connector-first">Where</span>
      ) : (
        <select
          className="connector"
          aria-label={`How condition ${number} joins the one above`}
          value={row.connector}
          onChange={(e) => onChange({ ...row, connector: e.target.value })}
        >
          {config.connectors.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      )}
      <select aria-label={`Column for condition ${number}`} value={field.id} onChange={(e) => setField(e.target.value)}>
        {config.fields.map((f) => (
          <option key={f.id} value={f.id}>
            {f.label}
          </option>
        ))}
      </select>
      <select
        aria-label={`Operator for condition ${number}`}
        value={condition.operator}
        onChange={(e) => setCondition({ operator: e.target.value })}
      >
        {type.operators.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>
      <input
        className="value"
        type={type.input === 'number' ? 'number' : 'text'}
        step={type.input === 'number' ? 'any' : undefined}
        aria-label={`Value for condition ${number}`}
        aria-invalid={error ? true : undefined}
        maxLength={config.limits.max_value_length}
        value={condition.value}
        onChange={(e) => setCondition({ value: e.target.value })}
      />
      <button type="button" className="icon" aria-label={`Remove condition ${number}`} disabled={!canRemove} onClick={onRemove}>
        ×
      </button>
      {operator?.hint && <p className="hint condition-note">{operator.hint}</p>}
      {error && (
        <p className="bad condition-note" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
