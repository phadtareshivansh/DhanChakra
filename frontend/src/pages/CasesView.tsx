import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api from '../utils/api'
import {
  AssignableUser,
  Case,
  CaseActivityEntry,
  CaseComment,
  CaseEntityLink,
} from '../types/api'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import Input from '../components/ui/Input'
import Modal from '../components/ui/Modal'
import Select from '../components/ui/Select'
import Skeleton, { SkeletonText } from '../components/ui/Skeleton'
import Drawer from '../components/ui/Drawer'
import { useToast } from '../components/ui/Toast'
import InfoHint from '../components/InfoHint'
import { formatDate, initials, relativeTime, titleCase, truncateMiddle } from '../utils/format'
import { RISK_THRESHOLDS } from '../config/risk'

const STATUSES = ['open', 'in_progress', 'closed'] as const
type Status = (typeof STATUSES)[number]

const STATUS_META: Record<string, { label: string; tone: 'accent' | 'amber' | 'neutral'; accent: string }> = {
  open: { label: 'Open', tone: 'accent', accent: 'var(--color-accent)' },
  in_progress: { label: 'In progress', tone: 'amber', accent: 'var(--color-amber)' },
  closed: { label: 'Closed', tone: 'neutral', accent: 'var(--color-text-disabled)' },
}

function priorityLabel(priority: number): string {
  return priority >= 2 ? 'P2 · Critical' : priority === 1 ? 'P1 · Priority' : 'P0 · Standard'
}

