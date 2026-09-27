import type { ReactNode } from 'react'
import type { Estimate } from '../lib/api'
import { fmt } from '../lib/api'

export function StatusBadge({ validated, size = 'md' }: { validated: boolean; size?: 'sm' | 'md' }) {
  const pad = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'
  return validated ? (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-medium bg-good-bg text-good-text ring-1 ring-good/40 ${pad}`}>
      <svg aria-hidden width="14" height="14" viewBox="0 0 16 16"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
      Validated in hold-out
    </span>
  ) : (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-medium bg-neutral-bg text-ink-2 ring-1 ring-dashed ring-neutral/60 border border-dashed border-neutral/60 ${pad}`}>
      <svg aria-hidden width="14" height="14" viewBox="0 0 16 16"><circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeDasharray="2.5 2" /></svg>
      Not validated
    </span>
  )
}

type Kind = 'warning' | 'info' | 'good' | 'neutral'
const KIND: Record<Kind, { box: string; icon: ReactNode; label: string }> = {
  warning: { box: 'bg-warning-bg border-warning text-ink', label: 'Caveat',
    icon: <path d="M8 2l6.5 11.5h-13L8 2zm0 4v3.5m0 2v.5" fill="none" stroke="var(--warning-text)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /> },
  info: { box: 'bg-surface-2 border-marginal/60 text-ink', label: 'Note',
    icon: <path d="M8 1.8a6.2 6.2 0 110 12.4A6.2 6.2 0 018 1.8zM8 7v4.2M8 4.8v.4" fill="none" stroke="var(--marginal)" strokeWidth="1.6" strokeLinecap="round" /> },
  good: { box: 'bg-good-bg border-good text-ink', label: 'Validated',
    icon: <path d="M3 8.5l3 3 7-7" fill="none" stroke="var(--good-text)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /> },
  neutral: { box: 'bg-neutral-bg border-neutral border-dashed text-ink', label: 'Not validated',
    icon: <circle cx="8" cy="8" r="5.5" fill="none" stroke="var(--muted)" strokeWidth="1.6" strokeDasharray="2.5 2" /> },
}

export function Callout({ kind, title, children }: { kind: Kind; title?: string; children: ReactNode }) {
  const k = KIND[kind]
  return (
    <div className={`flex gap-3 rounded-2xl border-l-4 border p-4 text-sm leading-relaxed ${k.box}`} role={kind === 'warning' ? 'note' : undefined}>
      <svg aria-hidden width="18" height="18" viewBox="0 0 16 16" className="mt-0.5 shrink-0">{k.icon}</svg>
      <div>
        <div className="font-semibold">{title ?? k.label}</div>
        <div className="text-ink-2">{children}</div>
      </div>
    </div>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-3xl bg-surface ring-1 ring-ring p-5 sm:p-8 ${className}`}>{children}</section>
}

export function EstimateLine({ e, unit = 'kg CO₂/MWh shifted' }: { e: Estimate; unit?: string }) {
  return (
    <span className="tabular">
      <span className="text-2xl font-semibold">{fmt(e.value)}</span>{' '}
      <span className="text-ink-2">{unit}</span>
      <span className="block text-sm text-ink-2">95% CI {fmt(e.ci_low_95)} to {fmt(e.ci_high_95)}</span>
    </span>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-sm text-muted" role="status">
      <span className="flex gap-1">{[0, 1, 2].map((i) => <span key={i} className="h-2 w-2 animate-bounce rounded-full bg-marginal" style={{ animationDelay: `${i * 0.12}s` }} />)}</span>
      {label}…
    </div>
  )
}

export function ErrorBox({ error }: { error: unknown }) {
  return <Callout kind="warning" title="Could not load">{String((error as Error)?.message ?? error)}</Callout>
}
