from pydantic import BaseModel, Field
from typing import Optional, Any, List, Any, Dict
from datetime import date, datetime
from enum import Enum


class CompanyBase(BaseModel):
    cin: str
    gstin: Optional[str] = None
    name: str
    incorporation_date: Optional[date] = None
    status: Optional[str] = None
    authorized_capital: Optional[float] = None
    paid_up_capital: Optional[float] = None
    nic_code: Optional[str] = None
    roc: Optional[str] = None


class CompanyCreate(CompanyBase):
    pass


class Company(CompanyBase):
    id: str
    risk_score: Optional[float] = None
    risk_source: Optional[str] = None
    community_id: Optional[Any] = None
    pagerank: Optional[float] = None
    betweenness: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DirectorBase(BaseModel):
    din: str
    name: str
    pan_hash: str


class DirectorCreate(DirectorBase):
    pass


class Director(DirectorBase):
    id: str

    class Config:
        from_attributes = True


class AddressBase(BaseModel):
    street: str
    city: str
    state: str
    pincode: str
    country: str = "India"


class AddressCreate(AddressBase):
    pass


class Address(AddressBase):
    id: str

    class Config:
        from_attributes = True


class BankAccountBase(BaseModel):
    ifsc: str
    account_hash: str


class BankAccountCreate(BankAccountBase):
    pass


class BankAccount(BankAccountBase):
    id: str

    class Config:
        from_attributes = True


class TransactionBase(BaseModel):
    gstin_seller: str
    gstin_buyer: str
    amount: float
    invoice_date: date
    return_period: str


class Transaction(TransactionBase):
    pass


class SearchResult(BaseModel):
    id: str
    type: str
    name: str
    identifier: str
    risk_score: Optional[float] = None
    status: Optional[str] = None
    state: Optional[str] = None


class EntitySearchResponse(BaseModel):
    results: List[SearchResult]
    total: int


class NetworkNode(BaseModel):
    id: str
    label: str
    type: str
    properties: dict


class NetworkEdge(BaseModel):
    source: str
    target: str
    type: str
    properties: dict
    flagged: bool = False
    # True when this edge carries an invoice whose high value has no matching
    # e-Way Bill movement record (TASK B1). The UI badges these edges.
    eway_mismatch: bool = False


class NetworkResponse(BaseModel):
    nodes: List[NetworkNode]
    edges: List[NetworkEdge]


class LoopResult(BaseModel):
    path: List[str]
    length: int
    total_amount: Optional[float] = None
    companies: List[dict]


class LoopsResponse(BaseModel):
    loops: List[LoopResult]
    total: int


class RiskJobResponse(BaseModel):
    job_id: str
    status: str
    summary: Optional[dict] = None


class RiskResult(BaseModel):
    job_id: str
    status: str
    scores: Optional[dict] = None


class GNNModelInfo(BaseModel):
    """Active model_versions row (Backend Schema §3), enriched with the
    runtime state of the loaded GNN checkpoint."""
    id: str
    version_tag: str
    trained_on: str
    metrics: Dict[str, Any] = {}
    checkpoint_path: str
    deployed_at: Optional[datetime] = None
    is_active: bool
    checkpoint_available: bool
    runtime: Optional[Dict[str, Any]] = None


class ExplainEvidence(BaseModel):
    method: str = "subgraph_attribution"
    cycles: List[dict] = []
    communities: List[dict] = []
    shared_directors: List[dict] = []
    shared_addresses: List[dict] = []
    shared_bank_accounts: List[dict] = []
    eway_mismatches: List[dict] = []
    bursts: List[dict] = []
    risk: Optional[float] = None
    risk_decomposition: Optional[dict] = None


class ExplainResponse(BaseModel):
    entity: dict
    reasons: List[str]
    evidence: ExplainEvidence


class WorklistItem(BaseModel):
    cin: Optional[str] = None
    gstin: Optional[str] = None
    name: Optional[str] = None
    risk_score: Optional[float] = None
    status: Optional[str] = None
    nic_code: Optional[str] = None
    state: Optional[str] = None
    paid_up_capital: Optional[float] = None
    incorporation_date: Optional[str] = None
    pagerank: Optional[float] = None
    community_id: Optional[Any] = None
    cycle_count: Optional[int] = 0
    risk_source: Optional[str] = None


class WorklistResponse(BaseModel):
    items: List[WorklistItem]
    total: int
    page: int
    page_size: int


