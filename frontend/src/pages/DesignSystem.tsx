import { ReactNode, useState } from 'react'
import RiskBadge from '../components/RiskBadge'
import StatTile from '../components/StatTile'
import Badge, { BadgeTone } from '../components/ui/Badge'
import Breadcrumbs from '../components/ui/Breadcrumbs'
import Button from '../components/ui/Button'
import Drawer from '../components/ui/Drawer'
import EmptyState from '../components/ui/EmptyState'
import FilterChips from '../components/ui/FilterChips'
import Input from '../components/ui/Input'
import Modal from '../components/ui/Modal'
import Pagination from '../components/ui/Pagination'
import Select from '../components/ui/Select'
import Skeleton, { SkeletonTable, SkeletonText } from '../components/ui/Skeleton'
import Table, { TableColumn } from '../components/ui/Table'
import Tabs, { TabPanel } from '../components/ui/Tabs'
import { useToast } from '../components/ui/Toast'
import Tooltip from '../components/ui/Tooltip'
import { cn } from '../utils/cn'

const COLOR_TOKENS = [
  { token: '--color-canvas', label: 'Canvas', usage: 'App background' },
  { token: '--color-surface', label: 'Surface', usage: 'Panels, cards, sidebar' },
  { token: '--color-raised', label: 'Raised', usage: 'Hover, dropdowns' },
  { token: '--color-border', label: 'Border', usage: 'Dividers, outlines' },
  { token: '--color-text-primary', label: 'Text primary', usage: 'Body copy' },
  { token: '--color-text-secondary', label: 'Text secondary', usage: 'Labels, hints' },
  { token: '--color-text-disabled', label: 'Text disabled', usage: 'Placeholders' },
  { token: '--color-accent', label: 'Accent', usage: 'Primary actions' },
  { token: '--color-accent-ring', label: 'Accent ring', usage: 'Focus, selection' },
  { token: '--color-amber', label: 'Amber', usage: 'Warnings, attention' },
  { token: '--risk-critical', label: 'Risk critical', usage: 'Critical score' },
  { token: '--risk-high', label: 'Risk high', usage: 'High score' },
  { token: '--risk-medium', label: 'Risk medium', usage: 'Medium score' },
  { token: '--risk-low', label: 'Risk low', usage: 'Low score' },
  { token: '--risk-neutral', label: 'Risk neutral', usage: 'Insufficient data' },
]

const TYPE_SCALE = [
  { name: 'text-2xl', size: '30px', usage: 'Page hero / empty-state headline' },
  { name: 'text-xl', size: '24px', usage: 'Section headline' },
  { name: 'text-lg', size: '20px', usage: 'Panel headline' },
  { name: 'text-md', size: '16px', usage: 'Modal title' },
  { name: 'text-base', size: '14px', usage: 'Body copy' },
  { name: 'text-sm', size: '13px', usage: 'Controls, table cells' },
  { name: 'text-xs', size: '11px', usage: 'Labels, captions' },
  { name: 'text-micro', size: '11px', usage: 'Uppercase micro labels' },
]

const SPACING = [4, 8, 12, 16, 20, 24, 32, 40, 48, 64]
const RADII = [
  { name: '--radius-sm', value: '6px' },
  { name: '--radius-md', value: '8px' },
  { name: '--radius-lg', value: '12px' },
  { name: '--radius-full', value: '9999px' },
]
const MOTION = [
  { name: '--motion-fast', value: '120ms', usage: 'Hover, focus' },
  { name: '--motion-base', value: '200ms', usage: 'Panels, dropdowns' },
  { name: '--motion-slow', value: '320ms', usage: 'Page transitions' },
  { name: '--ease-standard', value: 'cubic-bezier(0.2, 0, 0, 1)', usage: 'Default easing' },
]

interface SampleEntity {
  id: string
  name: string
  identifier: string
  state: string
  risk?: number
  exposure: number
}

