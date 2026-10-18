type Props = {
  value: string
  onChange: (value: string) => void
  serverHasKey: boolean | null
}

/** The user's own Jev (TypeSafe) key, sent with each upload. Kept only in this browser. */
export default function ApiKeyField({ value, onChange, serverHasKey }: Props) {
  return (
    <section className="card key-field">
      <label htmlFor="jev-key">Jev API key</label>
      <input
        id="jev-key"
        type="password"
        autoComplete="off"
        spellCheck={false}
        placeholder="ts-…"
        value={value}
        onChange={(event) => onChange(event.target.value.trim())}
      />
      <UploadMode hasKey={value !== ''} serverHasKey={serverHasKey} />
      <p className="hint">Saved in this browser only and sent with each upload; never stored on the server.</p>
    </section>
  )
}

/** Which way the next upload reads column names: the user's key, the server's key, or rules only. */
function UploadMode({ hasKey, serverHasKey }: { hasKey: boolean; serverHasKey: boolean | null }) {
  if (hasKey) return <p className="mode ok">Uploads use Jev with your key.</p>
  if (serverHasKey === null) return null
  if (serverHasKey) return <p className="mode ok">Uploads use Jev with the server's key.</p>
  return (
    <p className="mode warn">
      No key: uploads use keyword rules only. Statements whose column names are images (such as SBI) need a key.
    </p>
  )
}
