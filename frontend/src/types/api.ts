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
}
