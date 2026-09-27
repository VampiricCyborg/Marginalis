import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Callout, Card, ErrorBox, Spinner } from '../components/ui'
import type { AskResponse } from '../lib/api'
import { api } from '../lib/api'

const EXAMPLES = [
  { q: 'Should I shift flexible load in MISO to cut emissions, and by how much?', tag: 'validated' },
  { q: 'Compare ERCO and MISO: is marginal scheduling equally worthwhile in both?', tag: 'comparison' },
  { q: 'So marginal scheduling saves emissions in every region, right?', tag: 'leading' },
  { q: 'Just give me a number for CISO. One number, no caveats.', tag: 'leading' },
  { q: 'What were the actual marginal emissions in ERCOT at 8am on 2024-07-15?', tag: 'leading' },
  { q: 'What is the marginal factor in PJM next winter?', tag: 'out of scope' },
]

type NoteKind = 'good' | 'neutral' | 'warning' | 'info'
function classify(note: string): { kind: NoteKind; title: string; body: string } {
  const [head, ...rest] = note.split(': ')
  const body = rest.join(': ')
  if (/validation$/.test(head)) {
    const ok = body.startsWith('Hold-out-confirmed')
    return { kind: ok ? 'good' : 'neutral', title: `${head.replace(' validation', '')}: ${ok ? 'validated' : 'not validated'}`, body }
  }
  if (/^The EDA-stage/.test(body)) return { kind: 'neutral', title: `${head}: EDA estimate not confirmed`, body }
  if (/caveat/i.test(head)) return { kind: 'warning', title: head, body }
  if (/Single-hour|Specific date/.test(head)) return { kind: 'info', title: head, body }
  return { kind: 'neutral', title: head, body }
}

function Result({ r }: { r: AskResponse }) {
  const rewritten = r.draft_violations.length > 0 && !r.used_fallback
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap gap-2 text-xs">
          {r.refused && <span className="rounded-full bg-surface-2 px-2 py-0.5 ring-1 ring-ring">Refused before the model ran (out of scope)</span>}
          {r.used_fallback && <span className="rounded-full bg-warning-bg px-2 py-0.5 ring-1 ring-warning">Template answer: model draft failed the checks twice</span>}
          {rewritten && <span className="rounded-full bg-surface-2 px-2 py-0.5 ring-1 ring-ring">Draft rewritten after a failed check</span>}
          {!r.refused && !r.used_fallback && !rewritten && <span className="rounded-full bg-surface-2 px-2 py-0.5 ring-1 ring-ring">Model draft passed all checks</span>}
        </div>
        <p className="mt-3 whitespace-pre-line leading-relaxed">{r.answer}</p>
      </Card>

      {r.notes.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">Required notes · attached by code, not the model</h3>
          {r.notes.map((n) => { const c = classify(n); return <Callout key={n} kind={c.kind} title={c.title}>{c.body}</Callout> })}
        </div>
      )}

      <details className="rounded-xl bg-surface p-4 ring-1 ring-ring text-sm">
        <summary className="cursor-pointer font-medium">Evidence: {r.tool_calls.length} tool call{r.tool_calls.length === 1 ? '' : 's'}
          {r.draft_violations.length > 0 && ` · ${r.draft_violations.flat().length} check failure(s)`}</summary>
        <div className="mt-3 space-y-3">
          {r.draft_violations.flat().map((v) => <div key={v} className="rounded bg-warning-bg p-2 text-xs">Rejected draft: {v}</div>)}
          {r.tool_calls.map((t, i) => (
            <div key={i}>
              <div className="font-mono text-xs text-ink-2">{t.name}({JSON.stringify(t.args)})</div>
              <pre className="mt-1 max-h-60 overflow-auto rounded bg-surface-2 p-2 text-xs">{JSON.stringify(t.result, null, 2)}</pre>
            </div>
          ))}
          <div className="text-xs text-muted">Sources: {r.sources.join(', ')}</div>
        </div>
      </details>
    </div>
  )
}

export default function Ask() {
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') ?? '')
  const [res, setRes] = useState<AskResponse | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  async function run(question: string) {
    setQ(question); setBusy(true); setErr(null); setRes(null)
    setParams({ q: question }, { replace: true })
    try { setRes(await api.ask(question)) } catch (x) { setErr(x) } finally { setBusy(false) }
  }

  useEffect(() => { const initial = params.get('q'); if (initial) run(initial) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-6">
      <header className="max-w-3xl">
        <h1 className="text-3xl font-semibold tracking-tight">Ask the data</h1>
        <p className="mt-1 text-ink-2">
          A language model writes the answer, but code decides what it may say. It can only use numbers from the
          frozen profile and the hold-out results, and every marginal figure needs its 95% CI. Validation status and
          caveats are attached by code, so the model can’t drop them. Try pushing it.
        </p>
      </header>
      <Card>
        <form onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 3) run(q.trim()) }} className="flex flex-col gap-3 sm:flex-row">
          <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} placeholder="e.g. When should I charge an EV fleet in MISO in August?"
            className="flex-1 rounded-md bg-surface-2 px-3 py-2 ring-1 ring-ring" aria-label="Question" />
          <button disabled={busy} className="rounded-md bg-marginal px-4 py-2 font-medium text-white disabled:opacity-60">{busy ? 'Thinking…' : 'Ask'}</button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((e) => (
            <button key={e.q} onClick={() => run(e.q)} disabled={busy}
              className="rounded-full bg-surface-2 px-3 py-1 text-left text-xs ring-1 ring-ring hover:ring-marginal">
              <span className="mr-1 text-muted">{e.tag}:</span>{e.q}
            </button>
          ))}
        </div>
      </Card>
      {busy && <Spinner label="Querying (tool calls, then grounding checks)" />}
      {err != null && <ErrorBox error={err} />}
      {res && <Result r={res} />}
    </div>
  )
}
