import { useCallback, useEffect, useState } from 'react'
import {
  deleteStatement,
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

const KEY_STORAGE = 'track-my-money.jev-key'

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
  const [apiKey, setApiKey] = useState(loadKey)
  const [serverHasKey, setServerHasKey] = useState<boolean | null>(null)
  const [statements, setStatements] = useState<Statement[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [transactions, setTransactions] = useState<Transaction[] | null>(null)
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
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (selectedId === null) return
    let current = true
    setTransactions(null)
    listTransactions(selectedId)
      .then((rows) => current && setTransactions(rows))
      .catch((e: Error) => current && setError(e.message))
    return () => {
      current = false
    }
  }, [selectedId])

  async function remove(id: number) {
    try {
      await deleteStatement(id)
      if (id === selectedId) setSelectedId(null)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const selected = statements.find((s) => s.id === selectedId) ?? null

  return (
    <main>
      <header>
        <h1>Track My Money</h1>
        <p className="sub">Import bank statements and see every transaction in one place.</p>
      </header>

      {error && (
        <p className="banner" role="alert">
          {error}
        </p>
      )}

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

      <StatementList statements={statements} selectedId={selectedId} onSelect={setSelectedId} onDelete={remove} />
      {selected && <TransactionTable statement={selected} transactions={transactions} />}
    </main>
  )
}
