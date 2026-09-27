import { AnimatePresence } from 'motion/react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { Footer, Nav, PageTransition, Preloader } from './components/Shell'
import { Cursor, ScrollProgress, SmoothScroll } from './lib/motion'
import Ask from './pages/Ask'
import BAPage from './pages/BAPage'
import Overview from './pages/Overview'
import Schedule from './pages/Schedule'

export default function App() {
  const location = useLocation()
  return (
    <SmoothScroll>
      <div className="grain min-h-screen">
        <Preloader />
        <Cursor />
        <ScrollProgress />
        <Nav />
        <AnimatePresence mode="wait">
          <PageTransition key={location.pathname}>
            <main>
              <Routes location={location}>
                <Route path="/" element={<Overview />} />
                <Route path="/ba/:code" element={<BAPage />} />
                <Route path="/schedule" element={<Schedule />} />
                <Route path="/ask" element={<Ask />} />
              </Routes>
            </main>
          </PageTransition>
        </AnimatePresence>
        <Footer />
      </div>
    </SmoothScroll>
  )
}
