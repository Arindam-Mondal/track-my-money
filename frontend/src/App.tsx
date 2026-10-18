import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import {
  type Categories,
  categoriseStatement,
  deleteStatement,
  getCategories,
  getHealth,
  listStatements,
  listTransactions,
  type Statement,
  type Transaction,
} from './api'
import ApiKeyField from './components/ApiKeyField'
import StatementList from './components/StatementList'
import TransactionTable from './components/TransactionTable'
import UploadPanel from './components/UploadPanel'

// The charts library is large: load the Money flow tab only when it's opened.
const MoneyFlow = lazy(() => import('./components/MoneyFlow'))

const KEY_STORAGE = 'track-my-money.jev-key'
const POLL_MS = 2000 // while Laya categorises in the background

type Tab = 'statements' | 'flow'

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

export default function App() {
  const [tab, setTab] = useState<Tab>('statements')
  const [apiKey, setApiKey] = useState(loadKey)
  const [serverHasKey, setServerHasKey] = useState<boolean | null>(null)
  const [categories, setCategories] = useState<Categories | null>(null)
  const [statements, setStatements] = useState<Statement[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [transactions, setTransactions] = useState<Transaction[] | null>(null)
  const [transactionsVersion, setTransactionsVersion] = useState(0)
  const [error, setError] = useState<string | null>(null)

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
  }, [refresh])

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

  async function categorise(id: number) {
    try {
      await categoriseStatement(id)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function transactionChanged(updated: Transaction) {
    setTransactions((rows) => rows?.map((row) => (row.id === updated.id ? updated : row)) ?? rows)
    void refresh()
  }

  const selected = statements.find((s) => s.id === selectedId) ?? null

  return (
    <main>
      <header>
        <h1>Track My Money</h1>
        <p className="sub">Import bank statements and see every transaction in one place.</p>
        <nav className="tabs" aria-label="Views">
          <button type="button" aria-current={tab === 'statements'} onClick={() => setTab('statements')}>
            Statements
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

      {tab === 'flow' ? (
        <Suspense fallback={<p className="empty">Loading charts…</p>}>
          <MoneyFlow categories={categories} />
        </Suspense>
      ) : (
        <>
          <div className="top">
            <UploadPanel apiKey={apiKey} onImported={refresh} />
            <ApiKeyField
              value={apiKey}
              serverHasKey={serverHasKey}
              onChange={(key) => {
                setApiKey(key)
                saveKey(key)
              }}
            />
          </div>

          <StatementList
            statements={statements}
            selectedId={selectedId}
            onSelect={select}
            onDelete={remove}
            onCategorise={categorise}
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
  )
}
