import { useRef, useState } from 'react'
import { ApiError, type Statement, uploadStatement } from '../api'

type Status = 'uploading' | 'needs_password' | 'wrong_password' | 'imported' | 'duplicate' | 'error'

type Item = {
  id: number
  file: File
  status: Status
  message?: string
  statement?: Statement
  password: string
}

type Props = {
  apiKey: string
  onImported: () => void
}

let nextId = 1

/** Pick or drop several PDFs; each uploads on its own, and locked ones ask for their password. */
export default function UploadPanel({ apiKey, onImported }: Props) {
  const [items, setItems] = useState<Item[]>([])
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const update = (id: number, changes: Partial<Item>) =>
    setItems((current) => current.map((item) => (item.id === id ? { ...item, ...changes } : item)))

  async function send(id: number, file: File, password?: string) {
    update(id, { status: 'uploading', message: undefined })
    try {
      const statement = await uploadStatement(file, { password, apiKey })
      update(id, { status: 'imported', statement, password: '' })
      onImported()
    } catch (error) {
      if (!(error instanceof ApiError)) throw error
      if (error.code === 'password_required') update(id, { status: 'needs_password' })
      else if (error.code === 'wrong_password') update(id, { status: 'wrong_password', password: '' })
      else if (error.code === 'duplicate') update(id, { status: 'duplicate', message: error.message })
      else update(id, { status: 'error', message: error.message })
    }
  }

  function addFiles(files: FileList | null) {
    if (!files?.length) return
    const added = Array.from(files).map((file) => ({ id: nextId++, file, status: 'uploading' as const, password: '' }))
    setItems((current) => [...added, ...current])
    for (const item of added) void send(item.id, item.file)
  }

  return (
    <section className="card">
      <h2>Upload statements</h2>
      <div
        className={`dropzone${dragging ? ' dragging' : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          addFiles(event.dataTransfer.files)
        }}
      >
        <p>Drop bank statement PDFs here</p>
        <button type="button" className="primary" onClick={() => input.current?.click()}>
          Choose files
        </button>
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(event) => {
            addFiles(event.target.files)
            event.target.value = '' // allow picking the same file again
          }}
        />
      </div>

      {items.length > 0 && (
        <ul className="uploads">
          {items.map((item) => (
            <li key={item.id} className={`upload ${item.status}`}>
              <span className="filename" title={item.file.name}>
                {item.file.name}
              </span>
              <UploadStatus item={item} />
              {(item.status === 'needs_password' || item.status === 'wrong_password') && (
                <form
                  className="password"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void send(item.id, item.file, item.password)
                  }}
                >
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder="PDF password"
                    aria-label={`Password for ${item.file.name}`}
                    value={item.password}
                    onChange={(event) => update(item.id, { password: event.target.value })}
                    autoFocus
                  />
                  <button type="submit" disabled={!item.password}>
                    Unlock
                  </button>
                </form>
              )}
              {item.status !== 'uploading' && (
                <button
                  type="button"
                  className="icon"
                  aria-label={`Dismiss ${item.file.name}`}
                  onClick={() => setItems((current) => current.filter((other) => other.id !== item.id))}
                >
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function UploadStatus({ item }: { item: Item }) {
  switch (item.status) {
    case 'uploading':
      return <span className="status">Reading…</span>
    case 'needs_password':
      return <span className="status warn">Locked: enter its password</span>
    case 'wrong_password':
      return <span className="status warn">Wrong password, try again</span>
    case 'imported':
      return (
        <span className="status ok">
          Imported {item.statement?.transaction_count} transactions
          {item.statement?.header_mapping && <> · columns by {item.statement.header_mapping}</>} · not categorised yet:
          check the masked text, then use Categorise in the list
        </span>
      )
    case 'duplicate':
      return <span className="status muted">Already imported</span>
    case 'error':
      return <span className="status bad">{item.message}</span>
  }
}
