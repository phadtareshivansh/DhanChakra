import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import Dashboard from './pages/Dashboard'
import EntitySearch from './pages/EntitySearch'
import EntityDetail from './pages/EntityDetail'
import LoopsView from './pages/LoopsView'
import CasesView from './pages/CasesView'
import Worklist from './pages/Worklist'
import Ingest from './pages/Ingest'
import Settings from './pages/Settings'
import CaseExport from './pages/CaseExport'
import Login from './pages/Login'
import Layout from './components/Layout'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const [checked, setChecked] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const token = localStorage.getItem('dhanchakra_token')
    if (!token) {
      window.location.href = `/login?next=${encodeURIComponent(location.pathname)}`
    }
    setChecked(true)
  }, [])

  if (!checked) return null
  return <>{children}</>
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/search" element={<EntitySearch />} />
        <Route path="/worklist" element={<Worklist />} />
        <Route path="/entity/:id/network" element={<EntityDetail />} />
        <Route path="/loops" element={<LoopsView />} />
        <Route path="/cases" element={<CasesView />} />
        <Route path="/case/:id/export" element={<CaseExport />} />
        <Route path="/ingest" element={<Ingest />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default App