export default function CasesView() {
  const [params] = useSearchParams()
  const toast = useToast()
  const highlight = params.get('highlight')
  const [cases, setCases] = useState<Case[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'board' | 'list'>(() => {
    const stored = localStorage.getItem('dhanchakra_cases_view')
    return stored === 'list' ? 'list' : 'board'
  })
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [newCase, setNewCase] = useState({ title: '', description: '', company_cin: '', priority: 0, assignee_id: '' })
  const [creating, setCreating] = useState(false)
  const [users, setUsers] = useState<AssignableUser[]>([])
  const [usersError, setUsersError] = useState(false)
  const [selected, setSelected] = useState<Case | null>(null)
  const [comments, setComments] = useState<CaseComment[]>([])
  const [activity, setActivity] = useState<CaseActivityEntry[]>([])
  const [caseEntities, setCaseEntities] = useState<CaseEntityLink[]>([])
  const [drawerLoading, setDrawerLoading] = useState(false)
  const [commentDraft, setCommentDraft] = useState('')
  const [commenting, setCommenting] = useState(false)
  const [entityCin, setEntityCin] = useState('')
  const [linking, setLinking] = useState(false)
  const [exporting, setExporting] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [dragId, setDragId] = useState<string | null>(null)
  const openedHighlight = useRef(false)

  useEffect(() => {
    localStorage.setItem('dhanchakra_cases_view', view)
  }, [view])

  const fetchCases = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<Case[]>(`/cases${statusFilter ? `?status=${statusFilter}` : ''}`)
      setCases(res.data)
      if (highlight && !openedHighlight.current) {
        const match = res.data.find((item) => item.id === highlight)
        if (match) {
          setSelected(match)
          openedHighlight.current = true
        }
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail?.message || 'Could not load case files.')
    } finally {
      setLoading(false)
    }
  }, [statusFilter, highlight])

  useEffect(() => { fetchCases() }, [fetchCases])

  useEffect(() => {
    api.get<AssignableUser[]>('/users/assignable')
      .then((res) => setUsers(res.data))
      .catch(() => setUsersError(true))
  }, [])

  const loadDrawer = useCallback(async (caseId: string) => {
    setDrawerLoading(true)
    try {
      const [commentsRes, activityRes, entitiesRes] = await Promise.all([
        api.get<CaseComment[]>(`/cases/${caseId}/comments`),
        api.get<CaseActivityEntry[]>(`/cases/${caseId}/activity`),
        api.get<CaseEntityLink[]>(`/cases/${caseId}/entities`),
      ])
      setComments(commentsRes.data)
      setActivity(activityRes.data)
      setCaseEntities(entitiesRes.data)
    } catch {
      toast.push({ title: 'Could not load case details', tone: 'critical' })
    } finally {
      setDrawerLoading(false)
    }
  }, [toast])

  useEffect(() => {
    if (!selected) return
    setCommentDraft('')
    setEntityCin('')
    loadDrawer(selected.id)
  }, [selected?.id, loadDrawer])

  const patchCase = async (target: Case, patch: Partial<Case>, successTitle: string) => {
    try {
      const res = await api.patch<Case>(`/cases/${target.id}`, patch)
      setCases((current) => current.map((item) => (item.id === target.id ? res.data : item)))
      setSelected((current) => (current?.id === target.id ? res.data : current))
      toast.push({ title: successTitle, tone: 'success' })
      loadDrawer(target.id)
    } catch (err: any) {
      toast.push({ title: 'Update failed', description: err?.response?.data?.detail?.message, tone: 'critical' })
    }
  }

  const createCase = async () => {
    if (!newCase.title.trim()) return
    setCreating(true)
    try {
      const res = await api.post<Case>('/cases', {
        title: newCase.title.trim(),
        description: newCase.description.trim() || undefined,
        company_cin: newCase.company_cin.trim() || undefined,
        priority: Number(newCase.priority),
        assignee_id: newCase.assignee_id || undefined,
      })
      setCases((current) => [res.data, ...current])
      setCreateOpen(false)
      setNewCase({ title: '', description: '', company_cin: '', priority: 0, assignee_id: '' })
      toast.push({ title: 'Case created', description: res.data.title, tone: 'success' })
      setSelected(res.data)
    } catch (err: any) {
      toast.push({ title: 'Could not create case', description: err?.response?.data?.detail?.message, tone: 'critical' })
    } finally {
      setCreating(false)
    }
  }

  const addComment = async () => {
    if (!selected || !commentDraft.trim()) return
    setCommenting(true)
    try {
      const res = await api.post<CaseComment>(`/cases/${selected.id}/comments`, { body: commentDraft.trim() })
      setComments((current) => [...current, res.data])
      setCommentDraft('')
      const activityRes = await api.get<CaseActivityEntry[]>(`/cases/${selected.id}/activity`)
      setActivity(activityRes.data)
    } catch (err: any) {
      toast.push({ title: 'Could not add comment', description: err?.response?.data?.detail?.message, tone: 'critical' })
    } finally {
      setCommenting(false)
    }
  }

  const linkEntity = async () => {
    if (!selected || !entityCin.trim()) return
    setLinking(true)
    try {
      const res = await api.post<CaseEntityLink>(`/cases/${selected.id}/entities`, { entity_cin: entityCin.trim() })
      setCaseEntities((current) => [...current.filter((item) => item.entity_cin !== res.data.entity_cin), res.data])
      setEntityCin('')
      toast.push({ title: 'Entity linked to case', tone: 'success' })
      const activityRes = await api.get<CaseActivityEntry[]>(`/cases/${selected.id}/activity`)
      setActivity(activityRes.data)
    } catch (err: any) {
      toast.push({ title: 'Could not link entity', description: err?.response?.data?.detail?.message, tone: 'critical' })
    } finally {
      setLinking(false)
    }
  }

  const unlinkEntity = async (cin: string) => {
    if (!selected) return
    try {
      await api.delete(`/cases/${selected.id}/entities/${cin}`)
      setCaseEntities((current) => current.filter((item) => item.entity_cin !== cin))
      const activityRes = await api.get<CaseActivityEntry[]>(`/cases/${selected.id}/activity`)
      setActivity(activityRes.data)
    } catch (err: any) {
      toast.push({ title: 'Could not unlink entity', description: err?.response?.data?.detail?.message, tone: 'critical' })
    }
  }

  const exportCase = async (target: Case) => {
    setExporting(target.id)
    try {
      const res = await api.post(`/cases/${target.id}/export?include_network=true`)
      const blob = new Blob([JSON.stringify(res.data.payload, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `dhan-chakra-case-${target.id.slice(0, 8)}.json`
      anchor.click()
      URL.revokeObjectURL(url)
      setDone(target.id)
      setTimeout(() => setDone(null), 3000)
      toast.push({ title: 'Case bundle exported', tone: 'success' })
    } catch (err: any) {
      toast.push({ title: 'Export failed', description: err?.response?.data?.detail?.message, tone: 'critical' })
    } finally {
      setExporting(null)
    }
  }

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return cases.filter((item) => {
      if (statusFilter && item.status !== statusFilter) return false
      if (!query) return true
      return [item.title, item.description, item.company_cin, item.assignee_id]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query))
    })
  }, [cases, search, statusFilter])

  const byStatus = (status: Status) => filtered.filter((item) => item.status === status)
  const assigneeName = (caseItem: Case) => {
    if (!caseItem.assignee_id) return 'Unassigned'
    const user = users.find((candidate) => candidate.id === caseItem.assignee_id)
    return user?.display_name || user?.email || 'Assigned'
  }
  const assigneeOptions = [
    { value: '', label: 'Unassigned' },
    ...users.map((user) => ({ value: user.id, label: `${user.display_name || user.email} · ${titleCase(user.role)}` })),
  ]

  const dropOn = (status: Status, caseId: string | null) => {
    setDragId(null)
    const target = cases.find((item) => item.id === caseId)
    if (target && target.status !== status) {
      patchCase(target, { status }, `Moved to ${titleCase(status)}`)
    }
  }

  const drawerOpen = selected !== null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="micro-label text-accent-ring">Investigations</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Case files</h1>
          <p className="mt-1 max-w-2xl text-sm text-text-secondary">
            Open, assign and resolve investigations. Every status change, comment and label is preserved in the case timeline.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-border p-0.5" role="group" aria-label="Case view">
            <button
              type="button"
              onClick={() => setView('board')}
              aria-pressed={view === 'board'}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${view === 'board' ? 'bg-raised text-text-primary' : 'text-text-secondary hover:text-text-primary'}`}
            >
              Board
            </button>
            <button
              type="button"
              onClick={() => setView('list')}
              aria-pressed={view === 'list'}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${view === 'list' ? 'bg-raised text-text-primary' : 'text-text-secondary hover:text-text-primary'}`}
            >
              List
            </button>
          </div>
          <Button onClick={() => setCreateOpen(true)}>New case</Button>
        </div>
      </div>

      <div className="panel flex flex-wrap items-center gap-3 p-3">
        <div className="min-w-52 flex-1">
          <Input
            inputSize="sm"
            placeholder="Search title, CIN or description"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            leadingIcon={
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            }
          />
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by status">
          {['', ...STATUSES].map((status) => (
            <button
              key={status || 'all'}
              type="button"
              onClick={() => setStatusFilter(status)}
              aria-pressed={statusFilter === status}
              className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                statusFilter === status
                  ? 'border-accent bg-accent/15 text-accent-ring'
                  : 'border-border text-text-secondary hover:bg-raised hover:text-text-primary'
              }`}
            >
              {status ? STATUS_META[status].label : 'All'}
              <span className="ml-1 font-mono text-[10px] text-text-disabled">
                {status ? cases.filter((item) => item.status === status).length : cases.length}
              </span>
            </button>
          ))}
        </div>
        {usersError && (
          <span className="text-xs text-risk-high">
            Assignee list unavailable; check your session.
          </span>
        )}
      </div>

      {error ? (
        <div className="panel p-8 text-center" role="alert">
          <p className="text-sm font-medium text-risk-critical">{error}</p>
          <Button variant="secondary" className="mt-4" onClick={fetchCases}>Retry</Button>
        </div>
      ) : loading ? (
        view === 'board' ? (
          <div className="grid gap-4 lg:grid-cols-3">
            {STATUSES.map((status) => (
              <div key={status} className="panel p-3">
                <Skeleton className="h-3 w-24" />
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={index} className="mt-3 rounded-lg border border-border p-3">
                    <Skeleton className="h-3 w-4/5" />
                    <Skeleton className="mt-2 h-3 w-2/5" />
                  </div>
                ))}
              </div>
            ))}
          </div>
        ) : (
          <div className="panel p-5"><SkeletonText lines={8} /></div>
        )
      ) : view === 'board' ? (
        <div className="grid gap-4 lg:grid-cols-3">
          {STATUSES.map((status) => {
            const columnCases = byStatus(status)
            const meta = STATUS_META[status]
            return (
              <section
                key={status}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => dropOn(status, dragId)}
                className="panel flex min-h-[18rem] flex-col p-3"
                aria-label={`${meta.label} cases`}
              >
                <div className="flex items-center justify-between px-1 pb-2">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: meta.accent }} aria-hidden="true" />
                    <h2 className="text-sm font-semibold">{meta.label}</h2>
                    <Badge tone={meta.tone}>{columnCases.length}</Badge>
                  </div>
                </div>
                <div className="flex-1 space-y-2">
                  {columnCases.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-border px-3 py-8 text-center text-xs text-text-disabled">
                      No {meta.label.toLowerCase()} cases
                    </div>
                  ) : (
                    columnCases.map((caseItem) => (
                      <article
                        key={caseItem.id}
                        draggable
                        onDragStart={() => setDragId(caseItem.id)}
                        onDragEnd={() => setDragId(null)}
                        onClick={() => setSelected(caseItem)}
                        onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelected(caseItem) } }}
                        tabIndex={0}
                        role="button"
                        className={`cursor-pointer rounded-lg border bg-canvas p-3 transition-colors hover:border-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-ring ${
                          highlight === caseItem.id ? 'border-accent ring-1 ring-accent/40' : 'border-border'
                        } ${dragId === caseItem.id ? 'opacity-50' : ''}`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="line-clamp-2 text-sm font-medium">{caseItem.title}</h3>
                          {caseItem.risk_score > 0 && (
                            <span
                              className="shrink-0 font-mono text-xs"
                              style={{ color: caseItem.risk_score >= RISK_THRESHOLDS.critical ? 'var(--color-risk-critical)' : caseItem.risk_score >= RISK_THRESHOLDS.high ? 'var(--color-risk-high)' : 'var(--color-risk-medium)' }}
                              title={`Entity risk score ${Math.round(caseItem.risk_score)}`}
                            >
                              {Math.round(caseItem.risk_score)}
                            </span>
                          )}
                        </div>
                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                          <Badge tone={caseItem.priority >= 2 ? 'critical' : caseItem.priority === 1 ? 'amber' : 'neutral'}>
                            {priorityLabel(caseItem.priority).split(' · ')[0]}
                          </Badge>
                          {caseItem.company_cin && (
                            <span className="truncate font-mono text-[10px] text-text-disabled">
                              {truncateMiddle(caseItem.company_cin, 18)}
                            </span>
                          )}
                        </div>
                        <div className="mt-2 flex items-center justify-between gap-2 border-t border-border pt-2">
                          <span className="flex min-w-0 items-center gap-1.5 text-[11px] text-text-secondary">
                            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-raised text-[9px] font-semibold">
                              {initials(assigneeName(caseItem) === 'Unassigned' ? '?' : assigneeName(caseItem))}
                            </span>
                            <span className="truncate">{assigneeName(caseItem)}</span>
                          </span>
                          <time className="shrink-0 text-[10px] text-text-disabled">{relativeTime(caseItem.updated_at)}</time>
                        </div>
                      </article>
                    ))
                  )}
                </div>
              </section>
            )
          })}
        </div>
      ) : (
        <div className="panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead className="bg-raised/60 text-left text-micro uppercase tracking-micro text-text-secondary">
                <tr>
                  <th className="px-4 py-2.5">Case</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5">Priority</th>
                  <th className="px-4 py-2.5">Assignee</th>
                  <th className="px-4 py-2.5">Company CIN</th>
                  <th className="px-4 py-2.5">Updated</th>
                  <th className="px-4 py-2.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((caseItem) => (
                  <tr
                    key={caseItem.id}
                    onClick={() => setSelected(caseItem)}
                    className={`cursor-pointer border-t border-border hover:bg-raised/40 ${highlight === caseItem.id ? 'bg-accent/10' : ''}`}
                  >
                    <td className="max-w-[22rem] px-4 py-2.5">
                      <p className="truncate font-medium">{caseItem.title}</p>
                      {caseItem.description && <p className="truncate text-xs text-text-secondary">{caseItem.description}</p>}
                    </td>
                    <td className="px-4 py-2.5" onClick={(event) => event.stopPropagation()}>
                      <Select
                        selectSize="sm"
                        value={caseItem.status}
                        onChange={(event) => patchCase(caseItem, { status: event.target.value }, 'Status updated')}
                        options={STATUSES.map((status) => ({ value: status, label: STATUS_META[status].label }))}
                        aria-label={`Status for ${caseItem.title}`}
                      />
                    </td>
                    <td className="px-4 py-2.5"><Badge tone={caseItem.priority >= 2 ? 'critical' : caseItem.priority === 1 ? 'amber' : 'neutral'}>{priorityLabel(caseItem.priority)}</Badge></td>
                    <td className="px-4 py-2.5 text-xs">{assigneeName(caseItem)}</td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-text-secondary">{caseItem.company_cin || '—'}</td>
                    <td className="px-4 py-2.5 text-xs text-text-secondary">{formatDate(caseItem.updated_at)}</td>
                    <td className="px-4 py-2.5" onClick={(event) => event.stopPropagation()}>
                      <div className="flex justify-end gap-1.5">
                        <Link to={`/case/${caseItem.id}/export`} className="btn-secondary btn-compact">Preview</Link>
                        <Button size="sm" variant="secondary" onClick={() => exportCase(caseItem)} loading={exporting === caseItem.id}>
                          {done === caseItem.id ? 'Exported' : 'Export'}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length === 0 && (
            <EmptyState
              title={cases.length === 0 ? 'No cases yet' : 'No cases match this view'}
              description={cases.length === 0 ? 'Open a case from the worklist or entity page, or create one here.' : 'Try a different status or clear the search.'}
              action={cases.length === 0 ? <Button onClick={() => setCreateOpen(true)}>New case</Button> : <Button variant="secondary" onClick={() => { setSearch(''); setStatusFilter('') }}>Clear filters</Button>}
            />
          )}
        </div>
      )}

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="New case"
        description="Open an investigation against an entity or a ring."
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button onClick={createCase} loading={creating} disabled={!newCase.title.trim()}>Create case</Button>
          </div>
        }
      >
        <div className="space-y-3">
          <Input
            label="Title"
            required
            placeholder="e.g. Circular trading — Maya Trading cluster"
            value={newCase.title}
            onChange={(event) => setNewCase({ ...newCase, title: event.target.value })}
            autoFocus
          />
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary" htmlFor="case-description">Description</label>
            <textarea
              id="case-description"
              rows={3}
              className="w-full rounded-lg border border-border bg-canvas p-3 text-sm text-text-primary placeholder:text-text-disabled focus:border-accent-ring focus:outline-none focus:ring-2 focus:ring-accent-ring"
              placeholder="What is the suspected conduct and what evidence should be checked first?"
              value={newCase.description}
              onChange={(event) => setNewCase({ ...newCase, description: event.target.value })}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="Company CIN"
              placeholder="L12345MH2020PLC123456"
              value={newCase.company_cin}
              onChange={(event) => setNewCase({ ...newCase, company_cin: event.target.value })}
              className="font-mono"
            />
            <Select
              label="Priority"
              value={newCase.priority}
              onChange={(event) => setNewCase({ ...newCase, priority: Number(event.target.value) })}
              options={[
                { value: '0', label: 'P0 · Standard' },
                { value: '1', label: 'P1 · Priority' },
                { value: '2', label: 'P2 · Critical' },
              ]}
            />
          </div>
          <Select
            label="Assignee"
            value={newCase.assignee_id}
            onChange={(event) => setNewCase({ ...newCase, assignee_id: event.target.value })}
            options={assigneeOptions}
            hint="You can change ownership later."
          />
        </div>
      </Modal>

      <Drawer
        open={drawerOpen}
        onClose={() => setSelected(null)}
        title={selected?.title || 'Case'}
        description={selected ? `Case ${selected.id.slice(0, 8)} · updated ${relativeTime(selected.updated_at)}` : undefined}
        size="lg"
        footer={
          selected && (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Link to={`/case/${selected.id}/export`} className="btn-secondary btn-compact">Preview bundle</Link>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" onClick={() => exportCase(selected)} loading={exporting === selected.id}>Export JSON</Button>
                <Button size="sm" onClick={() => setSelected(null)}>Done</Button>
              </div>
            </div>
          )
        }
      >
        {selected && (
          <div className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-2">
              <Select
                label="Status"
                value={selected.status}
                onChange={(event) => patchCase(selected, { status: event.target.value }, 'Status updated')}
                options={STATUSES.map((status) => ({ value: status, label: STATUS_META[status].label }))}
              />
              <Select
                label="Assignee"
                value={selected.assignee_id || ''}
                onChange={(event) => patchCase(selected, { assignee_id: event.target.value }, 'Assignee updated')}
                options={assigneeOptions}
              />
              <div>
                <span className="micro-label">Priority</span>
                <div className="mt-1.5"><Badge tone={selected.priority >= 2 ? 'critical' : selected.priority === 1 ? 'amber' : 'neutral'}>{priorityLabel(selected.priority)}</Badge></div>
              </div>
              <div>
                <span className="micro-label">Opened</span>
                <p className="mt-1.5 text-sm">{formatDate(selected.created_at, true)}</p>
              </div>
            </div>

            {selected.description && (
              <div className="rounded-lg border border-border bg-raised/40 p-3">
                <p className="whitespace-pre-wrap text-sm text-text-secondary">{selected.description}</p>
              </div>
            )}

            <div>
              <div className="flex items-center justify-between">
                <h3 className="flex items-center gap-1.5 text-sm font-semibold">
                  Linked entities
                  <InfoHint content="Entities attached to this case. Linking does not change their score; it keeps evidence together for the investigation." />
                </h3>
                <Badge tone="neutral">{caseEntities.length}</Badge>
              </div>
              <div className="mt-2 flex gap-2">
                <Input
                  inputSize="sm"
                  placeholder="CIN to link"
                  value={entityCin}
                  onChange={(event) => setEntityCin(event.target.value)}
                  onKeyDown={(event) => { if (event.key === 'Enter') linkEntity() }}
                  className="font-mono"
                />
                <Button size="sm" variant="secondary" onClick={linkEntity} loading={linking} disabled={!entityCin.trim()}>Link</Button>
              </div>
              {caseEntities.length === 0 ? (
                <p className="mt-2 text-xs text-text-secondary">No entities linked yet. The primary company CIN is in the case metadata.</p>
              ) : (
                <ul className="mt-2 divide-y divide-border">
                  {caseEntities.map((link) => (
                    <li key={link.entity_cin} className="flex items-center justify-between gap-2 py-2">
                      <Link to={`/entity/${link.entity_cin}/network`} className="font-mono text-xs text-accent-ring hover:underline">
                        {link.entity_cin}
                      </Link>
                      <button type="button" onClick={() => unlinkEntity(link.entity_cin)} className="text-xs text-text-secondary hover:text-risk-critical">
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {selected.company_cin && (
                <div className="mt-2 flex items-center gap-2 text-xs text-text-secondary">
                  Primary entity:
                  <Link to={`/entity/${selected.company_cin}/network`} className="font-mono text-accent-ring hover:underline">
                    {selected.company_cin}
                  </Link>
                </div>
              )}
            </div>

            <div>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">Comments</h3>
                <Badge tone="neutral">{comments.length}</Badge>
              </div>
              {drawerLoading ? (
                <div className="mt-3"><SkeletonText lines={3} /></div>
              ) : comments.length === 0 ? (
                <p className="mt-2 text-xs text-text-secondary">No comments yet. Add the first note for the investigating team.</p>
              ) : (
                <ul className="mt-2 divide-y divide-border">
                  {comments.map((comment) => (
                    <li key={comment.id} className="py-2.5">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-xs font-medium">{comment.author_name || 'Analyst'}</span>
                        <time className="text-[11px] text-text-disabled" dateTime={comment.created_at}>{relativeTime(comment.created_at)}</time>
                      </div>
                      <p className="mt-1 whitespace-pre-wrap text-sm text-text-secondary">{comment.body}</p>
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-2">
                <textarea
                  rows={2}
                  className="w-full rounded-lg border border-border bg-canvas p-2.5 text-sm text-text-primary placeholder:text-text-disabled focus:border-accent-ring focus:outline-none focus:ring-2 focus:ring-accent-ring"
                  placeholder="Add a comment for the case team…"
                  value={commentDraft}
                  onChange={(event) => setCommentDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) addComment()
                  }}
                />
                <div className="mt-1.5 flex items-center justify-between">
                  <span className="text-[11px] text-text-disabled">⌘/Ctrl + Enter to post</span>
                  <Button size="sm" onClick={addComment} loading={commenting} disabled={!commentDraft.trim()}>Post comment</Button>
                </div>
              </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold">Activity timeline</h3>
              {drawerLoading ? (
                <div className="mt-3"><SkeletonText lines={4} /></div>
              ) : activity.length === 0 ? (
                <p className="mt-2 text-xs text-text-secondary">No recorded activity yet.</p>
              ) : (
                <ol className="mt-3">
                  {activity.map((entry, index) => (
                    <li key={entry.id} className="relative flex gap-3 pb-3 last:pb-0">
                      <span className="relative flex flex-col items-center">
                        <span className="mt-1.5 h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
                        {index < activity.length - 1 && <span className="mt-1 w-px flex-1 bg-border" aria-hidden="true" />}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium">{titleCase(entry.action)}</p>
                        <p className="text-[11px] text-text-secondary">
                          {entry.actor_name || 'System'} · {relativeTime(entry.created_at)}
                          {entry.detail?.preview ? ` · ${entry.detail.preview}` : ''}
                          {entry.detail?.entity_cin ? ` · ${entry.detail.entity_cin}` : ''}
                          {entry.detail?.from ? ` · ${entry.detail.from} → ${entry.detail.to}` : ''}
                          {entry.detail?.count ? ` · ${entry.detail.count} entities` : ''}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  )
}
