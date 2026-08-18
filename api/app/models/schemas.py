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


class ExplainEvidence(BaseModel):
    cycles: List[dict] = []
    shared_directors: List[dict] = []
    shared_addresses: List[dict] = []
    risk: Optional[float] = None


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
    method: str


class CaseBase(BaseModel):
    title: str
    description: Optional[str] = None
    company_cin: Optional[str] = None
    priority: int = 0


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


class UserCreate(UserBase):
    display_name: Optional[str] = None
    password: str


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


class AuditLogEntry(BaseModel):
    id: str
    user_id: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    details: dict = {}
    timestamp: datetime
