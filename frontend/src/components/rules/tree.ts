import type { Condition, ConditionGroup, RuleConfig } from '../../api'

/** One line of the builder: a condition, joined to the line above by a connector (none on the first). */
export type Row = { key: number; connector: string | null; condition: Condition }

let nextKey = 0
export function newKey(): number {
  nextKey += 1
  return nextKey
}

function isGroup(item: Condition | ConditionGroup): item is ConditionGroup {
  return 'items' in item
}

/**
 * Builder lines -> the stored tree. `precedence` lists connector ids tightest-binding first, as the
 * config sends them, so with [and, or] the lines A and B or C become or(and(A, B), and(C)).
 */
export function toTree(rows: Row[], precedence: string[]): ConditionGroup {
  if (precedence.length === 1) return { match: precedence[0], items: rows.map((row) => row.condition) }
  const loosest = precedence[precedence.length - 1]
  const segments: Row[][] = []
  rows.forEach((row, i) => {
    if (i === 0 || row.connector === loosest) segments.push([])
    segments[segments.length - 1].push(row)
  })
  return { match: loosest, items: segments.map((segment) => toTree(segment, precedence.slice(0, -1))) }
}

/** The stored tree -> builder lines, joining each group's items with its connector. */
export function toRows(group: ConditionGroup): Row[] {
  return group.items.flatMap((item, i) => {
    const rows = isGroup(item) ? toRows(item) : [{ key: newKey(), connector: null, condition: item }]
    if (i > 0 && rows.length) rows[0] = { ...rows[0], connector: group.match }
    return rows
  })
}

/** A blank condition: the first column, its type's first operator. */
export function blankCondition(config: RuleConfig): Condition {
  const field = config.fields[0]
  return { field: field.id, operator: config.types[field.type].operators[0].id, value: '' }
}

/** "Particulars matches regex "UPI/…" AND Debit = 26000", with the config's labels. */
export function summarise(group: ConditionGroup, config: RuleConfig): string {
  const connectorLabel = new Map(config.connectors.map((c) => [c.id, c.label]))
  return toRows(group)
    .map(({ connector, condition }) => {
      const field = config.fields.find((f) => f.id === condition.field)
      const operator = field && config.types[field.type]?.operators.find((o) => o.id === condition.operator)
      const value = field && config.types[field.type]?.input === 'number' ? condition.value : `"${condition.value}"`
      const text = `${field?.label ?? condition.field} ${operator?.label ?? condition.operator} ${value}`
      return connector ? `${connectorLabel.get(connector) ?? connector} ${text}` : text
    })
    .join(' ')
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

/** "14 transactions categorised, 2 back to uncategorised" */
export function describeApplied(set: number, cleared: number): string {
  return `${plural(set, 'transaction')} categorised${cleared ? `, ${cleared} back to uncategorised` : ''}`
}
