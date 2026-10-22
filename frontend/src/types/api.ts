export interface SearchResult {
  id: string
  type: string
  name: string
  identifier: string
  risk_score?: number
  status?: string
  state?: string
}

export interface EntitySearchResponse {
  results: SearchResult[]
  total: number
}

export interface NetworkNode {
  id: string
  label: string
  type: string
  properties: Record<string, any>
}

export interface NetworkEdge {
  source: string
  target: string
  type: string
  properties: Record<string, any>
  /** True when this edge carries an invoice whose high value has no matching
   *  e-Way Bill movement record (TASK B1). */
  eway_mismatch?: boolean
}

export interface NetworkResponse {
  nodes: NetworkNode[]
  edges: NetworkEdge[]
}

export interface LoopResult {
  path: string[]
  length: number
  total_amount?: number
  companies: Record<string, any>[]
}

export interface LoopsResponse {
  loops: LoopResult[]
  total: number
}

export interface RiskJobResponse {
  job_id: string
  status: string
  summary?: Record<string, any>
}

export interface RiskResult {
  job_id: string
  status: string
  scores?: Record<string, any>
}

export interface ExplainCycleCompany {
  cin: string
  name: string
  gstin?: string
}

export interface ExplainInvoice {
  invoice_no?: string
  seller_cin?: string
  seller_name?: string
  buyer_cin?: string
  buyer_name?: string
  amount?: number
  invoice_date?: string | null
}

export interface ExplainEWayMismatch {
  invoice_no?: string
  amount?: number
  date?: string | null
  /** Why the invoice failed to match a movement record:
   *  'no_ref' | 'no_movement_record' | 'amount_mismatch' */
  reason?: string
  reason_label?: string
  /** The e-Way Bill reference the invoice cited. */
  claimed_ref?: string | null
  /** The movement record that backs it — null when none exists. */
  movement_ref?: string | null
  movement_amount?: number | null
  movement_date?: string | null
  from_state?: string | null
  to_state?: string | null
  vehicle_no?: string | null
  distance_km?: number | null
}

export interface ExplainCycle {
  cycle_id?: string
  hop_count: number
  company_count: number
  total_invoice_amount: number
  date_span?: {
    first: string
    last: string
    span_days?: number | null
    invoice_dates?: number
  } | null
  companies: ExplainCycleCompany[]
  invoices: ExplainInvoice[]
}

export interface ExplainCommunity {
  community_id?: string
  member_count?: number
  member_cins?: string[]
}

export interface ExplainSharedDirector {
  director: string
  din?: string
  companies: string[]
  cins?: string[]
}

export interface ExplainSharedAddress {
  address: string
  state?: string
  companies: string[]
}

export interface ExplainResponse {
  entity: Record<string, any>
  reasons: string[]
  evidence: {
    /** Attribution method actually used. Structural evidence (subgraph
     *  attribution from detected cycle/community/shared links), NOT learned
     *  GNNExplainer. */
    method?: string
    cycles: ExplainCycle[]
    communities?: ExplainCommunity[]
    shared_directors: ExplainSharedDirector[]
    shared_addresses: ExplainSharedAddress[]
    shared_bank_accounts?: Record<string, any>[]
    eway_mismatches?: ExplainEWayMismatch[]
    bursts?: any[]
    risk?: number
    risk_decomposition?: Record<string, any> | null
  }
}

export interface WorklistItem {
  cin?: string
  gstin?: string
  name?: string
  risk_score?: number
  status?: string
  nic_code?: string
  state?: string
  paid_up_capital?: number
  incorporation_date?: string
  pagerank?: number
  community_id?: string
  cycle_count?: number
}

export interface WorklistResponse {
  items: WorklistItem[]
  total: number
  page: number
  page_size: number
}

export interface StatsOverview {
  companies: number
  directors: number
  flagged_entities: number
  cycles_detected: number
  estimated_itc_at_risk: number
  top_risk_state?: string
  open_cases: number
  risk_distribution?: {
    critical: number
    high: number
    medium: number
    low: number
    unscored?: number
  }
  exposure_trend?: ExposurePoint[]
  feedback_counts?: { counts: Record<string, number>; total: number }
  active_model?: { version_tag: string; trained_on?: string; deployed_at?: string } | null
}

export interface ExposurePoint {
  period: string
  amount: number
  invoices: number
}

export interface WorklistFacets {
  states: string[]
  sectors: string[]
  risk_bands: { critical: number; high: number; medium: number }
}

export interface AssignableUser {
  id: string
  email: string
  display_name?: string
  role: string
}

export interface EntityAssignment {
  entity_cin: string
  assignee_id?: string
  assignee_name?: string
  assigned_at?: string
}

export interface CaseComment {
  id: string
  case_id: string
  author_id?: string
  author_name?: string
  body: string
  created_at: string
}

export interface CaseActivityEntry {
  id: string
  case_id: string
  actor_id?: string
  actor_name?: string
  action: string
  detail: Record<string, any>
  created_at: string
}

export interface CaseEntityLink {
  case_id: string
  entity_cin: string
  added_by?: string
  added_at: string
}

export interface EntityNote {
  id: string
  entity_cin: string
  author_id?: string
  author_name?: string
  body: string
  created_at: string
}

export interface EntityHistoryEvent {
  kind: 'feedback' | 'case' | 'note' | 'invoice' | string
  at?: string
  title: string
  detail?: string
  actor?: string
  amount?: number
}

export interface EntityHistoryResponse {
  entity_cin: string
  events: EntityHistoryEvent[]
}

export interface TimelineInvoice {
  date: string
  amount: number
  seller_gstin: string
  buyer_gstin: string
  return_period: string
  counterparty: {
    id: string
    name: string
    cin: string
  }
}

export interface TimelineResponse {
  timeline: TimelineInvoice[]
}

export interface AuditLogEntry {
  id: string
  user_id?: string
  action: string
  entity_type?: string
  entity_id?: string
  details: Record<string, any>
  timestamp: string
}

export interface WorklistBulkResponse {
  action: string
  affected: number
  skipped: string[]
}

export interface Case {
  id: string
  title: string
  description?: string
  status: string
  assignee_id?: string
  created_at: string
  updated_at: string
  closed_at?: string
  metadata: Record<string, any>
  risk_score: number
  priority: number
  company_cin?: string
}

export interface CaseExportResponse {
  export_id: string
  format: string
  payload: Record<string, any>
}

export interface IngestionJobResponse {
  job_id: string
  status: string
  source: string
}

export interface IngestionJobStatus {
  id: string
  source: string
  status: string
  started_at: string
  completed_at?: string
  records_processed: number
  records_failed: number
  error_log?: string
}

export interface User {
  id: string
  email: string
  display_name?: string
  role: string
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
  /** The session credential. Short-lived access tokens are refreshed with it. */
  refresh_token?: string
  /** Access-token lifetime in seconds. */
  expires_in?: number
}
