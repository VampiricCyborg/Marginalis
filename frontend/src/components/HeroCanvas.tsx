import { useReducedMotion } from 'motion/react'
import { useEffect, useRef } from 'react'

/* Generative hero (illustrative, labelled on-canvas as not data): two drifting "intensity" curves (marginal blue, average orange) across a
   24-hour grid, with particles riding the marginal curve. The pointer bends the curves.
   Purely decorative — no data is implied — so it's aria-hidden. */
export function HeroCanvas({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const reduce = useReducedMotion()

  useEffect(() => {
    const canvas = ref.current!
    const ctx = canvas.getContext('2d')!
    let w = 0, h = 0, dpr = 1, raf = 0, running = true
    const mouse = { x: -9999, y: -9999, tx: -9999, ty: -9999 }
    const css = getComputedStyle(canvas)
    const col = (v: string, fb: string) => css.getPropertyValue(v).trim() || fb
    const C = { m: col('--marginal', '#2a78d6'), a: col('--average', '#eb6834'), grid: col('--grid', '#ddd'), muted: col('--muted', '#888') }

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      const r = canvas.getBoundingClientRect()
      w = r.width; h = r.height
      canvas.width = w * dpr; canvas.height = h * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      if (reduce) requestAnimationFrame(draw)
    }

    const parts = Array.from({ length: 70 }, () => ({ u: Math.random(), s: 0.0006 + Math.random() * 0.0016, r: 1 + Math.random() * 2.2 }))

    const curve = (u: number, t: number, kind: 'm' | 'a') => {
      const base = kind === 'm'
        ? 0.52 + 0.16 * Math.sin(u * Math.PI * 2 + t * 0.35) + 0.07 * Math.sin(u * 11 + t * 0.9)
        : 0.62 - 0.12 * Math.sin((u - 0.1) * Math.PI * 2 + t * 0.22) + 0.02 * Math.sin(u * 7 + t * 0.5)
      let y = base * h
      const x = u * w
      const dx = x - mouse.x, dy = y - mouse.y
      const d2 = dx * dx + dy * dy
      const pull = Math.exp(-d2 / (2 * 140 * 140))
      y += (mouse.y - y) * pull * (kind === 'm' ? 0.35 : 0.18)
      return y
    }

    const draw = (ms: number) => {
      const t = reduce ? 0 : ms / 1000
      mouse.x += (mouse.tx - mouse.x) * 0.08; mouse.y += (mouse.ty - mouse.y) * 0.08
      ctx.clearRect(0, 0, w, h)
      // hour grid
      ctx.strokeStyle = C.grid; ctx.lineWidth = 1
      ctx.fillStyle = C.muted; ctx.font = '10px "JetBrains Mono Variable", monospace'
      for (let i = 0; i <= 24; i++) {
        const x = Math.round((i / 24) * w) + 0.5
        ctx.globalAlpha = i % 6 === 0 ? 0.9 : 0.35
        ctx.beginPath(); ctx.moveTo(x, h * 0.18); ctx.lineTo(x, h); ctx.stroke()
      }
      ctx.globalAlpha = 1
      ctx.fillText('ILLUSTRATIVE · NOT DATA', 12, h - 10)
      // curves
      const N = 120
      for (const k of ['a', 'm'] as const) {
        ctx.beginPath()
        for (let i = 0; i <= N; i++) {
          const u = i / N, y = curve(u, t, k)
          if (i) ctx.lineTo(u * w, y); else ctx.moveTo(0, y)
        }
        ctx.strokeStyle = k === 'm' ? C.m : C.a
        ctx.lineWidth = k === 'm' ? 2.5 : 2
        ctx.stroke()
        if (k === 'm') {
          // soft band under marginal
          ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath()
          const g = ctx.createLinearGradient(0, h * 0.3, 0, h)
          g.addColorStop(0, C.m + '26'); g.addColorStop(1, C.m + '00')
          ctx.fillStyle = g; ctx.fill()
        }
      }
      // particles riding the marginal curve
      ctx.fillStyle = C.m
      for (const p of parts) {
        if (!reduce) p.u = (p.u + p.s) % 1
        const y = curve(p.u, t, 'm')
        ctx.globalAlpha = 0.35 + 0.65 * Math.sin(p.u * Math.PI)
        ctx.beginPath(); ctx.arc(p.u * w, y, p.r, 0, Math.PI * 2); ctx.fill()
      }
      ctx.globalAlpha = 1
      // scanning "now" line
      const sx = ((t * 0.04) % 1) * w
      ctx.strokeStyle = C.muted; ctx.setLineDash([3, 5])
      ctx.beginPath(); ctx.moveTo(sx, h * 0.18); ctx.lineTo(sx, h); ctx.stroke(); ctx.setLineDash([])
      for (const k of ['m', 'a'] as const) {
        ctx.fillStyle = k === 'm' ? C.m : C.a
        ctx.beginPath(); ctx.arc(sx, curve(sx / w, t, k), 5, 0, Math.PI * 2); ctx.fill()
      }
      if (running && !reduce) raf = requestAnimationFrame(draw)
    }
    resize()
    const ro = new ResizeObserver(resize); ro.observe(canvas)
    raf = requestAnimationFrame(draw)

    const move = (e: PointerEvent) => { const r = canvas.getBoundingClientRect(); mouse.tx = e.clientX - r.left; mouse.ty = e.clientY - r.top }
    const leave = () => { mouse.tx = -9999; mouse.ty = -9999 }
    window.addEventListener('pointermove', move)
    canvas.addEventListener('pointerleave', leave)
    const io = new IntersectionObserver(([e]) => {
      const was = running; running = e.isIntersecting
      if (running && !was && !reduce) raf = requestAnimationFrame(draw)
    })
    io.observe(canvas)
    return () => { cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); window.removeEventListener('pointermove', move) }
  }, [reduce])

  return <canvas ref={ref} aria-hidden className={`block h-full w-full ${className}`} />
}
