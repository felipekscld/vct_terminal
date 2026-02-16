import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api } from './api/client'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import DashboardPage from './pages/Dashboard'
import MatchAnalysisPage from './pages/MatchAnalysis'
import StatsPage from './pages/Stats'
import LivePage from './pages/Live'
import SettingsPage from './pages/Settings'
import CrossMatchParlaysPage from './pages/CrossMatchParlays'

function App() {
  const [config, setConfig] = useState(null)
  const [configError, setConfigError] = useState('')

  useEffect(() => {
    api.getConfig()
      .then(setConfig)
      .catch((err) => setConfigError(err.message))
  }, [])

  return (
    <div className="min-h-screen px-3 py-4 md:px-6 md:py-6">
      <div className="mx-auto flex w-full max-w-[1400px] gap-4 md:gap-6">
        <Sidebar />

        <div className="flex min-h-[85vh] flex-1 flex-col gap-4 md:gap-6">
          <Header warning={configError} />

          <main className="flex-1">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/match/:id" element={<MatchAnalysisPage />} />
              <Route path="/parlays" element={<CrossMatchParlaysPage />} />
              <Route path="/stats" element={<StatsPage />} />
              <Route path="/live/:id" element={<LivePage />} />
              <Route path="/settings" element={<SettingsPage config={config} onConfigUpdate={setConfig} />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </div>
  )
}

export default App
