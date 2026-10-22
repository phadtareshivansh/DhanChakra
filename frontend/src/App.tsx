import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { lazy, Suspense, useEffect, useState } from 'react'
import Dashboard from './pages/Dashboard'
import EntitySearch from './pages/EntitySearch'
import EntityDetail from './pages/EntityDetail'
import LoopsView from './pages/LoopsView'
import CasesView from './pages/CasesView'
import Worklist from './pages/Worklist'
import Ingest from './pages/Ingest'
import Settings from './pages/Settings'
import AdminUsers from './pages/AdminUsers'
import CaseExport from './pages/CaseExport'
import DesignSystem from './pages/DesignSystem'
import Login from './pages/Login'
import Layout from './components/Layout'

const GraphWorkspace = lazy(() => import('./pages/GraphWorkspace'))

function GraphWorkspaceRoute() {
  return (
    <Suspense
      fallback={
        <div className="flex h-[calc(100vh-8rem)] items-center justify-center">
          <div className="text-center">
            <div className="mx-auto h-9 w-9 animate-spin rounded-full border-2 border-border border-t-accent-ring" />
            <p className="mt-3 text-sm text-text-secondary">Loading graph workspace…</p>
          </div>
        </div>
      }
    >
      <GraphWorkspace />
    </Suspense>
  )
}

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
        <Route path="/graph" element={<GraphWorkspaceRoute />} />
        <Route path="/graph/:id" element={<GraphWorkspaceRoute />} />
        <Route path="/entity/:id/network" element={<EntityDetail />} />
        <Route path="/loops" element={<LoopsView />} />
        <Route path="/cases" element={<CasesView />} />
        <Route path="/case/:id/export" element={<CaseExport />} />
        <Route path="/ingest" element={<Ingest />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/admin/users" element={<AdminUsers />} />
        <Route path="/design-system" element={<DesignSystem />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default App