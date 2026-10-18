import type { Categoriser } from '../api'

type Props = {
  value: Categoriser
  onChange: (value: Categoriser) => void
  jevAvailable: boolean // a key in the field or on the server
}

/** Which model the Categorise buttons use. Nothing is categorised until a button is clicked. */
export default function CategoriserSwitch({ value, onChange, jevAvailable }: Props) {
  return (
    <section className="card categoriser" aria-label="Categorise with">
      <span className="label">Categorise with</span>
      <div className="segmented" role="radiogroup">
        <label className={value === 'laya' ? 'on' : undefined}>
          <input type="radio" name="categoriser" checked={value === 'laya'} onChange={() => onChange('laya')} />
          Laya <span className="sub">local</span>
        </label>
        <label className={value === 'jev' ? 'on' : undefined}>
          <input type="radio" name="categoriser" checked={value === 'jev'} onChange={() => onChange('jev')} />
          Jev <span className="sub">cloud, masked</span>
        </label>
      </div>
      <p className="hint">
        {value === 'laya'
          ? 'Runs on this computer. Narrations never leave it.'
          : 'Sends only the masked narration, direction and an amount range. Check "Show what Jev sees" first.'}
        {value === 'jev' && !jevAvailable && <strong className="warn-text"> Needs a Jev API key.</strong>}
      </p>
    </section>
  )
}