const SAMPLE_ROWS: SampleEntity[] = [
  { id: 'e1', name: 'Meridian Traders Pvt Ltd', identifier: '27AABCM1234A1Z5', state: 'Maharashtra', risk: 92, exposure: 18400000 },
  { id: 'e2', name: 'Kaveri Logistics LLP', identifier: '29AAGCK8812B1Z2', state: 'Karnataka', risk: 74, exposure: 6200000 },
  { id: 'e3', name: 'Northline Exports', identifier: '07AAECN4455C1Z8', state: 'Delhi', risk: 48, exposure: 2100000 },
  { id: 'e4', name: 'Sundara Textiles', identifier: '33AAJCS9921D1Z1', state: 'Tamil Nadu', risk: 19, exposure: 940000 },
  { id: 'e5', name: 'Unrated Holdings', identifier: '19AAKCU1023E1Z6', state: 'West Bengal', exposure: 0 },
]

function Section({
  id,
  title,
  description,
  children,
}: {
  id: string
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section id={id} className="scroll-mt-20">
      <div className="mb-4 border-b border-border pb-3">
        <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
        {description && <p className="mt-1 max-w-3xl text-xs leading-relaxed text-text-secondary">{description}</p>}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  )
}

function Example({
  title,
  description,
  code,
  children,
  className,
}: {
  title: string
  description?: string
  code?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className="panel overflow-hidden">
      <div className="border-b border-border px-4 py-2.5">
        <h3 className="text-xs font-semibold text-text-primary">{title}</h3>
        {description && <p className="mt-0.5 text-[11px] text-text-secondary">{description}</p>}
      </div>
      <div className={cn('p-4', className ?? 'flex flex-wrap items-center gap-3')}>{children}</div>
      {code && (
        <pre className="overflow-x-auto border-t border-border bg-canvas px-4 py-2.5 text-[11px] leading-relaxed text-text-secondary">
          <code>{code}</code>
        </pre>
      )}
    </div>
  )
}

const tableColumns: TableColumn<SampleEntity>[] = [
  {
    key: 'name',
    header: 'Entity',
    sortable: true,
    render: (row) => <span className="font-medium">{row.name}</span>,
  },
  {
    key: 'identifier',
    header: 'Identifier',
    sortable: true,
    render: (row) => <span className="mono-id">{row.identifier}</span>,
  },
  {
    key: 'state',
    header: 'State',
    sortable: true,
    render: (row) => <Badge tone="outline">{row.state}</Badge>,
  },
  {
    key: 'risk',
    header: 'Risk',
    sortable: true,
    align: 'right',
    sortValue: (row) => row.risk ?? -1,
    render: (row) => <RiskBadge score={row.risk} />,
  },
  {
    key: 'exposure',
    header: 'Exposure (₹)',
    sortable: true,
    align: 'right',
    render: (row) => row.exposure.toLocaleString('en-IN'),
  },
]

const BADGE_TONES: BadgeTone[] = ['neutral', 'accent', 'amber', 'critical', 'high', 'medium', 'low', 'outline']

