from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SourceType = Literal[
    "webpage",
    "dynamic_webpage",
    "sitemap",
    "rss",
    "public_api",
    "social_api",
    "public_database",
    "file_upload",
]
SourceAccessMethod = Literal["public", "api_key", "oauth2", "secret_ref", "upload"]
SourceAuthorizationStatus = Literal["pending", "approved", "expired", "rejected"]
SourceClassification = Literal["public", "internal", "restricted"]
SourceFrequency = Literal["manual", "15m", "hourly", "6h", "daily", "weekly"]
SourceOperationalStatus = Literal["healthy", "warning", "error", "disabled"]
SourceCheckStatus = Literal["passed", "failed", "pending", "not_applicable"]
CollectionRunStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "partial",
    "failed",
    "cancelled",
    "manual_review",
]
SourceTriggerType = Literal["manual", "scheduled", "event", "api", "upload", "retry", "recovery"]
WorkflowStepStatus = Literal[
    "pending",
    "running",
    "waiting_retry",
    "succeeded",
    "failed",
    "skipped",
]
ProcessingStatus = Literal[
    "pending",
    "processing",
    "completed",
    "review_required",
    "failed",
]
OCRStatus = Literal["not_required", "completed", "unavailable", "failed"]
DuplicateType = Literal["none", "exact", "near"]
EntityType = Literal[
    "company",
    "brand",
    "product",
    "person",
    "version",
    "price",
    "location",
    "date",
    "feature",
]
EventType = Literal[
    "release",
    "price_increase",
    "price_decrease",
    "partnership",
    "funding",
    "acquisition",
    "market_entry",
    "market_exit",
    "feature_add",
    "feature_remove",
    "hiring",
]
KnowledgeItemType = Literal["fact", "entity", "event", "insight"]
KnowledgeReviewStatus = Literal["verified", "review_required", "conflict"]
KnowledgeValidityStatus = Literal["active", "at_risk", "expired", "archived"]


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(APIModel):
    status: Literal["ok"]
    service: str
    environment: str
    database: Literal["ok"]


class UserSummary(APIModel):
    id: str
    name: str
    initial: str


class ProjectSummary(APIModel):
    id: str
    name: str
    avatar: str
    template: str
    regions: list[str]
    status: Literal["active", "archived"]


class ProjectCreate(APIModel):
    name: str = Field(min_length=1, max_length=100)
    template: Literal["daily", "compare", "strategy"] = "daily"
    regions: list[Literal["cn", "global", "jp", "sea"]] = Field(
        default_factory=lambda: ["cn", "global"], min_length=1
    )


class Headline(APIModel):
    greeting: str
    new_changes: int
    priority_changes: int


class DailyBrief(APIModel):
    title: str
    summary: str
    evidence_count: int
    confidence: int
    impact_level: Literal["high", "medium", "low"]
    insight_id: int | None = None


class Metric(APIModel):
    key: str
    label: str
    value: str
    unit: str | None = None
    delta: str
    trend: Literal["up", "down"]
    note: str
    accent: bool = False


class TrendSeries(APIModel):
    range: Literal["24h", "7d", "30d"]
    labels: list[str]
    events: list[int]
    high_impact: list[int]


class SourceHealth(APIModel):
    score: int
    total: int
    normal: int
    abnormal: int
    disabled: int
    last_sync: str


class SourceCheck(APIModel):
    key: Literal[
        "connectivity",
        "compliance",
        "rate_limit",
        "field_availability",
    ]
    label: str
    status: SourceCheckStatus
    message: str
    checked_at: str | None = None


class SourceHealthMetrics(APIModel):
    success_rate: float = Field(ge=0, le=100)
    consecutive_failures: int = Field(ge=0)
    average_latency_ms: int = Field(ge=0)
    freshness_minutes: int = Field(ge=0)
    content_change_rate: float = Field(ge=0, le=100)
    parser_completeness: float = Field(ge=0, le=100)


class SourceRecord(APIModel):
    id: str
    project_id: str
    name: str
    source_type: SourceType
    endpoint: str
    subject: str
    access_method: SourceAccessMethod
    crawl_strategy: str
    regions: list[str]
    authorization_basis: str
    authorization_status: SourceAuthorizationStatus
    data_classification: SourceClassification
    retention_days: int
    schedule_frequency: SourceFrequency
    rate_limit_per_minute: int
    concurrency_limit: int
    task_timeout_seconds: int
    max_attempts: int
    retry_backoff_seconds: int
    priority: int
    circuit_state: Literal["closed", "open", "half_open"]
    circuit_open_until: str | None = None
    credential_masked: str | None = None
    credential_expires_at: str | None = None
    fields_available: list[str]
    collection_config: dict[str, Any]
    robots_acknowledged: bool
    terms_acknowledged: bool
    enabled: bool
    status: SourceOperationalStatus
    health_score: int = Field(ge=0, le=100)
    health: SourceHealthMetrics
    checks: list[SourceCheck]
    activation_ready: bool
    last_checked_at: str | None = None
    last_collected_at: str | None = None
    last_success_at: str | None = None
    next_run_at: str | None = None
    archived_at: str | None = None
    archived_by: str | None = None
    created_at: str
    updated_at: str