class StatsOverview(BaseModel):
    companies: int
    directors: int
    flagged_entities: int
    cycles_detected: int
    estimated_itc_at_risk: float
    top_risk_state: Optional[str] = None
    open_cases: int


class ResolveResponse(BaseModel):
    resolved_edges: int
    method: str = "deterministic+fuzzy"
    deterministic: int = 0
    fuzzy: int = 0


class CaseBase(BaseModel):
    title: str
    description: Optional[str] = None
    company_cin: Optional[str] = None
    priority: int = 0
    assignee_id: Optional[str] = None


class CaseCreate(CaseBase):
    pass


class CaseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assignee_id: Optional[str] = None
    priority: Optional[int] = None
    risk_score: Optional[float] = None


class Case(CaseBase):
    id: str
    status: str
    assignee_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    metadata: dict = {}
    risk_score: float = 0.0

    class Config:
        from_attributes = True


class CaseExportResponse(BaseModel):
    export_id: str
    format: str
    payload: dict


class ExportPreviewResponse(BaseModel):
    payload: dict


class IngestionJobResponse(BaseModel):
    job_id: str
    status: str
    source: str


class IngestionJobStatus(BaseModel):
    id: str
    source: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    records_processed: int
    records_failed: int
    error_log: Optional[str] = None


class UserBase(BaseModel):
    email: str
    role: str = "analyst"


class User(UserBase):
    id: str
    display_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict
    # The session credential (TASK C1). It is opaque, revocable and
    # short-lived; the access token above is what is sent on each request.
    refresh_token: Optional[str] = None
    # Lifetime of the access token in seconds, so a client knows when to
    # refresh instead of guessing.
    expires_in: Optional[int] = None


class RefreshRequest(BaseModel):
    refresh_token: str


# --- Admin user management (Super Admin only) --------------------------------
# The role is fixed by the 3-slot model (1 admin, 2 analysts), so no admin
# request schema accepts a role: PUT can only change email/display_name/password.

class AdminUserOut(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    role: str
    created_at: Optional[datetime] = None


class AdminUserList(BaseModel):
    users: List[AdminUserOut]


class AdminUserUpdate(BaseModel):
    """Change a standard user's identity or password. Role is not accepted."""
    email: Optional[str] = None
    display_name: Optional[str] = None
    password: Optional[str] = None


class PasswordReset(BaseModel):
    """Optional explicit password; when omitted a strong one is generated."""
    password: Optional[str] = None


class FeedbackCreate(BaseModel):
    entity_id: Optional[str] = None
    entity_cin: Optional[str] = None
    label: str
    note: Optional[str] = None


class FeedbackItem(BaseModel):
    id: str
    entity_id: Optional[str] = None
    entity_cin: Optional[str] = None
    user_id: Optional[str] = None
    label: str
    note: Optional[str] = None
    created_at: datetime


class AuditLogEntry(BaseModel):
    id: str
    user_id: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    details: dict = {}
    timestamp: datetime


# ---------------------------------------------------------------------------
# Case collaboration, worklist bulk actions and entity notes (P2.2)
# ---------------------------------------------------------------------------

class AssignableUser(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    role: str


class CaseCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class CaseComment(BaseModel):
    id: str
    case_id: str
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    body: str
    created_at: datetime


class CaseActivityEntry(BaseModel):
    id: str
    case_id: str
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    action: str
    detail: dict = {}
    created_at: datetime


class CaseEntityAdd(BaseModel):
    entity_cin: str


class CaseEntityLink(BaseModel):
    case_id: str
    entity_cin: str
    added_by: Optional[str] = None
    added_at: datetime


class EntityAssignmentOut(BaseModel):
    entity_cin: str
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    assigned_at: Optional[datetime] = None


class EntityNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class EntityNote(BaseModel):
    id: str
    entity_cin: str
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    body: str
    created_at: datetime


class WorklistBulkRequest(BaseModel):
    action: str
    entity_cins: List[str] = Field(min_length=1)
    label: Optional[str] = None
    assignee_id: Optional[str] = None
    case_id: Optional[str] = None


class WorklistBulkResponse(BaseModel):
    action: str
    affected: int
    skipped: List[str] = []


class WorklistFacets(BaseModel):
    states: List[str]
    sectors: List[str]
    risk_bands: dict


class EntityHistoryEvent(BaseModel):
    kind: str
    at: Optional[datetime] = None
    title: str
    detail: Optional[str] = None
    actor: Optional[str] = None
    amount: Optional[float] = None
