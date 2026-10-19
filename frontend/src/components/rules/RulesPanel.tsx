import { useEffect, useState } from 'react'
import { applyAllRules, applyRule, deleteRule, getRuleConfig, type Rule, type RuleConfig } from '../../api'
import RuleEditor from './RuleEditor'
import { describeApplied, plural, summarise } from './tree'

type Props = {
  rules: Rule[]
  onClose: () => void
  onRulesChanged: () => void // a rule was saved or deleted: reload the list
  onTransactionsChanged: () => void // categories changed: reload what's on screen
}

type View = { kind: 'list' } | { kind: 'edit'; rule: Rule | null }

/**
 * The rules side panel: the list (checked top to bottom, first match wins), and the editor.
 * Rules run on upload and before Laya or Jev; Apply runs them on the transactions already stored.
 */
export default function RulesPanel({ rules, onClose, onRulesChanged, onTransactionsChanged }: Props) {
  const [config, setConfig] = useState<RuleConfig | null>(null)
  const [view, setView] = useState<View>({ kind: 'list' })
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: 'ok' | 'bad'; text: string } | null>(null)

  useEffect(() => {
    getRuleConfig()
      .then(setConfig)
      .catch((e: Error) => setMessage({ kind: 'bad', text: e.message }))
  }, [])

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape' && view.kind === 'list') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, view.kind])

  async function run(action: () => Promise<string>) {
    setBusy(true)
    setMessage(null)
    try {
      setMessage({ kind: 'ok', text: await action() })
    } catch (e) {
      setMessage({ kind: 'bad', text: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  function applyAll() {
    void run(async () => {
      const result = await applyAllRules()
      onRulesChanged()
      onTransactionsChanged()
      return `Applied all rules: ${describeApplied(result.set, result.cleared)}.`
    })
  }

  function applyOne(rule: Rule) {
    void run(async () => {
      const result = await applyRule(rule.id)
      onRulesChanged()
      onTransactionsChanged()
      return `Applied "${rule.name}": ${describeApplied(result.set, result.cleared)}.`
    })
  }

  function remove(rule: Rule) {
    const effect = rule.applied_count ? ` ${plural(rule.applied_count, 'transaction')} it categorised go back to uncategorised.` : ''
    if (!window.confirm(`Delete the rule "${rule.name}"?${effect}`)) return
    void run(async () => {
      await deleteRule(rule.id)
      onRulesChanged()
      if (rule.applied_count) onTransactionsChanged()
      return `Deleted "${rule.name}".`
    })
  }

  return (
    <aside className="drawer" aria-label="Rules">
      <div className="drawer-head">
        <h2>Rules</h2>
        <button type="button" className="icon" aria-label="Close rules" onClick={onClose}>
          ×
        </button>
      </div>

      {config === null ? (
        message ? (
          <p className="bad">{message.text}</p>
        ) : (
          <p className="empty">Loading…</p>
        )
      ) : view.kind === 'edit' ? (
        <RuleEditor
          key={view.rule?.id ?? 'new'}
          config={config}
          rule={view.rule}
          onDone={(text, applied) => {
            setView({ kind: 'list' })
            if (text) {
              setMessage({ kind: 'ok', text })
              onRulesChanged()
              if (applied) onTransactionsChanged()
            }
          }}
        />
      ) : (
        <>
          <p className="hint">
            Rules run on upload and before Laya or Jev, top to bottom: the first match wins. Categories you set by hand are
            never changed.
          </p>
          <div className="drawer-actions">
            <button type="button" className="primary" onClick={() => setView({ kind: 'edit', rule: null })}>
              New rule
            </button>
            <button type="button" disabled={busy || rules.length === 0} onClick={applyAll}>
              Apply all rules
            </button>
          </div>
          {message && (
            <p className={message.kind} role={message.kind === 'bad' ? 'alert' : 'status'}>
              {message.text}
            </p>
          )}
          {rules.length === 0 ? (
            <p className="empty">No rules yet.</p>
          ) : (
            <ol className="rule-list">
              {rules.map((rule) => (
                <li key={rule.id}>
                  <div className="rule-name">{rule.name}</div>
                  <div className="rule-summary">{summarise(rule.conditions, config)}</div>
                  <div className="rule-meta">
                    → <strong>{rule.category}</strong>
                    <span className="sub"> · used on {plural(rule.applied_count, 'transaction')}</span>
                  </div>
                  <div className="rule-actions">
                    <button type="button" disabled={busy} onClick={() => applyOne(rule)}>
                      Apply
                    </button>
                    <button type="button" disabled={busy} onClick={() => setView({ kind: 'edit', rule })}>
                      Edit
                    </button>
                    <button type="button" className="danger" disabled={busy} onClick={() => remove(rule)}>
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </aside>
  )
}
