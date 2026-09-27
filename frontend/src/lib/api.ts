// Typed client for the Marginalis API. The frontend only displays these values.
export type Estimate = { value: number; ci_low_95: number; ci_high_95: number; unit: string }

export type BAStatus = {
  ba_code: string
  name: string
  timezone: string
  status: 'hold_out_confirmed' | 'not_confirmed'
  scheduling_recommendation_validated: boolean
  realised_gap_2025: Estimate
  realised_gap_2025_derived: Estimate
  realised_gap_2026_ytd: Estimate
  eda_predicted_gap: number
  decision_rule: string
  summary: string
  eda_estimate_not_confirmed?: string
  data_caveats?: string[]
}

export type OvernightCheck = {
  local_hours: string
  what_this_is: string
  train: { marginal: Estimate; average: number }
  holdout_2025: { marginal: Estimate; average: number }
}

export type Findings = { validation: BAStatus; usage: { text: string }; overnight_check?: OvernightCheck }

export type MefRow = {
  month: number
  local_hour: number
  marginal: Estimate
  average_intensity_kg_per_mwh: number
  n_obs: number
}
export type MefResponse = { ba_code: string; rows: MefRow[]; usage: { text: string }; estimated_on: string }

export type Window = {
  start_local: string
  end_local: string
  window_marginal_mean: { value: number; ci_bounds_conservative: [number, number]; ci_note: string }
  window_average_intensity_kg_per_mwh: number
}
export type ScheduleResponse = {
  ba_code: string
  date: string
  duration_h: number
  load_mwh: number
  marginal_optimal_window: Window
  average_optimal_window: Window
  same_window: boolean
  usage: { text: string }
  validation: BAStatus
  recommendation:
    | { validated: true; label: string; advice: string; realised_saving_per_mwh_2025: Estimate;
        realised_saving_for_this_load_kg: { value: number; ci_low_95: number; ci_high_95: number; basis: string } }
    | { validated: false; label: string; advice: string }
  caveats: string[]
}

export type AskResponse = {
  question: string
  answer: string
  notes: string[]
  tool_calls: { name: string; args: Record<string, unknown>; result: unknown }[]
  draft_violations: string[][]
  used_fallback: boolean
  refused: boolean
  sources: string[]
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `HTTP ${r.status}`)
  return r.json()
}

export const api = {
  bas: () => get<BAStatus[]>('/api/bas'),
  findings: (ba: string) => get<Findings>(`/api/findings/${ba}`),
  mef: (ba: string, month: number) => get<MefResponse>(`/api/mef?ba=${ba}&month=${month}`),
  schedule: (q: URLSearchParams) => get<ScheduleResponse>(`/api/schedule?${q}`),
  ask: async (question: string): Promise<AskResponse> => {
    const r = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `HTTP ${r.status}`)
    return r.json()
  },
}

export const BA_LABEL: Record<string, string> = { ERCO: 'ERCOT', CISO: 'CAISO', MISO: 'MISO' }
export const fmt = (n: number, d = 0) => n.toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d })
export const ciText = (e: { ci_low_95: number; ci_high_95: number }) => `95% CI ${fmt(e.ci_low_95)} to ${fmt(e.ci_high_95)}`
