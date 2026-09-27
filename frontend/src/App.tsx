import { NavLink, Route, Routes } from 'react-router-dom'
import Ask from './pages/Ask'
import BAPage from './pages/BAPage'
import Overview from './pages/Overview'
import Schedule from './pages/Schedule'

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-2.5 py-1.5 text-sm ${isActive ? 'bg-surface-2 font-medium text-ink ring-1 ring-ring' : 'text-ink-2 hover:text-ink'}`

export default function App() {
  return (
    <div className="min-h-screen">
      <nav className="sticky top-0 z-10 border-b border-ring bg-page/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-1 px-4 py-2">
          <NavLink to="/" className="mr-3 font-semibold tracking-tight">Marginalis</NavLink>
          <NavLink to="/" end className={link}>Overview</NavLink>
          <NavLink to="/ba/MISO" className={link}>MISO</NavLink>
          <NavLink to="/ba/ERCO" className={link}>ERCOT</NavLink>
          <NavLink to="/ba/CISO" className={link}>CAISO</NavLink>
          <NavLink to="/schedule" className={link}>Scheduler</NavLink>
          <NavLink to="/ask" className={link}>Ask</NavLink>
        </div>
      </nav>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/ba/:code" element={<BAPage />} />
          <Route path="/schedule" element={<Schedule />} />
          <Route path="/ask" element={<Ask />} />
        </Routes>
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-10 text-xs text-muted">
        EIA-930 hourly data, 2019-07 to 2026-08. Estimates are frozen and pre-registered; see the repository for methods and limitations.
      </footer>
    </div>
  )
}
