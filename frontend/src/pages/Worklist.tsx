import { t } from '../i18n'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../utils/api'
import {
  AssignableUser,
  Case,
  EntityAssignment,
  WorklistFacets,
  WorklistItem,
  WorklistResponse,
} from '../types/api'
import { RISK_THRESHOLDS, riskBand } from '../config/risk'
import RiskBadge from '../components/RiskBadge'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import FilterChips from '../components/ui/FilterChips'
import Input from '../components/ui/Input'
import Modal from '../components/ui/Modal'
import Pagination from '../components/ui/Pagination'
import Select from '../components/ui/Select'
import Skeleton from '../components/ui/Skeleton'
import { useToast } from '../components/ui/Toast'
import InfoHint from '../components/InfoHint'
import { formatDate, formatInr, initials, titleCase } from '../utils/format'

type SortKey = 'risk_score' | 'name' | 'paid_up_capital'
type Direction = 'asc' | 'desc'

interface Filters {
  q: string
  state: string
  sector: string
  minScore: string
  maxScore: string
  hasCycles: boolean
  bands: string[]
}

interface SavedView {
  id: string
  name: string
  filters: Filters
  sort: SortKey
  direction: Direction
}

const EMPTY_FILTERS: Filters = {
  q: '',
  state: '',
  sector: '',
  minScore: '',
  maxScore: '',
  hasCycles: false,
  bands: [],
}

const VIEWS_KEY = 'dhanchakra_worklist_views_v1'
const PAGE_SIZE = 20

function bandBounds(bands: string[]): { min: string; max: string } {
  if (bands.length === 0) return { min: '', max: '' }
  const lower: Record<string, number> = {
    critical: RISK_THRESHOLDS.critical,
    high: RISK_THRESHOLDS.high,
    medium: RISK_THRESHOLDS.medium,
    low: 0,
  }
  const upper: Record<string, string> = {
    critical: '',
    high: String(RISK_THRESHOLDS.critical),
    medium: String(RISK_THRESHOLDS.high),
    low: String(RISK_THRESHOLDS.medium),
  }
  return {
    min: String(Math.min(...bands.map((band) => lower[band] ?? 0))),
    max: bands.includes('critical') ? '' : String(Math.max(...bands.map((band) => Number(upper[band]) || 100))),
  }
}

function activeFilterCount(filters: Filters): number {
  return [
    filters.q,
    filters.state,
    filters.sector,
    filters.minScore,
    filters.maxScore,
    filters.hasCycles ? '1' : '',
  ].filter(Boolean).length + filters.bands.length
}