export default function DesignSystem() {
  const [tab, setTab] = useState('overview')
  const [modalOpen, setModalOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [page, setPage] = useState(2)
  const [filters, setFilters] = useState<string[]>(['critical'])
  const toast = useToast()

  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-bold text-text-primary">Design System</h1>
          <Badge tone="accent">v1</Badge>
        </div>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-text-secondary">
          The living catalogue of Dhan-Chakra&apos;s interface foundations and components. Every component below is
          rendered by the same React code the product uses, so this page doubles as visual regression coverage in both
          light and dark themes. Toggle the theme in the top bar to check contrast.
        </p>
        <nav className="mt-4 flex flex-wrap gap-2 text-xs">
          {[
            ['foundations', 'Foundations'],
            ['buttons', 'Buttons'],
            ['inputs', 'Inputs'],
            ['navigation', 'Navigation'],
            ['data-display', 'Data display'],
            ['feedback', 'Feedback'],
            ['overlays', 'Overlays'],
          ].map(([id, label]) => (
            <a
              key={id}
              href={`#${id}`}
              className="rounded-full border border-border px-3 py-1 text-text-secondary hover:bg-raised hover:text-text-primary"
            >
              {label}
            </a>
          ))}
        </nav>
      </header>

      <Section
        id="foundations"
        title="Foundations"
        description="Tokens are defined once as CSS custom properties in src/index.css and exposed to Tailwind. Components must consume tokens, never raw hex values, so both themes stay in sync."
      >
        <Example
          title="Colour"
          description="Semantic tokens. Risk tokens are colours, not component props — RiskBadge maps a score to them."
          className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
        >
          {COLOR_TOKENS.map((item) => (
            <div key={item.token} className="min-w-0">
              <div
                className="h-12 w-full rounded-md border border-border"
                style={{ backgroundColor: `var(${item.token})` }}
              />
              <div className="mt-1.5 truncate text-[11px] font-medium text-text-primary">{item.label}</div>
              <div className="truncate font-mono text-[10px] text-text-secondary">{item.token}</div>
              <div className="truncate text-[10px] text-text-disabled">{item.usage}</div>
            </div>
          ))}
        </Example>

        <Example title="Typography" description="Inter for UI, IBM Plex Mono for identifiers and figures." className="block">
          <div className="space-y-3">
            {TYPE_SCALE.map((item) => (
              <div key={item.name} className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <span className="w-20 shrink-0 font-mono text-[10px] text-text-secondary">{item.size}</span>
                <span style={{ fontSize: item.size }} className="font-semibold text-text-primary">
                  Graph intelligence
                </span>
                <span className="text-[10px] text-text-disabled">
                  {item.name} · {item.usage}
                </span>
              </div>
            ))}
            <div className="mt-4 border-t border-border pt-3">
              <div className="font-mono text-data text-text-primary">27AABCM1234A1Z5 · ₹1,84,00,000</div>
              <div className="mt-1 text-[11px] text-text-secondary">IBM Plex Mono for GSTINs, CINs and money.</div>
            </div>
          </div>
        </Example>

        <Example title="Spacing" description="4px base grid." className="block">
          <div className="space-y-2">
            {SPACING.map((value) => (
              <div key={value} className="flex items-center gap-3">
                <span className="w-12 shrink-0 font-mono text-[10px] text-text-secondary">{value}px</span>
                <span className="h-2 rounded-sm bg-accent/60" style={{ width: value }} />
                <span className="font-mono text-[10px] text-text-disabled">--space-{value / 4}</span>
              </div>
            ))}
          </div>
        </Example>

        <div className="grid gap-4 md:grid-cols-2">
          <Example title="Radius" className="grid grid-cols-2 gap-4">
            {RADII.map((item) => (
              <div key={item.name}>
                <div
                  className="h-14 w-full border border-border bg-raised"
                  style={{ borderRadius: `var(${item.name})` }}
                />
                <div className="mt-1 font-mono text-[10px] text-text-secondary">{item.name}</div>
                <div className="text-[10px] text-text-disabled">{item.value}</div>
              </div>
            ))}
          </Example>
          <Example title="Elevation" className="grid grid-cols-1 gap-4">
            {[1, 2, 3].map((level) => (
              <div
                key={level}
                className="rounded-lg border border-border bg-surface px-3 py-2 text-[11px] text-text-secondary"
                style={{ boxShadow: `var(--elevation-${level})` }}
              >
                elevation-{level}
              </div>
            ))}
          </Example>
        </div>

        <Example title="Motion" description="All transitions respect prefers-reduced-motion." className="block">
          <div className="grid gap-2 sm:grid-cols-2">
            {MOTION.map((item) => (
              <div key={item.name} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                <span className="font-mono text-[11px] text-text-primary">{item.name}</span>
                <span className="text-[10px] text-text-secondary">
                  {item.value} · {item.usage}
                </span>
              </div>
            ))}
          </div>
        </Example>
      </Section>

      <Section id="buttons" title="Buttons" description="One primary action per view. Use secondary for adjacent actions and ghost for low-emphasis controls.">
        <Example
          title="Variants"
          code={'<Button variant="primary">Run analysis</Button>\n<Button variant="secondary">Export</Button>\n<Button variant="ghost">Cancel</Button>\n<Button variant="critical">Escalate</Button>'}
        >
          <Button>Run analysis</Button>
          <Button variant="secondary">Export</Button>
          <Button variant="ghost">Cancel</Button>
          <Button variant="critical">Escalate</Button>
        </Example>
        <Example title="Sizes and states" code={'<Button size="sm">Small</Button>\n<Button loading>Saving…</Button>\n<Button disabled>Disabled</Button>'}>
          <Button size="sm">Small</Button>
          <Button size="md">Medium</Button>
          <Button size="lg">Large</Button>
          <Button loading>Running</Button>
          <Button disabled>Disabled</Button>
          <Button
            variant="secondary"
            leadingIcon={
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 4v16m8-8H4" />
              </svg>
            }
          >
            With icon
          </Button>
        </Example>
      </Section>

      <Section id="inputs" title="Inputs" description="Labels sit above controls; errors replace hints and set aria-invalid. Every control is keyboard reachable with a visible focus ring.">
        <div className="grid gap-4 md:grid-cols-2">
          <Example title="Text input" className="block" code={'<Input label="GSTIN" placeholder="27AABCM1234A1Z5" hint="15 characters" />'}>
            <div className="space-y-3">
              <Input label="GSTIN" placeholder="27AABCM1234A1Z5" hint="15 characters, no spaces" />
              <Input label="Search" placeholder="Company name…" leadingIcon={<span className="text-xs">⌕</span>} />
              <Input label="Invalid" defaultValue="27AABCM1234" error="GSTIN must be 15 characters." />
              <Input label="Disabled" placeholder="Read-only" disabled />
              <Input label="Small" placeholder="Compact" inputSize="sm" />
            </div>
          </Example>
          <Example title="Select" className="block" code={'<Select label="Risk band" options={[…]} />'}>
            <div className="space-y-3">
              <Select
                label="Risk band"
                defaultValue="all"
                options={[
                  { value: 'all', label: 'All risk bands' },
                  { value: 'critical', label: 'Critical (80+)' },
                  { value: 'high', label: 'High (60–79)' },
                  { value: 'medium', label: 'Medium (40–59)' },
                ]}
              />
              <Select
                label="Error state"
                defaultValue=""
                error="Choose an ingestion source."
                options={[
                  { value: '', label: 'Select source…', disabled: true },
                  { value: 'gstn', label: 'GSTN' },
                  { value: 'mca', label: 'MCA' },
                ]}
              />
            </div>
          </Example>
        </div>
      </Section>

      <Section id="navigation" title="Navigation" description="Breadcrumbs and tabs orient the analyst inside a case without adding another sidebar level.">
        <Example title="Breadcrumbs" className="block" code={'<Breadcrumbs items={[{label: "Cases", href: "/cases"}, {label: "CASE-1042"}]} />'}>
          <Breadcrumbs
            items={[
              { label: 'Dashboard', href: '/' },
              { label: 'Cases', href: '/cases' },
              { label: 'CASE-1042' },
            ]}
          />
        </Example>
        <Example title="Tabs" className="block" code={'<Tabs items={[…]} value={tab} onChange={setTab} />'}>
          <Tabs
            items={[
              { id: 'overview', label: 'Overview' },
              { id: 'evidence', label: 'Evidence', count: 12 },
              { id: 'timeline', label: 'Timeline' },
              { id: 'notes', label: 'Notes', disabled: true },
            ]}
            value={tab}
            onChange={setTab}
          />
          <TabPanel id="overview" value={tab}>
            <p className="text-xs text-text-secondary">Summary of the selected entity, risk contributors and open actions.</p>
          </TabPanel>
          <TabPanel id="evidence" value={tab}>
            <p className="text-xs text-text-secondary">Twelve evidence items, grouped by signal source.</p>
          </TabPanel>
          <TabPanel id="timeline" value={tab}>
            <p className="text-xs text-text-secondary">Chronological view of invoices, filings and case events.</p>
          </TabPanel>
        </Example>
        <Example title="Filter chips" className="block" code={'<FilterChips options={[…]} selected={filters} onToggle={toggle} onClear={clear} />'}>
          <FilterChips
            options={[
              { id: 'critical', label: 'Critical', count: 8 },
              { id: 'high', label: 'High', count: 21 },
              { id: 'medium', label: 'Medium', count: 34 },
              { id: 'low', label: 'Low', count: 57 },
              { id: 'unrated', label: 'Insufficient data', count: 4 },
            ]}
            selected={filters}
            onToggle={(id) =>
              setFilters((current) =>
                current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
              )
            }
            onClear={() => setFilters([])}
          />
        </Example>
        <Example title="Pagination" className="block" code={'<Pagination page={page} pageSize={10} total={243} onChange={setPage} />'}>
          <Pagination page={page} pageSize={10} total={243} onChange={setPage} />
        </Example>
      </Section>

      <Section id="data-display" title="Data display" description="Tables are sortable with a sticky header and column visibility; badges encode categorical state, never risk scores (use RiskBadge for that).">
        <Example title="Badges" className="block">
          <div className="flex flex-wrap gap-2">
            {BADGE_TONES.map((tone) => (
              <Badge key={tone} tone={tone} dot={tone !== 'outline'}>
                {tone}
              </Badge>
            ))}
          </div>
        </Example>
        <Example title="Risk badge" description="Driven by RISK_THRESHOLDS; always shows the band label alongside the optional score." className="block">
          <div className="flex flex-wrap items-center gap-2">
            <RiskBadge score={92} />
            <RiskBadge score={74} />
            <RiskBadge score={48} />
            <RiskBadge score={19} />
            <RiskBadge score={undefined} />
            <RiskBadge score={74} showScore={false} />
          </div>
        </Example>
        <Example title="Stat tiles" className="grid w-full gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Entities" value="12,480" sub="Across 6 states" />
          <StatTile label="Critical" value="38" sub="+6 in 7 days" accent="red" />
          <StatTile label="Open cases" value="21" sub="4 awaiting review" accent="amber" />
          <StatTile label="Resolved" value="146" sub="Last 30 days" accent="green" />
        </Example>
        <Example title="Table" className="block">
          <Table
            columns={tableColumns}
            rows={SAMPLE_ROWS}
            rowKey={(row) => row.id}
            initialSort={{ key: 'risk', direction: 'desc' }}
            caption="Sample entities with sortable columns"
          />
        </Example>
      </Section>

      <Section id="feedback" title="Feedback" description="Empty states explain what is missing and offer the next action. Skeletons mirror the final layout so the page does not jump.">
        <div className="grid gap-4 md:grid-cols-2">
          <Example title="Empty state" className="block">
            <EmptyState
              title="No cases in this view"
              description="Adjust the filters or open a new case from the worklist."
              action={<Button size="sm">Open worklist</Button>}
            />
          </Example>
          <Example title="Empty state (compact)" className="block">
            <EmptyState compact title="No evidence yet" description="Evidence appears after the next graph run." />
          </Example>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Example title="Skeleton" className="block">
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <Skeleton circle className="h-9 w-9" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-3 w-1/2" />
                  <Skeleton className="h-3 w-1/3" />
                </div>
              </div>
              <SkeletonText lines={3} />
            </div>
          </Example>
          <Example title="Skeleton table" className="block">
            <SkeletonTable rows={3} columns={3} />
          </Example>
        </div>
        <Example title="Toast" className="block" code={'const toast = useToast()\ntoast.push({ title: "Case assigned", tone: "success" })'}>
          <Button
            variant="secondary"
            onClick={() => toast.push({ title: 'Case assigned', description: 'CASE-1042 moved to Priya.', tone: 'success' })}
          >
            Success toast
          </Button>
          <Button
            variant="secondary"
            onClick={() => toast.push({ title: 'Ingestion warning', description: '14 rows skipped: unresolved GSTIN.', tone: 'warning' })}
          >
            Warning toast
          </Button>
          <Button
            variant="secondary"
            onClick={() => toast.push({ title: 'Export failed', description: 'Retry from the case page.', tone: 'critical' })}
          >
            Error toast
          </Button>
          <Button
            variant="secondary"
            onClick={() => toast.push({ title: 'Graph run queued', description: 'You will be notified when it completes.', tone: 'info' })}
          >
            Info toast
          </Button>
        </Example>
        <Example title="Tooltip" className="block" code={'<Tooltip content="Scores refresh hourly"><Button variant="ghost">Why?</Button></Tooltip>'}>
          <Tooltip content="Scores refresh hourly from the graph run.">
            <Button variant="ghost">Hover for tooltip</Button>
          </Tooltip>
          <Tooltip content="Bottom placement" side="bottom">
            <Badge tone="accent">Bottom</Badge>
          </Tooltip>
        </Example>
      </Section>

      <Section id="overlays" title="Overlays" description="Modals confirm, drawers investigate. Both trap focus, close on Escape and restore focus to the trigger.">
        <Example title="Modal" className="block" code={'<Modal open={open} onClose={close} title="Assign case" footer={…}>…</Modal>'}>
          <Button onClick={() => setModalOpen(true)}>Open modal</Button>
          <Modal
            open={modalOpen}
            onClose={() => setModalOpen(false)}
            title="Assign case"
            description="The assignee receives a notification and the case moves to their worklist."
            footer={
              <>
                <Button variant="secondary" onClick={() => setModalOpen(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={() => {
                    setModalOpen(false)
                    toast.push({ title: 'Case assigned', tone: 'success' })
                  }}
                >
                  Assign
                </Button>
              </>
            }
          >
            <div className="space-y-3">
              <Select
                label="Assignee"
                defaultValue="priya"
                options={[
                  { value: 'priya', label: 'Priya Nair · Analyst' },
                  { value: 'arun', label: 'Arun Mehta · Analyst' },
                  { value: 'meera', label: 'Meera Rao · Reviewer' },
                ]}
              />
              <Input label="Note" placeholder="Optional context for the assignee" />
            </div>
          </Modal>
        </Example>
        <Example title="Drawer" className="block" code={'<Drawer open={open} onClose={close} title="Evidence" side="right">…</Drawer>'}>
          <Button variant="secondary" onClick={() => setDrawerOpen(true)}>
            Open drawer
          </Button>
          <Drawer
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            title="Evidence"
            description="Circular trade loop · 5 entities"
            footer={
              <Button variant="secondary" onClick={() => setDrawerOpen(false)}>
                Close
              </Button>
            }
          >
            <div className="space-y-3 text-xs leading-relaxed text-text-secondary">
              <p>
                Invoices with amount <span className="font-mono text-text-primary">₹2,00,000</span> pass between five
                entities within a 9-day window, returning to the originator with no underlying movement.
              </p>
              <div className="panel p-3">
                <div className="micro-label">Signals</div>
                <ul className="mt-2 space-y-1.5">
                  <li>• Circular path length 5</li>
                  <li>• Repeated invoice amounts (3)</li>
                  <li>• Shared addresses (2)</li>
                </ul>
              </div>
            </div>
          </Drawer>
        </Example>
      </Section>

      <footer className="border-t border-border pt-4 text-[11px] text-text-secondary">
        Tokens live in <code className="font-mono text-text-primary">src/index.css</code>; components live in{' '}
        <code className="font-mono text-text-primary">src/components/ui</code>. This catalogue is itself the reference
        for every state — if it is not on this page, it is not part of the system.
      </footer>
    </div>
  )
}
