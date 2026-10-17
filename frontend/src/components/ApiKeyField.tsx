type Props = {
  value: string
  onChange: (value: string) => void
  serverHasKey: boolean | null
}

/** The user's own Jev (TypeSafe) key, sent with each upload. Kept only in this browser. */
export default function ApiKeyField({ value, onChange, serverHasKey }: Props) {
  const fallback =
    serverHasKey === null ? '' : serverHasKey ? "the server's key is used" : 'keyword rules are used instead of Jev'
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
      <p className="hint">
        Saved in this browser only and sent with each upload; never stored on the server.
        {fallback && <> Leave empty and {fallback}.</>}
      </p>
    </section>
  )
}