export default function Worklist() {
  const navigate = useNavigate()
  const toast = useToast()
  const [data, setData] = useState<WorklistResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [sort, setSort] = useState<SortKey>('risk_score')
  const [direction, setDirection] = useState<Direction>('desc')
  const [page, setPage] = useState(1)
  const [facets, setFacets] = useState<WorklistFacets | null>(null)
  const [assignments, setAssignments] = useState<Record<string, EntityAssignment>>({})
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkModal, setBulkModal] = useState<'assign' | 'label' | 'case' | null>(null)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [assigneeId, setAssigneeId] = useState('')
  const [label, setLabel] = useState('needs_review')
  const [caseId, setCaseId] = useState('')
  const [users, setUsers] = useState<AssignableUser[]>([])
  const [cases, setCases] = useState<Case[]>([])
  const [views, setViews] = useState<SavedView[]>([])
  const [saveOpen, setSaveOpen] = useState(false)
  const [viewName, setViewName] = useState('')
  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})

  useEffect(() => {
    try {
      const stored = localStorage.getItem(VIEWS_KEY)
      if (stored) setViews(JSON.parse(stored))
    } catch {
      setViews([])
    }
  }, [])

  const persistViews = (next: SavedView[]) => {
    setViews(next)
    localStorage.setItem(VIEWS_KEY, JSON.stringify(next))
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        sort,
        direction,
        page: String(page),
        page_size: String(PAGE_SIZE),
      })
      if (filters.q) params.set('q', filters.q)
      if (filters.state) params.set('state', filters.state)
      if (filters.sector) params.set('sector', filters.sector)
      if (filters.minScore) params.set('min_score', filters.minScore)
      if (filters.maxScore) params.set('max_score', filters.maxScore)
      if (filters.hasCycles) params.set('has_cycles', 'true')
      const res = await api.get<WorklistResponse>(`/worklist?${params.toString()}`)
      setData(res.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail?.message || t('Could not load the worklist.'))
    } finally {
      setLoading(false)
    }
  }, [sort, direction, page, filters])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    api.get<WorklistFacets>('/worklist/facets')
      .then((res) => setFacets(res.data))
      .catch(() => setFacets(null))
  }, [])

  useEffect(() => {
    const cins = data?.items.map((item) => item.cin).filter(Boolean) as string[]
    if (!cins?.length) {
      setAssignments({})
      return
    }
    api.get<EntityAssignment[]>('/worklist/assignments', { params: { cins: cins.join(',') } })
      .then((res) => {
        const next: Record<string, EntityAssignment> = {}
        res.data.forEach((assignment) => { next[assignment.entity_cin] = assignment })
        setAssignments(next)
      })
      .catch(() => setAssignments({}))
  }, [data])

  useEffect(() => {
    setSelected(new Set())
  }, [page, filters, sort, direction])

  const items = data?.items || []
  const allSelected = items.length > 0 && items.every((item) => item.cin && selected.has(item.cin))

  const updateFilter = (patch: Partial<Filters>) => {
    setPage(1)
    setFilters((current) => ({ ...current, ...patch }))
  }

  const toggleBand = (band: string) => {
    const bands = filters.bands.includes(band)
      ? filters.bands.filter((value) => value !== band)
      : [...filters.bands, band]
    const bounds = bandBounds(bands)
    updateFilter({ bands, minScore: bounds.min, maxScore: bounds.max })
  }

  const clearFilters = () => {
    setPage(1)
    setFilters(EMPTY_FILTERS)
  }

  const toggleSort = (key: SortKey) => {
    if (sort === key) {
      setDirection((current) => (current === 'desc' ? 'asc' : 'desc'))
    } else {
      setSort(key)
      setDirection('desc')
    }
    setPage(1)
  }

  const toggleSelected = (cin?: string) => {
    if (!cin) return
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(cin)) next.delete(cin)
      else next.add(cin)
      return next
    })
  }

  const toggleAll = () => {
    setSelected((current) => {
      const next = new Set(current)
      if (allSelected) items.forEach((item) => item.cin && next.delete(item.cin))
      else items.forEach((item) => item.cin && next.add(item.cin))
      return next
    })
  }

  const handleRowKey = (event: React.KeyboardEvent<HTMLTableRowElement>, item: WorklistItem, index: number) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const nextIndex = event.key === 'ArrowDown' ? index + 1 : index - 1
      const next = items[nextIndex]
      if (next?.cin) rowRefs.current[next.cin]?.focus()
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      const target = event.key === 'Home' ? items[0] : items[items.length - 1]
      if (target?.cin) rowRefs.current[target.cin]?.focus()
    } else if (event.key === ' ') {
      event.preventDefault()
      toggleSelected(item.cin)
    } else if (event.key === 'Enter' && item.cin) {
      event.preventDefault()
      navigate(`/entity/${item.cin}/network`)
    }
  }

  const openBulk = async (kind: 'assign' | 'label' | 'case') => {
    setBulkModal(kind)
    if (kind === 'assign' && users.length === 0) {
      try {
        const res = await api.get<AssignableUser[]>('/users/assignable')
        setUsers(res.data)
        if (res.data[0]) setAssigneeId(res.data[0].id)
      } catch {
        toast.push({ title: t('Could not load analysts'), tone: 'critical' })
      }
    }
    if (kind === 'case' && cases.length === 0) {
      try {
        const res = await api.get<Case[]>('/cases')
        setCases(res.data)
        if (res.data[0]) setCaseId(res.data[0].id)
      } catch {
        toast.push({ title: t('Could not load cases'), tone: 'critical' })
      }
    }
  }

  const runBulk = async () => {
    const entity_cins = [...selected]
    if (entity_cins.length === 0) return
    const payload: Record<string, any> = { entity_cins }
    if (bulkModal === 'assign') {
      if (!assigneeId) return
      Object.assign(payload, { action: 'assign', assignee_id: assigneeId })
    } else if (bulkModal === 'label') {
      Object.assign(payload, { action: 'label', label })
    } else if (bulkModal === 'case') {
      if (!caseId) return
      Object.assign(payload, { action: 'add_to_case', case_id: caseId })
    } else {
      return
    }
    setBulkBusy(true)
    try {
      const res = await api.post('/worklist/bulk', payload)
      const actionLabel = bulkModal === 'assign' ? 'assigned' : bulkModal === 'label' ? 'labelled' : 'added to case'
      toast.push({
        title: `${res.data.affected} ${res.data.affected === 1 ? 'entity' : 'entities'} ${actionLabel}`,
        tone: 'success',
      })
      setBulkModal(null)
      setSelected(new Set())
      await load()
    } catch (err: any) {
      toast.push({
        title: t('Bulk action failed'),
        description: err?.response?.data?.detail?.message || 'Try again or reduce the selection.',
        tone: 'critical',
      })
    } finally {
      setBulkBusy(false)
    }
  }

  const saveView = () => {
    const name = viewName.trim()
    if (!name) return
    const next = [
      ...views.filter((view) => view.name.toLowerCase() !== name.toLowerCase()),
      { id: `${Date.now()}`, name, filters, sort, direction },
    ]
    persistViews(next)
    setSaveOpen(false)
    setViewName('')
    toast.push({ title: `Saved view “${name}”`, tone: 'success' })
  }

  const applyView = (view: SavedView) => {
    setFilters(view.filters)
    setSort(view.sort)
    setDirection(view.direction)
    setPage(1)
  }

  const removeView = (id: string) => persistViews(views.filter((view) => view.id !== id))

  const bandOptions = useMemo(
    () => [
      { id: 'critical', label: `Critical ${RISK_THRESHOLDS.critical}+` },
      { id: 'high', label: `High ${RISK_THRESHOLDS.high}–${RISK_THRESHOLDS.critical - 1}` },
      { id: 'medium', label: t('Medium {min}–{max}', { min: RISK_THRESHOLDS.medium, max: RISK_THRESHOLDS.high - 1 }) },
      { id: 'low', label: t('Low <{max}', { max: RISK_THRESHOLDS.medium }) },
    ],
    [],
  )

  const stateOptions = [
    { value: '', label: t('All states') },
    ...(facets?.states || []).map((state) => ({ value: state, label: state })),
  ]
  const sectorOptions = [
    { value: '', label: t('All sectors') },
    ...(facets?.sectors || []).map((sector) => ({ value: sector, label: `NIC ${sector}` })),
  ]

  const filterCount = activeFilterCount(filters)
  const pageCount = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="micro-label text-accent-ring">{t('Investigation queue')}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">{t('Risk worklist')}</h1>
          <p className="mt-1 max-w-2xl text-sm text-text-secondary">
            {t('Ranked entities with network evidence. Filter, save a view, then assign or label a batch without leaving the queue.')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <Badge tone="neutral">
              {data.total.toLocaleString('en-IN')} {data.total === 1 ? 'entity' : 'entities'}
            </Badge>
          )}
          <Button variant="secondary" onClick={() => setSaveOpen(true)}>{t('Save view')}</Button>
        </div>
      </div>

      <div className="panel space-y-3 p-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-12">
          <div className="xl:col-span-4">
            <label className="micro-label mb-1.5 block" htmlFor="worklist-search">{t('Search')}</label>
            <Input
              id="worklist-search"
              inputSize="sm"
              placeholder={t('Name, CIN or GSTIN')}
              value={filters.q}
              onChange={(event) => updateFilter({ q: event.target.value })}
              leadingIcon={
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              }
            />
          </div>
          <div className="xl:col-span-2">
            <Select label={t('State')} selectSize="sm" value={filters.state} onChange={(event) => updateFilter({ state: event.target.value })} options={stateOptions} />
          </div>
          <div className="xl:col-span-2">
            <Select label={t('Sector')} selectSize="sm" value={filters.sector} onChange={(event) => updateFilter({ sector: event.target.value })} options={sectorOptions} />
          </div>
          <div className="xl:col-span-1">
            <Input label={t('Min score')} inputSize="sm" type="number" min={0} max={100} value={filters.minScore} onChange={(event) => updateFilter({ minScore: event.target.value, bands: [] })} />
          </div>
          <div className="xl:col-span-1">
            <Input label={t('Max score')} inputSize="sm" type="number" min={0} max={100} value={filters.maxScore} onChange={(event) => updateFilter({ maxScore: event.target.value, bands: [] })} />
          </div>
          <div className="flex items-end xl:col-span-2">
            <label className="flex h-8 cursor-pointer items-center gap-2 rounded-lg border border-border px-2.5 text-xs text-text-secondary">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 accent-[var(--color-accent)]"
                checked={filters.hasCycles}
                onChange={(event) => updateFilter({ hasCycles: event.target.checked })}
              />
              {t('In a ring')}
            </label>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
          <FilterChips
            ariaLabel="Risk bands"
            options={bandOptions}
            selected={filters.bands}
            onToggle={toggleBand}
            onClear={() => updateFilter({ bands: [], minScore: '', maxScore: '' })}
          />
          <div className="flex items-center gap-2">
            {filterCount > 0 && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>{t('Clear')} {filterCount} {t('filter')}{filterCount === 1 ? '' : 's'}</Button>
            )}
            <InfoHint
              content={t('Risk bands are presets over the same score range. Combining bands widens the min/max range; editing the score inputs clears band selection.')}
            />
          </div>
        </div>

        {views.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
            <span className="micro-label">{t('Saved views')}</span>
            {views.map((view) => (
              <span key={view.id} className="inline-flex items-center overflow-hidden rounded-full border border-border">
                <button
                  type="button"
                  onClick={() => applyView(view)}
                  className="px-2.5 py-1 text-xs text-text-secondary transition-colors hover:bg-raised hover:text-text-primary"
                >
                  {view.name}
                </button>
                <button
                  type="button"
                  onClick={() => removeView(view.id)}
                  aria-label={`Delete saved view ${view.name}`}
                  className="border-l border-border px-1.5 py-1 text-text-disabled hover:bg-raised hover:text-risk-critical"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {error ? (
        <div className="panel p-8 text-center" role="alert">
          <p className="text-sm font-medium text-risk-critical">{error}</p>
          <p className="mt-1 text-xs text-text-secondary">{t('Check that the graph is available, then retry.')}</p>
          <Button variant="secondary" className="mt-4" onClick={load}>{t('Retry')}</Button>
        </div>
      ) : loading && !data ? (
        <div className="panel overflow-hidden">
          <div className="border-b border-border bg-raised/60 px-4 py-3"><Skeleton className="h-3 w-40" /></div>
          {Array.from({ length: 9 }).map((_, index) => (
            <div key={index} className="flex items-center gap-4 border-b border-border px-4 py-3 last:border-0">
              <Skeleton className="h-4 w-4" />
              <Skeleton className="h-5 w-16" />
              <Skeleton className="h-4 flex-1" />
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-4 w-20" />
            </div>
          ))}
        </div>
      ) : (
        <div className="panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm" aria-label={t('Risk worklist')}>
              <thead className="sticky top-0 z-10 bg-raised/95 backdrop-blur">
                <tr className="text-left text-micro uppercase tracking-micro text-text-secondary">
                  <th className="w-10 px-3 py-2.5">
                    <input
                      type="checkbox"
                      aria-label={t('Select all rows on this page')}
                      className="h-3.5 w-3.5 accent-[var(--color-accent)]"
                      checked={allSelected}
                      onChange={toggleAll}
                    />
                  </th>
                  <th className="px-3 py-2.5">
                    <button type="button" className="hover:text-text-primary" onClick={() => toggleSort('risk_score')}>
                      {t('Risk')} {sort === 'risk_score' ? (direction === 'desc' ? '↓' : '↑') : ''}
                    </button>
                  </th>
                  <th className="px-3 py-2.5">
                    <button type="button" className="hover:text-text-primary" onClick={() => toggleSort('name')}>
                      {t('Entity')} {sort === 'name' ? (direction === 'desc' ? '↓' : '↑') : ''}
                    </button>
                  </th>
                  <th className="px-3 py-2.5">{t('GSTIN / CIN')}</th>
                  <th className="px-3 py-2.5">{t('State')}</th>
                  <th className="px-3 py-2.5">{t('Sector')}</th>
                  <th className="px-3 py-2.5">
                    <span className="inline-flex items-center gap-1">
                      {t('Loops')}
                      <InfoHint content={t('Number of detected fraud rings this entity belongs to. A ring is a closed chain of invoices.')} />
                    </span>
                  </th>
                  <th className="px-3 py-2.5">{t('Owner')}</th>
                  <th className="px-3 py-2.5 text-right">
                    <button type="button" className="hover:text-text-primary" onClick={() => toggleSort('paid_up_capital')}>
                      {t('Paid-up capital')} {sort === 'paid_up_capital' ? (direction === 'desc' ? '↓' : '↑') : ''}
                    </button>
                  </th>
                  <th className="px-3 py-2.5 text-right">{t('Updated')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, index) => {
                  const cin = item.cin || ''
                  const isSelected = selected.has(cin)
                  const assignment = assignments[cin]
                  const band = riskBand(item.risk_score)
                  return (
                    <tr
                      key={cin || index}
                      ref={(element) => { rowRefs.current[cin] = element }}
                      tabIndex={0}
                      aria-selected={isSelected}
                      onClick={() => cin && navigate(`/entity/${cin}/network`)}
                      onKeyDown={(event) => handleRowKey(event, item, index)}
                      className={`cursor-pointer border-t border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-ring ${
                        isSelected ? 'bg-accent/10' : 'hover:bg-raised/40'
                      }`}
                    >
                      <td className="px-3 py-2.5" onClick={(event) => event.stopPropagation()}>
                        <input
                          type="checkbox"
                          aria-label={`Select ${item.name || cin}`}
                          className="h-3.5 w-3.5 accent-[var(--color-accent)]"
                          checked={isSelected}
                          onChange={() => toggleSelected(item.cin)}
                        />
                      </td>
                      <td className="px-3 py-2.5"><RiskBadge score={item.risk_score} /></td>
                      <td className="max-w-[18rem] px-3 py-2.5">
                        <Link
                          to={`/entity/${cin}/network`}
                          onClick={(event) => event.stopPropagation()}
                          className="block truncate font-medium hover:text-accent-ring"
                        >
                          {item.name || 'Unnamed entity'}
                        </Link>
                        <span className="text-data text-text-disabled">
                          {[item.status, band ? titleCase(band) : null].filter(Boolean).join(' · ') || '—'}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="mono-id block text-[12px]">{item.gstin || '—'}</span>
                        <span className="text-data text-text-disabled">{item.cin || '—'}</span>
                      </td>
                      <td className="px-3 py-2.5 text-text-secondary">{item.state || '—'}</td>
                      <td className="px-3 py-2.5">
                        <span className="mono-id text-[12px] text-text-secondary">{item.nic_code || '—'}</span>
                      </td>
                      <td className="px-3 py-2.5">
                        {item.cycle_count ? (
                          <Badge tone="critical">{item.cycle_count}</Badge>
                        ) : (
                          <span className="text-text-disabled">0</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5">
                        {assignment?.assignee_name ? (
                          <span className="inline-flex items-center gap-1.5">
                            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-raised text-[10px] font-semibold text-text-secondary">
                              {initials(assignment.assignee_name)}
                            </span>
                            <span className="max-w-[8rem] truncate text-xs">{assignment.assignee_name}</span>
                          </span>
                        ) : (
                          <span className="text-xs text-text-disabled">{t('Unassigned')}</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-data">{formatInr(item.paid_up_capital)}</td>
                      <td className="px-3 py-2.5 text-right text-xs text-text-secondary">
                        {item.incorporation_date ? formatDate(item.incorporation_date) : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {!loading && items.length === 0 && (
            filterCount > 0 ? (
              <EmptyState
                title={t('No entities match these filters')}
                description={t('Try removing a risk band, widening the score range, or clearing the ring filter.')}
                action={<Button variant="secondary" onClick={clearFilters}>{t('Clear all filters')}</Button>}
              />
            ) : (
              <EmptyState
                title={t('No scored entities yet')}
                description={t('Import MCA and GST data, then run a risk job to populate the queue.')}
                action={<Link to="/ingest"><Button>{t('Import data')}</Button></Link>}
              />
            )
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
            <span className="text-xs text-text-disabled">
              <kbd className="rounded border border-border px-1">↑</kbd>{' '}
              <kbd className="rounded border border-border px-1">↓</kbd> {t('move ·')}{' '}
              <kbd className="rounded border border-border px-1">{t('Space')}</kbd> {t('select ·')}{' '}
              <kbd className="rounded border border-border px-1">{t('Enter')}</kbd> {t('open')}
              {loading && <span className="ml-2 text-accent-ring">{t('Refreshing…')}</span>}
            </span>
            {data && data.total > 0 && (
              <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
            )}
          </div>
        </div>
      )}

      {selected.size > 0 && (
        <div className="sticky bottom-4 z-20 mx-auto flex w-full max-w-4xl flex-wrap items-center justify-between gap-3 rounded-xl border border-accent/40 bg-surface/95 px-4 py-3 shadow-lg backdrop-blur">
          <div className="flex items-center gap-3">
            <Badge tone="accent">{selected.size} {t('selected')}</Badge>
            <button
              type="button"
              onClick={() => setSelected(new Set())}
              className="text-xs text-text-secondary hover:text-text-primary"
            >
              {t('Clear')}
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => openBulk('assign')}>{t('Assign')}</Button>
            <Button size="sm" variant="secondary" onClick={() => openBulk('label')}>{t('Label')}</Button>
            <Button size="sm" onClick={() => openBulk('case')}>{t('Add to case')}</Button>
          </div>
        </div>
      )}

      <Modal
        open={bulkModal !== null}
        onClose={() => setBulkModal(null)}
        title={
          bulkModal === 'assign' ? `Assign ${selected.size} entities` :
          bulkModal === 'label' ? `Label ${selected.size} entities` :
          `Add ${selected.size} entities to a case`
        }
        description={t('Changes apply to every selected entity and are recorded in the audit trail.')}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setBulkModal(null)}>{t('Cancel')}</Button>
            <Button onClick={runBulk} loading={bulkBusy}>{t('Confirm')}</Button>
          </div>
        }
      >
        {bulkModal === 'assign' && (
          <Select
            label={t('Assign to')}
            value={assigneeId}
            onChange={(event) => setAssigneeId(event.target.value)}
            options={users.map((user) => ({
              value: user.id,
              label: `${user.display_name || user.email} · ${titleCase(user.role)}`,
            }))}
          />
        )}
        {bulkModal === 'label' && (
          <div className="space-y-2">
            <Select
              label={t('Analyst label')}
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              options={[
                { value: 'needs_review', label: t('Needs review') },
                { value: 'confirm_fraud', label: t('Confirm fraud') },
                { value: 'false_positive', label: t('False positive') },
              ]}
            />
            <p className="text-xs text-text-secondary">
              {t('Labels feed the model feedback loop. They do not close entities or cases automatically.')}
            </p>
          </div>
        )}
        {bulkModal === 'case' && (
          <Select
            label={t('Case')}
            value={caseId}
            onChange={(event) => setCaseId(event.target.value)}
            options={cases.map((item) => ({ value: item.id, label: item.title }))}
          />
        )}
      </Modal>

      <Modal
        open={saveOpen}
        onClose={() => setSaveOpen(false)}
        title={t('Save current view')}
        description={t('Filters and sorting are stored in this browser for this workstation.')}
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setSaveOpen(false)}>{t('Cancel')}</Button>
            <Button onClick={saveView} disabled={!viewName.trim()}>{t('Save view')}</Button>
          </div>
        }
      >
        <Input
          label={t('View name')}
          placeholder={t('e.g. Maharashtra critical rings')}
          value={viewName}
          onChange={(event) => setViewName(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter') saveView() }}
          autoFocus
        />
      </Modal>

      <p className="text-xs text-text-disabled">
        {t('Showing page')} {page} {t('of')} {pageCount}{t('. Saved views are local to this browser; server-synced views are on the roadmap.')}
      </p>
    </div>
  )
}
