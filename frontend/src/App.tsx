import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import {
  type Categories,
  type Categoriser,
  categoriseStatement,
  deleteStatement,
  getCategories,
  getHealth,
  listStatements,
  listRules,
  listTransactions,
  type Rule,
  type Statement,
  type Transaction,
} from './api'
import ApiKeyField from './components/ApiKeyField'
import CategoriserSwitch from './components/CategoriserSwitch'
import StatementList from './components/StatementList'
import TransactionSearch from './components/TransactionSearch'
import RulesPanel from './components/rules/RulesPanel'
import TransactionTable from './components/TransactionTable'
import UploadPanel from './components/UploadPanel'
import { RuleNames } from './ruleNames'

// The charts library is large: load the Money flow tab only when it's opened.
const MoneyFlow = lazy(() => import('./components/MoneyFlow'))

const KEY_STORAGE = 'track-my-money.jev-key'
const CATEGORISER_STORAGE = 'track-my-money.categoriser'
const POLL_MS = 2000 // while a statement is being categorised in the background

type Tab = 'statements' | 'transactions' | 'flow'

// localStorage can be unavailable (private windows, blocked site data); the key then lasts this visit only.
function loadKey(): string {
  try {
    return localStorage.getItem(KEY_STORAGE) ?? ''
  } catch {
    return ''
  }
}

function saveKey(key: string) {
  try {
    if (key) localStorage.setItem(KEY_STORAGE, key)
    else localStorage.removeItem(KEY_STORAGE)
  } catch {
    // not persisted; still used for this visit
  }
}

function loadCategoriser(): Categoriser {
  try {
    return localStorage.getItem(CATEGORISER_STORAGE) === 'jev' ? 'jev' : 'laya'
  } catch {
    return 'laya'
  }
}

function saveCategoriser(value: Categoriser) {
  try {
    localStorage.setItem(CATEGORISER_STORAGE, value)
  } catch {
    // not persisted; still used for this visit
  }
}

export default function App() {
  const [tab, setTab] = useState<Tab>('statements')
  const [apiKey, setApiKey] = useState(loadKey)
  const [categoriser, setCategoriser] = useState<Categoriser>(loadCategoriser)
  const [serverHasKey, setServerHasKey] = useState<boolean | null>(null)
  const [categories, setCategories] = useState<Categories | null>(null)
  const [statements, setStatements] = useState<Statement[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [transactions, setTransactions] = useState<Transaction[] | null>(null)
  const [transactionsVersion, setTransactionsVersion] = useState(0)
  const [rules, setRules] = useState<Rule[]>([])
  const [rulesOpen, setRulesOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshRules = useCallback(() => {
    listRules()
      .then(setRules)
      .catch((e: Error) => setError(e.message))
  }, [])
  const ruleNames = useMemo(() => new Map(rules.map((r) => [r.id, r.name])), [rules])
  const closeRules = useCallback(() => setRulesOpen(false), [])

  const refresh = useCallback(async () => {
    try {
      setStatements(await listStatements())
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    getHealth()
      .then((health) => setServerHasKey(health.server_jev_key))
      .catch((e: Error) => setError(e.message))
    getCategories()
      .then(setCategories)
      .catch((e: Error) => setError(e.message))
    void refresh()
    refreshRules()
  }, [refresh, refreshRules])

  // While any statement is being categorised, refresh its progress (and the open transactions).
  const categorising = statements.some((s) => s.categorising)
  useEffect(() => {
    if (!categorising) return
    const timer = setInterval(() => {
      void refresh()
      setTransactionsVersion((v) => v + 1)
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [categorising, refresh])

  useEffect(() => {
    if (selectedId === null) return
    let current = true
    listTransactions(selectedId)
      .then((rows) => current && setTransactions(rows))
      .catch((e: Error) => current && setError(e.message))
    return () => {
      current = false
    }
  }, [selectedId, transactionsVersion])

  function select(id: number) {
    setTransactions(null)
    setSelectedId(id)
  }

  async function remove(id: number) {
    try {
      await deleteStatement(id)
      if (id === selectedId) setSelectedId(null)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function categorise(id: number, redo: boolean) {
    try {
      await categoriseStatement(id, { categoriser, redo, apiKey })
      await refresh()
      refreshRules() // categorising runs the rules first
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function transactionChanged(updated: Transaction) {
    setTransactions((rows) => rows?.map((row) => (row.id === updated.id ? updated : row)) ?? rows)
    void refresh()
  }

  // Rules were applied or deleted: reload what's on screen in every tab.
  const transactionsChanged = useCallback(() => {
    void refresh()
    setTransactionsVersion((v) => v + 1)
  }, [refresh])

  const selected = statements.find((s) => s.id === selectedId) ?? null

  return (
    <RuleNames.Provider value={ruleNames}>
      <main className={rulesOpen ? 'with-drawer' : undefined}>
        <header>
          <div className="title-row">
            <h1>Track My Money</h1>
            <button type="button" aria-expanded={rulesOpen} onClick={() => setRulesOpen((open) => !open)}>
              Rules{rules.length ? ` (${rules.length})` : ''}
            </button>
          </div>
          <p className="sub">Import bank statements and see every transaction in one place.</p>
          <nav className="tabs" aria-label="Views">
            <button type="button" aria-current={tab === 'statements'} onClick={() => setTab('statements')}>
              Statements
            </button>
            <button type="button" aria-current={tab === 'transactions'} onClick={() => setTab('transactions')}>
              Transactions
            </button>
            <button type="button" aria-current={tab === 'flow'} onClick={() => setTab('flow')}>
              Money flow
            </button>
          </nav>
        </header>

        {error && (
          <p className="banner" role="alert">
            {error}
          </p>
        )}

        {tab === 'transactions' ? (
          <TransactionSearch
            categories={categories}
            statements={statements}
            version={transactionsVersion}
            onChanged={transactionsChanged}
          />
        ) : tab === 'flow' ? (
          <Suspense fallback={<p className="empty">Loading charts…</p>}>
            <MoneyFlow categories={categories} version={transactionsVersion} />
          </Suspense>
        ) : (
          <>
            <div className="top">
              <UploadPanel
                apiKey={apiKey}
                onImported={() => {
                  void refresh()
                  refreshRules() // uploads apply the rules
                }}
              />
              <div className="side">
                <ApiKeyField
                  value={apiKey}
                  serverHasKey={serverHasKey}
                  onChange={(key) => {
                    setApiKey(key)
                    saveKey(key)
                  }}
                />
                <CategoriserSwitch
                  value={categoriser}
                  jevAvailable={apiKey !== '' || serverHasKey === true}
                  onChange={(value) => {
                    setCategoriser(value)
                    saveCategoriser(value)
                  }}
                />
              </div>
            </div>

            <StatementList
              statements={statements}
              selectedId={selectedId}
              onSelect={select}
              onDelete={remove}
              onCategorise={categorise}
              categoriser={categoriser}
            />
            {selected && (
              <TransactionTable
                statement={selected}
                transactions={transactions}
                categories={categories}
                onTransactionChanged={transactionChanged}
              />
            )}
          </>
        )}
      </main>
      {rulesOpen && (
        <RulesPanel
          rules={rules}
          onClose={closeRules}
          onRulesChanged={refreshRules}
          onTransactionsChanged={transactionsChanged}
        />
      )}
    </RuleNames.Provider>
  )
}