class SourceCreate(APIModel):
    project_id: str
    name: str = Field(min_length=1, max_length=100)
    source_type: SourceType
    endpoint: str = Field(min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=100)
    access_method: SourceAccessMethod = "public"
    crawl_strategy: str = Field(default="增量采集", min_length=1, max_length=100)
    regions: list[str] = Field(default_factory=lambda: ["global"], min_length=1)
    authorization_basis: str = Field(min_length=1, max_length=300)
    authorization_status: SourceAuthorizationStatus = "pending"
    data_classification: SourceClassification = "public"
    retention_days: int = Field(default=365, ge=1, le=3650)
    schedule_frequency: SourceFrequency = "daily"
    rate_limit_per_minute: int = Field(default=30, ge=1, le=600)
    concurrency_limit: int = Field(default=1, ge=1, le=10)
    task_timeout_seconds: int = Field(default=120, ge=5, le=900)
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_backoff_seconds: int = Field(default=2, ge=1, le=300)
    priority: int = Field(default=5, ge=1, le=10)
    credential_ref: str | None = Field(default=None, max_length=200)
    credential_expires_at: datetime | None = None
    fields_available: list[str] = Field(default_factory=list, max_length=50)
    collection_config: dict[str, Any] = Field(default_factory=dict)
    robots_acknowledged: bool = False
    terms_acknowledged: bool = False

    @field_validator("name", "subject", "authorization_basis", "crawl_strategy")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("字段不能为空")
        return value

    @field_validator("fields_available")
    @classmethod
    def normalize_fields(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @model_validator(mode="after")
    def validate_endpoint_and_credential(self) -> "SourceCreate":
        endpoint = self.endpoint.strip()
        if self.source_type != "file_upload":
            parsed = urlparse(endpoint)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("在线数据源必须使用有效的 HTTP 或 HTTPS 地址")
        if self.access_method in {"api_key", "oauth2", "secret_ref"} and not self.credential_ref:
            raise ValueError("当前访问方式需要填写密钥服务引用")
        method = str(self.collection_config.get("request_method", "GET")).upper()
        if self.source_type in {"public_api", "social_api", "public_database"} and method != "GET":
            raise ValueError("API 采集仅允许只读 GET 请求")
        max_items = self.collection_config.get("max_items", 50)
        if not isinstance(max_items, int) or not 1 <= max_items <= 200:
            raise ValueError("max_items 必须是 1 到 200 之间的整数")
        timeout_seconds = self.collection_config.get("timeout_seconds", 20)
        if not isinstance(timeout_seconds, (int, float)) or not 1 <= timeout_seconds <= 60:
            raise ValueError("timeout_seconds 必须在 1 到 60 秒之间")
        self.endpoint = endpoint
        return self


class SourceUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    source_type: SourceType | None = None
    endpoint: str | None = Field(default=None, min_length=1, max_length=500)
    subject: str | None = Field(default=None, min_length=1, max_length=100)
    access_method: SourceAccessMethod | None = None
    crawl_strategy: str | None = Field(default=None, min_length=1, max_length=100)
    regions: list[str] | None = Field(default=None, min_length=1)
    authorization_basis: str | None = Field(default=None, min_length=1, max_length=300)
    authorization_status: SourceAuthorizationStatus | None = None
    data_classification: SourceClassification | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    schedule_frequency: SourceFrequency | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=600)
    concurrency_limit: int | None = Field(default=None, ge=1, le=10)
    task_timeout_seconds: int | None = Field(default=None, ge=5, le=900)
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    retry_backoff_seconds: int | None = Field(default=None, ge=1, le=300)
    priority: int | None = Field(default=None, ge=1, le=10)
    credential_ref: str | None = Field(default=None, max_length=200)
    credential_expires_at: datetime | None = None
    fields_available: list[str] | None = Field(default=None, max_length=50)
    collection_config: dict[str, Any] | None = None
    robots_acknowledged: bool | None = None
    terms_acknowledged: bool | None = None

    @field_validator("name", "subject", "authorization_basis", "crawl_strategy", "endpoint")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("字段不能为空")
        return value

    @field_validator("fields_available")
    @classmethod
    def normalize_optional_fields(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class SourceStatusUpdate(APIModel):
    enabled: bool


class SourceCredentialRotate(APIModel):
    credential_ref: str = Field(min_length=1, max_length=200)
    credential_expires_at: datetime | None = None


class SourceListSummary(APIModel):
    total: int
    enabled: int
    needs_attention: int
    disabled: int
    expiring_credentials: int
    average_health: int


class SourceListResponse(APIModel):
    project_id: str
    summary: SourceListSummary
    items: list[SourceRecord]


class SourceActionResponse(APIModel):
    item: SourceRecord
    message: str


class SourceScheduleUpdate(APIModel):
    schedule_frequency: SourceFrequency
    rate_limit_per_minute: int = Field(ge=1, le=600)
    concurrency_limit: int = Field(ge=1, le=10)
    task_timeout_seconds: int = Field(ge=5, le=900)
    max_attempts: int = Field(ge=1, le=10)
    retry_backoff_seconds: int = Field(ge=1, le=300)
    priority: int = Field(ge=1, le=10)


class WorkflowStep(APIModel):
    key: str
    name: str
    agent: str
    order: int
    status: WorkflowStepStatus
    attempt: int
    max_attempts: int
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    output_summary: str | None = None


class SourceRunSummary(APIModel):
    id: str
    source_id: str
    project_id: str
    source_name: str
    source_type: SourceType
    trigger_type: SourceTriggerType
    status: CollectionRunStatus
    priority: int
    attempt: int
    max_attempts: int
    timeout_seconds: int
    backoff_seconds: int
    scheduled_for: str | None = None
    available_at: str | None = None
    next_retry_at: str | None = None
    retry_delays: list[int] = Field(default_factory=list)
    retry_of: str | None = None
    recovery_of: str | None = None
    recovered_from_restart: bool = False
    workflow_version: str
    workflow_steps: list[WorkflowStep] = Field(default_factory=list)
    items_discovered: int
    documents_created: int
    documents_updated: int
    duplicates_skipped: int
    error_type: str | None = None
    error_message: str | None = None
    request_summary: str | None = None
    parser_steps: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str


class SourceRunListSummary(APIModel):
    total: int
    running: int
    succeeded: int
    failed: int


class SourceRunListResponse(APIModel):
    project_id: str
    summary: SourceRunListSummary
    items: list[SourceRunSummary]


class OrchestrationSummary(APIModel):
    scheduled_sources: int
    queued: int
    running: int
    exceptions: int
    success_rate_24h: float = Field(ge=0, le=100)
    recovered_24h: int


class OrchestrationSchedule(APIModel):
    source: SourceRecord
    active_runs: int
    last_run_status: CollectionRunStatus | None = None


class WorkflowNodeDefinition(APIModel):
    key: str
    name: str
    agent: str
    description: str


class OrchestrationDashboard(APIModel):
    project_id: str
    generated_at: str
    summary: OrchestrationSummary
    workflow_nodes: list[WorkflowNodeDefinition]
    schedules: list[OrchestrationSchedule]
    runs: list[SourceRunSummary]
    exceptions: list[SourceRunSummary]


class OrchestrationTrigger(APIModel):
    source_id: str
    trigger_type: Literal["manual", "event", "api"] = "manual"
    event_name: str | None = Field(default=None, max_length=100)


class OrchestrationBulkRetry(APIModel):
    run_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("run_ids")
    @classmethod
    def unique_run_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class OrchestrationRecover(APIModel):
    project_id: str
    run_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("run_ids")
    @classmethod
    def unique_recovery_run_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class OrchestrationActionResult(APIModel):
    queued: list[SourceRunSummary]
    skipped: dict[str, str] = Field(default_factory=dict)


class CollectionDocumentSummary(APIModel):
    id: str
    project_id: str
    source_id: str
    source_name: str
    source_type: SourceType
    run_id: str
    canonical_url: str
    title: str
    published_at: str | None = None
    collected_at: str
    language: str | None = None
    content_type: str
    content_hash: str
    readable_excerpt: str
    word_count: int
    version: int
    is_latest: bool


class CollectionDocumentDetail(CollectionDocumentSummary):
    readable_text: str
    metadata: dict[str, Any]
    structured_fields: dict[str, Any]
    parser_version: str
    previous_document_id: str | None = None


class CollectionDocumentListSummary(APIModel):
    total: int
    latest: int
    sources: int


class CollectionDocumentListResponse(APIModel):
    project_id: str
    summary: CollectionDocumentListSummary
    items: list[CollectionDocumentSummary]


class FileUploadResponse(APIModel):
    source: SourceRecord
    run: SourceRunSummary


class ProcessingOptions(APIModel):
    extract_body: bool = True
    denoise: bool = True
    deduplicate: bool = True
    detect_language: bool = True
    ocr: bool = True
    extract_entities: bool = True
    extract_events: bool = True


class ProcessingBatchRequest(APIModel):
    project_id: str
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    options: ProcessingOptions = Field(default_factory=ProcessingOptions)

    @field_validator("document_ids")
    @classmethod
    def unique_document_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class ProcessingStep(APIModel):
    key: str
    label: str
    status: Literal["completed", "skipped", "warning", "failed"]
    duration_ms: int = Field(ge=0)
    summary: str


class EntityMention(APIModel):
    id: str
    type: EntityType
    text: str
    normalized: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    method: str


class ExtractedEvent(APIModel):
    id: str
    type: EventType
    label: str
    subject: str | None = None
    object: str | None = None
    occurred_at: str | None = None
    impact_level: Literal["high", "medium", "low"]
    confidence: float = Field(ge=0, le=1)
    evidence_text: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    method: str


class DuplicateMatch(APIModel):
    type: DuplicateType
    document_id: str | None = None
    title: str | None = None
    source_name: str | None = None
    similarity: float = Field(default=0, ge=0, le=1)
    cluster_id: str


class ProcessingDocumentSummary(APIModel):
    document_id: str
    project_id: str
    source_id: str
    source_name: str
    title: str
    collected_at: str
    content_type: str
    status: ProcessingStatus
    quality_score: int = Field(ge=0, le=100)
    language: str | None = None
    language_confidence: float = Field(default=0, ge=0, le=1)
    ocr_status: OCRStatus
    duplicate: DuplicateMatch
    entity_count: int = Field(ge=0)
    event_count: int = Field(ge=0)
    noise_removed_lines: int = Field(ge=0)
    needs_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    processed_at: str | None = None


class ProcessingDocumentDetail(ProcessingDocumentSummary):
    original_excerpt: str
    clean_text: str
    body_extraction_method: str
    entities: list[EntityMention]
    events: list[ExtractedEvent]
    steps: list[ProcessingStep]
    processor_version: str
    error_message: str | None = None


class ProcessingOverviewSummary(APIModel):
    total: int
    processed: int
    pending: int
    review_required: int
    failed: int
    duplicates: int
    entities: int
    events: int
    ocr_completed: int


class ProcessingOverview(APIModel):
    project_id: str
    generated_at: str
    summary: ProcessingOverviewSummary
    items: list[ProcessingDocumentSummary]


class ProcessingBatchResponse(APIModel):
    requested: int
    completed: int
    review_required: int
    failed: int
    items: list[ProcessingDocumentSummary]


class KnowledgeCollectionSummary(APIModel):
    id: str
    project_id: str
    name: str
    description: str
    color: str
    item_count: int = Field(ge=0)
    updated_at: str


class KnowledgeCollectionCreate(APIModel):
    project_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    color: str = Field(default="#687c67", pattern=r"^#[0-9A-Fa-f]{6}$")


class KnowledgeItemSummary(APIModel):
    id: str
    project_id: str
    document_id: str | None = None
    source_id: str | None = None
    item_type: KnowledgeItemType
    title: str
    summary: str
    subject: str | None = None
    category: str
    language: str | None = None
    tags: list[str]
    confidence: int = Field(ge=0, le=100)
    quality_score: int = Field(ge=0, le=100)
    review_status: KnowledgeReviewStatus
    validity_status: KnowledgeValidityStatus
    source_count: int = Field(ge=0)
    source_name: str
    source_url: str
    evidence_excerpt: str
    extraction_method: str
    published_at: str | None = None
    updated_at: str
    collection_count: int = Field(ge=0)


class KnowledgeStorageSummary(APIModel):
    raw_documents: int = Field(ge=0)
    document_versions: int = Field(ge=0)
    processed_documents: int = Field(ge=0)
    storage_bytes: int = Field(ge=0)


class KnowledgeOverviewSummary(APIModel):
    knowledge_items: int = Field(ge=0)
    verified: int = Field(ge=0)
    review_required: int = Field(ge=0)
    conflicts: int = Field(ge=0)
    collections: int = Field(ge=0)
    sources: int = Field(ge=0)
    evidence_coverage: int = Field(ge=0, le=100)
    latest_update: str | None = None


class KnowledgeOverview(APIModel):
    project_id: str
    generated_at: str
    summary: KnowledgeOverviewSummary
    storage: KnowledgeStorageSummary
    type_counts: dict[KnowledgeItemType, int]
    items: list[KnowledgeItemSummary]
    collections: list[KnowledgeCollectionSummary]


class KnowledgeSourceTrace(APIModel):
    id: str | None = None
    name: str
    url: str
    authorization_status: SourceAuthorizationStatus | None = None
    retention_days: int | None = Field(default=None, ge=0)


class KnowledgeDocumentTrace(APIModel):
    id: str
    title: str
    version: int = Field(ge=1)
    content_hash: str
    parser_version: str
    collected_at: str
    published_at: str | None = None
    raw_available: bool


class KnowledgeEvidenceTrace(APIModel):
    excerpt: str
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    extraction_method: str


class KnowledgeRevision(APIModel):
    version: int = Field(ge=1)
    action: str
    snapshot: dict[str, Any]
    note: str
    changed_by: str | None = None
    created_at: str


class KnowledgeItemDetail(KnowledgeItemSummary):
    content: str
    source: KnowledgeSourceTrace
    document: KnowledgeDocumentTrace | None = None
    evidence: KnowledgeEvidenceTrace
    collections: list[KnowledgeCollectionSummary]
    revisions: list[KnowledgeRevision]


class KnowledgeReviewUpdate(APIModel):
    review_status: KnowledgeReviewStatus
    note: str = Field(default="", max_length=500)


class SourceArchiveResponse(APIModel):
    id: str
    archived: Literal[True]
    archived_at: str


class SourcePurgeRequest(APIModel):
    confirmation: str = Field(min_length=1, max_length=100)


class SourcePurgeResponse(APIModel):
    id: str
    purged: Literal[True]
    removed_runs: int = Field(ge=0)
    removed_documents: int = Field(ge=0)
    detached_knowledge_items: int = Field(ge=0)


class InsightSummary(APIModel):
    id: int
    time: str
    type: Literal["事实", "推断", "建议"]
    level: Literal["high", "medium", "low"]
    company: str
    title: str
    summary: str
    sources: int
    confidence: int


class Evidence(APIModel):
    id: int
    title: str
    source_name: str
    source_url: str
    excerpt: str
    source_type: Literal["primary", "cross_check"]
    published_at: str


class InsightDetail(InsightSummary):
    recommendation: str
    evidence: list[Evidence]


class ReviewItem(APIModel):
    id: int
    company: str
    field: str
    reason: str
    time: str
    tone: Literal["conflict", "warning", "neutral"]
    status: Literal["pending", "claimed", "resolved"]
    claimed_by: str | None = None


class ReviewQueue(APIModel):
    total: int
    items: list[ReviewItem]


class ReportSummary(APIModel):
    id: str
    title: str
    meta: str
    state: Literal["已交付", "生成中", "待审批", "生成失败"]
    progress: int = Field(ge=0, le=100)


class WorkbenchResponse(APIModel):
    project: ProjectSummary
    projects: list[ProjectSummary]
    user: UserSummary
    data_cutoff: str
    headline: Headline
    daily_brief: DailyBrief
    metrics: list[Metric]
    trend: TrendSeries
    source_health: SourceHealth
    insights: list[InsightSummary]
    review_queue: ReviewQueue
    reports: list[ReportSummary]


class ReviewClaimResponse(APIModel):
    item: ReviewItem
    pending_count: int


class ReportGenerate(APIModel):
    project_id: str
    template: Literal[
        "daily", "weekly", "compare", "flash", "strategy", "executive"
    ] = "daily"
    template_id: str | None = None
    time_window: Literal["24h", "7d", "30d", "90d"] = "24h"
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    audience: Literal["analyst", "product", "management", "general"] = "analyst"
    length: Literal["brief", "standard", "detailed"] = "standard"
    approval_required: bool | None = None


class ReportTemplateRecord(APIModel):
    id: str
    name: str
    report_type: Literal[
        "daily", "weekly", "compare", "flash", "strategy", "executive"
    ]
    description: str
    sections: list[str]
    language: Literal["zh-CN", "en-US"]
    audience: str
    approval_required: bool
    builtin: bool
    updated_at: str


class ReportRecord(APIModel):
    id: str
    project_id: str
    template_id: str | None
    title: str
    report_type: str
    version: int = Field(ge=1)
    time_window: str
    language: str
    audience: str
    state: Literal["已交付", "生成中", "待审批", "生成失败"]
    progress: int = Field(ge=0, le=100)
    approval_status: Literal["not_required", "pending", "approved", "rejected"]
    evidence_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    confidence: int = Field(ge=0, le=100)
    data_cutoff: str | None
    sections: dict[str, Any]
    failure_reason: str | None
    approved_by: str | None
    approved_at: str | None
    delivered_at: str | None
    created_at: str
    updated_at: str


class ReportSubscriptionRecord(APIModel):
    id: str
    project_id: str
    name: str
    template_id: str
    cadence: Literal["daily", "weekly", "monthly", "event"]
    delivery_time: str
    timezone: str
    channels: list[Literal["in_app", "email", "enterprise_message"]]
    recipients: list[str]
    enabled: bool
    next_run_at: str | None
    last_delivery_status: Literal["success", "failed", "pending", "never"]
    updated_at: str


class ReportSubscriptionUpdate(APIModel):
    enabled: bool


class AlertRuleRecord(APIModel):
    id: str
    project_id: str
    name: str
    competitors: list[str]
    keywords: list[str]
    event_types: list[str]
    min_impact: Literal["low", "medium", "high"]
    min_confidence: int = Field(ge=0, le=100)
    change_threshold: float = Field(ge=0)
    quiet_minutes: int = Field(ge=0, le=10080)
    escalation_minutes: int = Field(ge=0, le=10080)
    channels: list[Literal["in_app", "email", "enterprise_message"]]
    enabled: bool
    last_triggered_at: str | None
    updated_at: str


class AlertRuleCreate(APIModel):
    project_id: str
    name: str = Field(min_length=2, max_length=80)
    competitors: list[str] = Field(default_factory=list, max_length=20)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    event_types: list[str] = Field(default_factory=list, max_length=20)
    min_impact: Literal["low", "medium", "high"] = "medium"
    min_confidence: int = Field(default=75, ge=0, le=100)
    change_threshold: float = Field(default=0, ge=0)
    quiet_minutes: int = Field(default=60, ge=0, le=10080)
    escalation_minutes: int = Field(default=120, ge=0, le=10080)
    channels: list[Literal["in_app", "email", "enterprise_message"]] = Field(
        default_factory=lambda: ["in_app"]
    )
    enabled: bool = True


class AlertRuleUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    min_impact: Literal["low", "medium", "high"] | None = None
    min_confidence: int | None = Field(default=None, ge=0, le=100)
    quiet_minutes: int | None = Field(default=None, ge=0, le=10080)
    escalation_minutes: int | None = Field(default=None, ge=0, le=10080)
    channels: list[Literal["in_app", "email", "enterprise_message"]] | None = None
    enabled: bool | None = None


class AlertRecord(APIModel):
    id: str
    project_id: str
    rule_id: str | None
    insight_id: int | None
    title: str
    summary: str
    competitor: str
    event_type: str
    impact: Literal["low", "medium", "high", "critical"]
    confidence: int = Field(ge=0, le=100)
    source_count: int = Field(ge=0)
    status: Literal["new", "acknowledged", "resolved", "suppressed"]
    occurrence_count: int = Field(ge=1)
    first_seen_at: str
    last_seen_at: str
    quiet_until: str | None
    acknowledged_by: str | None
    acknowledged_at: str | None
    resolved_by: str | None
    resolved_at: str | None


class ReportingSummary(APIModel):
    delivered: int = Field(ge=0)
    generating: int = Field(ge=0)
    pending_approval: int = Field(ge=0)
    active_alerts: int = Field(ge=0)
    critical_alerts: int = Field(ge=0)
    on_time_rate: float = Field(ge=0, le=100)
    evidence_coverage: float = Field(ge=0, le=100)


class ReportingDashboard(APIModel):
    project_id: str
    generated_at: str
    summary: ReportingSummary
    templates: list[ReportTemplateRecord]
    reports: list[ReportRecord]
    subscriptions: list[ReportSubscriptionRecord]
    alert_rules: list[AlertRuleRecord]
    alerts: list[AlertRecord]


class ReportApproval(APIModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=500)


class AlertAction(APIModel):
    action: Literal["acknowledge", "resolve"]
    note: str = Field(default="", max_length=500)


class SearchResult(APIModel):
    kind: Literal["project", "insight", "report", "evidence", "source", "knowledge"]
    id: str
    title: str
    subtitle: str


class SearchResponse(APIModel):
    query: str
    total: int
    items: list[SearchResult]


KnowledgeItemFilterType = Literal["fact", "entity", "event", "insight"]
KnowledgeReviewFilter = Literal["verified", "review_required", "conflict"]


class RAGFilters(APIModel):
    competitors: list[str] = Field(default_factory=list, max_length=8)
    item_types: list[KnowledgeItemFilterType] = Field(default_factory=list, max_length=4)
    categories: list[str] = Field(default_factory=list, max_length=12)
    review_statuses: list[KnowledgeReviewFilter] = Field(default_factory=list, max_length=3)
    collection_id: str | None = None
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    include_at_risk: bool = True
    top_k: int = Field(default=6, ge=3, le=12)


class RAGQueryRequest(APIModel):
    project_id: str = Field(min_length=1)
    question: str = Field(min_length=2, max_length=500)
    filters: RAGFilters = Field(default_factory=RAGFilters)


class RAGCitation(APIModel):
    id: int = Field(ge=1)
    item_id: str
    title: str
    subject: str
    item_type: KnowledgeItemFilterType
    category: str
    summary: str
    evidence_excerpt: str
    source_name: str
    source_url: str
    published_at: str | None = None
    confidence: int = Field(ge=0, le=100)
    relevance: float = Field(ge=0, le=1)
    review_status: KnowledgeReviewFilter
    validity_status: KnowledgeValidityStatus


class RAGTraceStage(APIModel):
    key: str
    label: str
    status: Literal["completed", "warning"]
    detail: str


class RAGTrace(APIModel):
    query_terms: list[str]
    candidate_count: int = Field(ge=0)
    retrieved_count: int = Field(ge=0)
    generation_mode: Literal["extractive_grounded"] = "extractive_grounded"
    stages: list[RAGTraceStage]


class RAGResponse(APIModel):
    id: str
    project_id: str
    question: str
    answer: str
    answer_type: Literal["grounded", "insufficient"]
    confidence: int = Field(ge=0, le=100)
    data_cutoff: str
    citations: list[RAGCitation]
    trace: RAGTrace
    notices: list[str]
    created_at: str


CompetitiveDimension = Literal[
    "capability", "pricing", "governance", "release", "market", "reputation"
]


class CompetitiveAnalysisRequest(APIModel):
    project_id: str = Field(min_length=1)
    competitors: list[str] = Field(min_length=2, max_length=8)
    dimensions: list[CompetitiveDimension] = Field(
        default_factory=lambda: ["capability", "pricing", "governance", "release"],
        min_length=1,
        max_length=6,
    )
    range_key: Literal["7d", "30d", "90d", "all"] = "30d"

    @field_validator("competitors")
    @classmethod
    def unique_competitors(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if len(dict.fromkeys(cleaned)) < 2:
            raise ValueError("至少选择两个不同竞品")
        return list(dict.fromkeys(cleaned))

    @field_validator("dimensions")
    @classmethod
    def unique_dimensions(
        cls, value: list[CompetitiveDimension]
    ) -> list[CompetitiveDimension]:
        return list(dict.fromkeys(value))


class AnalysisAgentStep(APIModel):
    key: str
    label: str
    agent: str
    status: Literal["completed", "warning"]
    detail: str
    evidence_count: int = Field(ge=0)


class ComparisonCell(APIModel):
    competitor: str
    dimension: CompetitiveDimension
    dimension_label: str
    status: Literal["evidence", "limited", "conflict", "missing"]
    summary: str
    confidence: int = Field(ge=0, le=100)
    evidence_count: int = Field(ge=0)
    citation_ids: list[int]


class AnalysisFinding(APIModel):
    type: Literal["fact", "inference"]
    title: str
    detail: str
    impact_level: Literal["high", "medium", "low"]
    competitors: list[str]
    citation_ids: list[int]


class SWOTEntry(APIModel):
    text: str
    citation_ids: list[int]


class CompetitorSWOT(APIModel):
    competitor: str
    strengths: list[SWOTEntry]
    weaknesses: list[SWOTEntry]
    opportunities: list[SWOTEntry]
    threats: list[SWOTEntry]


class BusinessRecommendation(APIModel):
    applicable_to: str
    action: str
    basis: str
    expected_impact: str
    risk: str
    validation: str
    citation_ids: list[int]


class CompetitiveAnalysisResult(APIModel):
    id: str
    project_id: str
    title: str
    status: Literal["completed", "partial"]
    competitors: list[str]
    dimensions: list[CompetitiveDimension]
    range_key: Literal["7d", "30d", "90d", "all"]
    data_cutoff: str
    sample_size: int = Field(ge=0)
    source_count: int = Field(ge=0)
    coverage_rate: int = Field(ge=0, le=100)
    executive_summary: str
    matrix: list[ComparisonCell]
    findings: list[AnalysisFinding]
    swot: list[CompetitorSWOT]
    recommendations: list[BusinessRecommendation]
    citations: list[RAGCitation]
    agent_steps: list[AnalysisAgentStep]
    notices: list[str]
    created_at: str
    completed_at: str


class CompetitiveAnalysisRunSummary(APIModel):
    id: str
    title: str
    status: Literal["completed", "partial"]
    competitors: list[str]
    dimensions: list[CompetitiveDimension]
    range_key: Literal["7d", "30d", "90d", "all"]
    coverage_rate: int = Field(ge=0, le=100)
    sample_size: int = Field(ge=0)
    created_at: str


class CompetitiveAnalysisOverview(APIModel):
    project_id: str
    suggested_competitors: list[str]
    dimensions: dict[CompetitiveDimension, str]
    runs: list[CompetitiveAnalysisRunSummary]


class OrganizationRecord(APIModel):
    id: str
    name: str
    domain: str
    plan: str
    sso_enforced: bool
    mfa_required: bool
    session_timeout_minutes: int = Field(ge=5, le=1440)
    status: Literal["active", "suspended"]


class RoleRecord(APIModel):
    id: str
    name: str
    description: str
    permissions: list[str]
    system: bool


class AdminUserRecord(APIModel):
    id: str
    name: str
    initial: str
    email: str
    role_id: str
    role_name: str
    status: Literal["active", "invited", "suspended"]
    mfa_enabled: bool
    export_permission: Literal["none", "standard", "sensitive"]
    project_scopes: list[str]
    data_domains: list[str]
    last_login_at: str | None


class AdminUserAccessUpdate(APIModel):
    role_id: str | None = None
    status: Literal["active", "invited", "suspended"] | None = None
    mfa_enabled: bool | None = None
    export_permission: Literal["none", "standard", "sensitive"] | None = None
    project_scopes: list[str] | None = Field(default=None, max_length=50)
    data_domains: list[str] | None = Field(default=None, max_length=30)


class ModelConfigRecord(APIModel):
    id: str
    provider: str
    model_name: str
    version: str
    routing_class: Literal["standard", "private", "restricted"]
    status: Literal["active", "degraded", "disabled"]
    allowed_data_classifications: list[str]
    monthly_budget: float = Field(ge=0)
    spent_amount: float = Field(ge=0)
    quota_warning_percent: int = Field(ge=1, le=100)
    fallback_model: str | None
    latency_p95_ms: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=100)
    updated_at: str


class ModelConfigUpdate(APIModel):
    status: Literal["active", "degraded", "disabled"] | None = None
    routing_class: Literal["standard", "private", "restricted"] | None = None
    allowed_data_classifications: list[str] | None = None
    monthly_budget: float | None = Field(default=None, ge=0)
    quota_warning_percent: int | None = Field(default=None, ge=1, le=100)
    fallback_model: str | None = Field(default=None, max_length=120)


class EvaluationMetricRecord(APIModel):
    id: str
    model_config_id: str
    dataset_name: str
    accuracy: float = Field(ge=0, le=100)
    citation_completeness: float = Field(ge=0, le=100)
    refusal_rate: float = Field(ge=0, le=100)
    latency_p95_ms: int = Field(ge=0)
    cost_per_run: float = Field(ge=0)
    sample_size: int = Field(ge=0)
    evaluated_at: str


class SecurityPolicyRecord(APIModel):
    id: str
    key: str
    name: str
    category: Literal["identity", "data", "export", "retention", "model"]
    value: dict[str, Any]
    status: Literal["enforced", "monitoring", "disabled"]
    updated_by: str | None
    updated_at: str


class SecurityPolicyUpdate(APIModel):
    value: dict[str, Any] | None = None
    status: Literal["enforced", "monitoring", "disabled"] | None = None


class AuditEventRecord(APIModel):
    id: int
    actor_id: str | None
    actor_name: str
    action: str
    entity_type: str
    entity_id: str
    detail: dict[str, Any]
    created_at: str


class ServiceComponentRecord(APIModel):
    id: str
    name: str
    status: Literal["healthy", "degraded", "outage", "maintenance"]
    uptime: float = Field(ge=0, le=100)
    latency_p95_ms: int = Field(ge=0)
    detail: str
    last_checked_at: str


class IncidentRecord(APIModel):
    id: str
    title: str
    severity: Literal["sev1", "sev2", "sev3", "sev4"]
    status: Literal["open", "acknowledged", "monitoring", "resolved"]
    owner: str
    started_at: str
    updated_at: str
    detail: str


class BackupRecord(APIModel):
    id: str
    backup_type: Literal["full", "incremental"]
    status: Literal["running", "succeeded", "failed"]
    rpo_minutes: int = Field(ge=0)
    size_bytes: int = Field(ge=0)
    started_at: str
    completed_at: str | None
    restore_verified: bool


class OperationsSummary(APIModel):
    availability: float = Field(ge=0, le=100)
    task_success_rate: float = Field(ge=0, le=100)
    report_success_rate: float = Field(ge=0, le=100)
    active_incidents: int = Field(ge=0)
    rpo_minutes: int = Field(ge=0)
    rto_hours: float = Field(ge=0)
    monthly_cost: float = Field(ge=0)
    budget_utilization: float = Field(ge=0)


class AdminDashboard(APIModel):
    generated_at: str
    organization: OrganizationRecord
    summary: OperationsSummary
    roles: list[RoleRecord]
    users: list[AdminUserRecord]
    models: list[ModelConfigRecord]
    evaluations: list[EvaluationMetricRecord]
    policies: list[SecurityPolicyRecord]
    audit_events: list[AuditEventRecord]
    services: list[ServiceComponentRecord]
    incidents: list[IncidentRecord]
    backups: list[BackupRecord]


class IncidentAction(APIModel):
    action: Literal["acknowledge", "resolve"]
    note: str = Field(default="", max_length=500)


class BackupActionResponse(APIModel):
    backup: BackupRecord
    message: str
