import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Callout, ErrorBox } from '../components/ui'
import { EASE, Magnetic, Reveal, SplitLines, useLenis } from '../lib/motion'
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
      <div className="rounded-3xl bg-surface p-6 ring-1 ring-ring sm:p-10">
        <div className="flex flex-wrap gap-2 text-xs">
          {r.refused && <span className="rounded-full bg-surface-2 px-2 py-0.5 ring-1 ring-ring">Refused before the model ran (out of scope)</span>}
          {r.used_fallback && <span className="rounded-full bg-warning-bg px-2 py-0.5 ring-1 ring-warning">Template answer: model draft failed the checks twice</span>}
          {rewritten && <span className="rounded-full bg-surface-2 px-2 py-0.5 ring-1 ring-ring">Draft rewritten after a failed check</span>}
          {!r.refused && !r.used_fallback && !rewritten && <span className="rounded-full bg-surface-2 px-2 py-0.5 ring-1 ring-ring">Model draft passed all checks</span>}
        </div>
        <TypeOut text={r.answer} />
      </div>

      {r.notes.length > 0 && (
        <div className="space-y-2">
          <h3 className="eyebrow pt-2">Required notes · attached by code, not the model</h3>
          {r.notes.map((n) => { const c = classify(n); return <Callout key={n} kind={c.kind} title={c.title}>{c.body}</Callout> })}
        </div>
      )}

      <details className="rounded-3xl bg-surface p-5 ring-1 ring-ring text-sm sm:p-6" data-lenis-prevent>
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

function TypeOut({ text }: { text: string }) {
  const reduce = useReducedMotion()
  const words = text.split(/(\s+)/)
  return (
    <p className="mt-5 whitespace-pre-line text-xl leading-relaxed tracking-tight sm:text-2xl">
      {reduce ? text : words.map((w, i) => (
        <motion.span key={i} initial={{ opacity: 0, filter: 'blur(6px)' }} animate={{ opacity: 1, filter: 'blur(0px)' }}
          transition={{ duration: 0.4, delay: Math.min(i * 0.018, 2.5) }}>{w}</motion.span>
      ))}
    </p>
  )
}

const STAGES = ['Scope check', 'Tool calls on frozen results', 'Model draft', 'Grounding checks', 'Caveats attached by code']
function Working() {
  const [k, setK] = useState(0)
  useEffect(() => { const id = setInterval(() => setK((x) => (x + 1) % STAGES.length), 900); return () => clearInterval(id) }, [])
  return (
    <div className="rounded-3xl bg-ink p-6 text-page sm:p-8" role="status" aria-live="polite">
      <p className="font-mono text-[11px] uppercase tracking-wider opacity-60">Working · what every answer goes through</p>
      <ol className="mt-5 grid gap-3 sm:grid-cols-5">
        {STAGES.map((st, i) => (
          <li key={st} className="relative overflow-hidden rounded-2xl p-4 ring-1 ring-white/15">
            {k === i && <motion.span layoutId="stage" className="absolute inset-0 bg-[#4a90e8]" transition={{ type: 'spring', stiffness: 300, damping: 30 }} />}
            <span className="relative block font-mono text-xs opacity-70">0{i + 1}</span>
            <span className="relative mt-3 block text-sm font-medium">{st}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

const TAG_STYLE: Record<string, string> = {
  validated: 'bg-good-bg text-good-text', comparison: 'bg-surface-2 text-ink-2',
  leading: 'bg-warning-bg text-warning-text', 'out of scope': 'bg-neutral-bg text-ink-2',
}

export default function Ask() {
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') ?? '')
  const [res, setRes] = useState<AskResponse | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const lenis = useLenis()
  async function run(question: string) {
    setQ(question); setBusy(true); setErr(null); setRes(null)
    requestAnimationFrame(() => {
      const el = document.getElementById('ask-out')
      if (el && el.getBoundingClientRect().top > window.innerHeight * 0.7) {
        if (lenis) lenis.scrollTo(el, { offset: -160, duration: 1.4 }); else el.scrollIntoView({ behavior: 'smooth' })
      }
    })
    setParams({ q: question }, { replace: true })
    try { setRes(await api.ask(question)) } catch (x) { setErr(x) } finally { setBusy(false) }
  }

  useEffect(() => { const initial = params.get('q'); if (initial) run(initial) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="px-4 pb-24 pt-28 sm:px-8">
      <header className="grid gap-8 md:grid-cols-[1.5fr_1fr] md:items-end">
        <div>
          <p className="eyebrow mb-6">Interface · grounded Q&amp;A</p>
          <h1 className="display text-[17vw] sm:text-[11vw] lg:text-[9vw]"><SplitLines immediate delay={0.3} lines={['Ask the', <span className="text-marginal">data.</span>]} /></h1>
        </div>
        <Reveal className="text-lg leading-relaxed text-ink-2">
          A language model writes the answer, but code decides what it may say. It can only use numbers from the frozen profile and the hold-out
          results, and every marginal figure needs its 95% CI. Validation status and caveats are attached by code, so the model can’t drop them.
          <b className="text-ink"> Try pushing it.</b>
        </Reveal>
      </header>

      <Reveal className="mt-12">
        <form onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 3) run(q.trim()) }}
          className="flex items-end gap-4 border-b-2 border-ink pb-3 focus-within:border-marginal">
          <label className="sr-only" htmlFor="q">Question</label>
          <input id="q" value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} placeholder="When should I charge an EV fleet in MISO in August?"
            className="min-w-0 flex-1 bg-transparent text-2xl tracking-tight outline-none placeholder:text-muted/70 sm:text-4xl" />
          <Magnetic>
            <button disabled={busy} aria-label="Ask"
              className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-ink text-2xl text-page transition-all duration-500 hover:scale-110 hover:bg-marginal disabled:opacity-50 sm:h-20 sm:w-20">
              {busy ? <span className="h-5 w-5 animate-spin rounded-full border-2 border-page border-t-transparent" /> : '→'}
            </button>
          </Magnetic>
        </form>
      </Reveal>

      <Reveal className="mt-10">
        <p className="eyebrow mb-3">Or try to break it</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {EXAMPLES.map((e, i) => (
            <motion.button key={e.q} onClick={() => run(e.q)} disabled={busy}
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 + i * 0.06, duration: 0.8, ease: EASE }}
              whileHover={{ y: -4 }} whileTap={{ scale: 0.98 }}
              className="flex flex-col justify-between gap-6 rounded-2xl bg-surface p-5 text-left ring-1 ring-ring transition-shadow hover:shadow-xl disabled:opacity-60">
              <span className={`self-start rounded-full px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${TAG_STYLE[e.tag]}`}>{e.tag}</span>
              <span className="text-lg leading-snug">{e.q}</span>
            </motion.button>
          ))}
        </div>
      </Reveal>

      <div id="ask-out" className="mt-10 space-y-4">
        <AnimatePresence mode="wait">
          {busy && <motion.div key="busy" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}><Working /></motion.div>}
          {res && !busy && <motion.div key="res" initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease: EASE }}><Result r={res} /></motion.div>}
        </AnimatePresence>
        {err != null && <ErrorBox error={err} />}
      </div>
    </div>
  )
}
