export type RangeKey = "24h" | "7d" | "30d";
export type InsightType = "事实" | "推断" | "建议";
export type ImpactLevel = "high" | "medium" | "low";
export type SourceType =
  | "webpage"
  | "dynamic_webpage"
  | "sitemap"
  | "rss"
  | "public_api"
  | "social_api"
  | "public_database"
  | "file_upload";
export type SourceStatus = "healthy" | "warning" | "error" | "disabled";

export type Project = {
  id: string;
  name: string;
  avatar: string;
  template: string;
  regions: string[];
  status: "active" | "archived";
};

export type Insight = {
  id: number;
  time: string;
  type: InsightType;
  level: ImpactLevel;
  company: string;
  title: string;
  summary: string;
  sources: number;
  confidence: number;
};

export type Evidence = {
  id: number;
  title: string;
  source_name: string;
  source_url: string;
  excerpt: string;
  source_type: "primary" | "cross_check";
  published_at: string;
};

export type InsightDetail = Insight & {
  recommendation: string;
  evidence: Evidence[];
};

export type Metric = {
  key: string;
  label: string;
  value: string;
  unit?: string | null;
  delta: string;
  trend: "up" | "down";
  note: string;
  accent: boolean;
};

export type TrendData = {
  range: RangeKey;
  labels: string[];
  events: number[];
  high_impact: number[];
};

export type ReviewItem = {
  id: number;
  company: string;
  field: string;
  reason: string;
  time: string;
  tone: "conflict" | "warning" | "neutral";
  status: "pending" | "claimed" | "resolved";
  claimed_by: string | null;
};

export type Report = {
  id: string;
  title: string;
  meta: string;
  state: "已交付" | "生成中" | "待审批" | "生成失败";
  progress: number;
};

export type WorkbenchData = {
  project: Project;
  projects: Project[];
  user: { id: string; name: string; initial: string };
  data_cutoff: string;
  headline: { greeting: string; new_changes: number; priority_changes: number };
  daily_brief: {
    title: string;
    summary: string;
    evidence_count: number;
    confidence: number;
    impact_level: ImpactLevel;
    insight_id: number | null;
  };
  metrics: Metric[];
  trend: TrendData;
  source_health: {
    score: number;
    total: number;
    normal: number;
    abnormal: number;
    disabled: number;
    last_sync: string;
  };
  insights: Insight[];
  review_queue: { total: number; items: ReviewItem[] };
  reports: Report[];
};

export type ReportTemplateRecord = {
  id: string;
  name: string;
  report_type: "daily" | "weekly" | "compare" | "flash" | "strategy" | "executive";
  description: string;
  sections: string[];
  language: "zh-CN" | "en-US";
  audience: string;
  approval_required: boolean;
  builtin: boolean;
  updated_at: string;
};

export type ReportRecord = {
  id: string;
  project_id: string;
  template_id: string | null;
  title: string;
  report_type: string;
  version: number;
  time_window: string;
  language: string;
  audience: string;
  state: "已交付" | "生成中" | "待审批" | "生成失败";
  progress: number;
  approval_status: "not_required" | "pending" | "approved" | "rejected";
  evidence_count: number;
  source_count: number;
  confidence: number;
  data_cutoff: string | null;
  sections: Record<string, unknown>;
  failure_reason: string | null;
  approved_by: string | null;
  approved_at: string | null;
  delivered_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ReportSubscriptionRecord = {
  id: string;
  project_id: string;
  name: string;
  template_id: string;
  cadence: "daily" | "weekly" | "monthly" | "event";
  delivery_time: string;
  timezone: string;
  channels: Array<"in_app" | "email" | "enterprise_message">;
  recipients: string[];
  enabled: boolean;
  next_run_at: string | null;
  last_delivery_status: "success" | "failed" | "pending" | "never";
  updated_at: string;
};

export type AlertRuleRecord = {
  id: string;
  project_id: string;
  name: string;
  competitors: string[];
  keywords: string[];
  event_types: string[];
  min_impact: "low" | "medium" | "high";
  min_confidence: number;
  change_threshold: number;
  quiet_minutes: number;
  escalation_minutes: number;
  channels: Array<"in_app" | "email" | "enterprise_message">;
  enabled: boolean;
  last_triggered_at: string | null;
  updated_at: string;
};

export type AlertRecord = {
  id: string;
  project_id: string;
  rule_id: string | null;
  insight_id: number | null;
  title: string;
  summary: string;
  competitor: string;
  event_type: string;
  impact: "low" | "medium" | "high" | "critical";
  confidence: number;
  source_count: number;
  status: "new" | "acknowledged" | "resolved" | "suppressed";
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
  quiet_until: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
};

export type ReportingDashboard = {
  project_id: string;
  generated_at: string;
  summary: {
    delivered: number;
    generating: number;
    pending_approval: number;
    active_alerts: number;
    critical_alerts: number;
    on_time_rate: number;
    evidence_coverage: number;
  };
  templates: ReportTemplateRecord[];
  reports: ReportRecord[];
  subscriptions: ReportSubscriptionRecord[];
  alert_rules: AlertRuleRecord[];
  alerts: AlertRecord[];
};

export type AdminDashboard = {
  generated_at: string;
  organization: {
    id: string;
    name: string;
    domain: string;
    plan: string;
    sso_enforced: boolean;
    mfa_required: boolean;
    session_timeout_minutes: number;
    status: "active" | "suspended";
  };
  summary: {
    availability: number;
    task_success_rate: number;
    report_success_rate: number;
    active_incidents: number;
    rpo_minutes: number;
    rto_hours: number;
    monthly_cost: number;
    budget_utilization: number;
  };
  roles: Array<{ id: string; name: string; description: string; permissions: string[]; system: boolean }>;
  users: Array<{
    id: string;
    name: string;
    initial: string;
    email: string;
    role_id: string;
    role_name: string;
    status: "active" | "invited" | "suspended";
    mfa_enabled: boolean;
    export_permission: "none" | "standard" | "sensitive";
    project_scopes: string[];
    data_domains: string[];
    last_login_at: string | null;
  }>;
  models: Array<{
    id: string;
    provider: string;
    model_name: string;
    version: string;
    routing_class: "standard" | "private" | "restricted";
    status: "active" | "degraded" | "disabled";
    allowed_data_classifications: string[];
    monthly_budget: number;
    spent_amount: number;
    quota_warning_percent: number;
    fallback_model: string | null;
    latency_p95_ms: number;
    success_rate: number;
    updated_at: string;
  }>;
  evaluations: Array<{
    id: string;
    model_config_id: string;
    dataset_name: string;
    accuracy: number;
    citation_completeness: number;
    refusal_rate: number;
    latency_p95_ms: number;
    cost_per_run: number;
    sample_size: number;
    evaluated_at: string;
  }>;
  policies: Array<{
    id: string;
    key: string;
    name: string;
    category: "identity" | "data" | "export" | "retention" | "model";
    value: Record<string, unknown>;
    status: "enforced" | "monitoring" | "disabled";
    updated_by: string | null;
    updated_at: string;
  }>;
  audit_events: Array<{
    id: number;
    actor_id: string | null;
    actor_name: string;
    action: string;
    entity_type: string;
    entity_id: string;
    detail: Record<string, unknown>;
    created_at: string;
  }>;
  services: Array<{
    id: string;
    name: string;
    status: "healthy" | "degraded" | "outage" | "maintenance";
    uptime: number;
    latency_p95_ms: number;
    detail: string;
    last_checked_at: string;
  }>;
  incidents: Array<{
    id: string;
    title: string;
    severity: "sev1" | "sev2" | "sev3" | "sev4";
    status: "open" | "acknowledged" | "monitoring" | "resolved";
    owner: string;
    started_at: string;
    updated_at: string;
    detail: string;
  }>;
  backups: Array<{
    id: string;
    backup_type: "full" | "incremental";
    status: "running" | "succeeded" | "failed";
    rpo_minutes: number;
    size_bytes: number;
    started_at: string;
    completed_at: string | null;
    restore_verified: boolean;
  }>;
};

export type ProjectCreatePayload = {
  name: string;
  template: "daily" | "compare" | "strategy";
  regions: Array<"cn" | "global" | "jp" | "sea">;
};

export type SourceCheck = {
  key: "connectivity" | "compliance" | "rate_limit" | "field_availability";
  label: string;
  status: "passed" | "failed" | "pending" | "not_applicable";
  message: string;
  checked_at: string | null;
};

export type DataSource = {
  id: string;
  project_id: string;
  name: string;
  source_type: SourceType;
  endpoint: string;
  subject: string;
  access_method: "public" | "api_key" | "oauth2" | "secret_ref" | "upload";
  crawl_strategy: string;
  regions: string[];
  authorization_basis: string;
  authorization_status: "pending" | "approved" | "expired" | "rejected";
  data_classification: "public" | "internal" | "restricted";
  retention_days: number;
  schedule_frequency: "manual" | "15m" | "hourly" | "6h" | "daily" | "weekly";
  rate_limit_per_minute: number;
  concurrency_limit: number;
  task_timeout_seconds: number;
  max_attempts: number;
  retry_backoff_seconds: number;
  priority: number;
  circuit_state: "closed" | "open" | "half_open";
  circuit_open_until: string | null;
  credential_masked: string | null;
  credential_expires_at: string | null;
  fields_available: string[];
  collection_config: Record<string, unknown>;
  robots_acknowledged: boolean;
  terms_acknowledged: boolean;
  enabled: boolean;
  status: SourceStatus;
  health_score: number;
  health: {
    success_rate: number;
    consecutive_failures: number;
    average_latency_ms: number;
    freshness_minutes: number;
    content_change_rate: number;
    parser_completeness: number;
  };
  checks: SourceCheck[];
  activation_ready: boolean;
  last_checked_at: string | null;
  last_collected_at: string | null;
  last_success_at: string | null;
  next_run_at: string | null;
  archived_at: string | null;
  archived_by: string | null;
  created_at: string;
  updated_at: string;
};

export type SourceCreatePayload = {
  project_id: string;
  name: string;
  source_type: SourceType;
  endpoint: string;
  subject: string;
  access_method: DataSource["access_method"];
  crawl_strategy: string;
  regions: string[];
  authorization_basis: string;
  authorization_status: DataSource["authorization_status"];
  data_classification: DataSource["data_classification"];
  retention_days: number;
  schedule_frequency: DataSource["schedule_frequency"];
  rate_limit_per_minute: number;
  concurrency_limit?: number;
  task_timeout_seconds?: number;
  max_attempts?: number;
  retry_backoff_seconds?: number;
  priority?: number;
  credential_ref?: string | null;
  credential_expires_at?: string | null;
  fields_available: string[];
  collection_config: Record<string, unknown>;
  robots_acknowledged: boolean;
  terms_acknowledged: boolean;
};

export type SourceUpdatePayload = Partial<Omit<SourceCreatePayload, "project_id">>;

export type SourceListResponse = {
  project_id: string;
  summary: {
    total: number;
    enabled: number;
    needs_attention: number;
    disabled: number;
    expiring_credentials: number;
    average_health: number;
  };
  items: DataSource[];
};

export type CollectionRunStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "partial"
  | "failed"
  | "cancelled"
  | "manual_review";

export type CollectionRun = {
  id: string;
  source_id: string;
  project_id: string;
  source_name: string;
  source_type: SourceType;
  trigger_type: "manual" | "scheduled" | "event" | "api" | "upload" | "retry" | "recovery";
  status: CollectionRunStatus;
  priority: number;
  attempt: number;
  max_attempts: number;
  timeout_seconds: number;
  backoff_seconds: number;
  scheduled_for: string | null;
  available_at: string | null;
  next_retry_at: string | null;
  retry_delays: number[];
  retry_of: string | null;
  recovery_of: string | null;
  recovered_from_restart: boolean;
  workflow_version: string;
  workflow_steps: WorkflowStep[];
  items_discovered: number;
  documents_created: number;
  documents_updated: number;
  duplicates_skipped: number;
  error_type: string | null;
  error_message: string | null;
  request_summary: string | null;
  parser_steps: string[];
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type WorkflowStep = {
  key: string;
  name: string;
  agent: string;
  order: number;
  status: "pending" | "running" | "waiting_retry" | "succeeded" | "failed" | "skipped";
  attempt: number;
  max_attempts: number;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  error_type: string | null;
  error_message: string | null;
  output_summary: string | null;
};

export type SourceSchedulePayload = {
  schedule_frequency: DataSource["schedule_frequency"];
  rate_limit_per_minute: number;
  concurrency_limit: number;
  task_timeout_seconds: number;
  max_attempts: number;
  retry_backoff_seconds: number;
  priority: number;
};

export type OrchestrationDashboard = {
  project_id: string;
  generated_at: string;
  summary: {
    scheduled_sources: number;
    queued: number;
    running: number;
    exceptions: number;
    success_rate_24h: number;
    recovered_24h: number;
  };
  workflow_nodes: Array<{
    key: string;
    name: string;
    agent: string;
    description: string;
  }>;
  schedules: Array<{
    source: DataSource;
    active_runs: number;
    last_run_status: CollectionRunStatus | null;
  }>;
  runs: CollectionRun[];
  exceptions: CollectionRun[];
};

export type OrchestrationActionResult = {
  queued: CollectionRun[];
  skipped: Record<string, string>;
};

export type CollectionRunListResponse = {
  project_id: string;
  summary: { total: number; running: number; succeeded: number; failed: number };
  items: CollectionRun[];
};

export type CollectionDocument = {
  id: string;
  project_id: string;
  source_id: string;
  source_name: string;
  source_type: SourceType;
  run_id: string;
  canonical_url: string;
  title: string;
  published_at: string | null;
  collected_at: string;
  language: string | null;
  content_type: string;
  content_hash: string;
  readable_excerpt: string;
  word_count: number;
  version: number;
  is_latest: boolean;
};

export type CollectionDocumentDetail = CollectionDocument & {
  readable_text: string;
  metadata: Record<string, unknown>;
  structured_fields: Record<string, unknown>;
  parser_version: string;
  previous_document_id: string | null;
};

export type CollectionDocumentListResponse = {
  project_id: string;
  summary: { total: number; latest: number; sources: number };
  items: CollectionDocument[];
};

export type ProcessingStatus = "pending" | "processing" | "completed" | "review_required" | "failed";
export type OcrStatus = "not_required" | "completed" | "unavailable" | "failed";
export type ProcessingOptions = {
  extract_body: boolean;
  denoise: boolean;
  deduplicate: boolean;
  detect_language: boolean;
  ocr: boolean;
  extract_entities: boolean;
  extract_events: boolean;
};

export type EntityMention = {
  id: string;
  type: "company" | "brand" | "product" | "person" | "version" | "price" | "location" | "date" | "feature";
  text: string;
  normalized: string;
  start: number;
  end: number;
  confidence: number;
  method: string;
};

export type ExtractedEvent = {
  id: string;
  type: "release" | "price_increase" | "price_decrease" | "partnership" | "funding" | "acquisition" | "market_entry" | "market_exit" | "feature_add" | "feature_remove" | "hiring";
  label: string;
  subject: string | null;
  object: string | null;
  occurred_at: string | null;
  impact_level: "high" | "medium" | "low";
  confidence: number;
  evidence_text: string;
  start: number;
  end: number;
  method: string;
};

export type ProcessingStep = {
  key: string;
  label: string;
  status: "completed" | "skipped" | "warning" | "failed";
  duration_ms: number;
  summary: string;
};

export type ProcessingDocument = {
  document_id: string;
  project_id: string;
  source_id: string;
  source_name: string;
  title: string;
  collected_at: string;
  content_type: string;
  status: ProcessingStatus;
  quality_score: number;
  language: string | null;
  language_confidence: number;
  ocr_status: OcrStatus;
  duplicate: {
    type: "none" | "exact" | "near";
    document_id: string | null;
    title: string | null;
    source_name: string | null;
    similarity: number;
    cluster_id: string;
  };
  entity_count: number;
  event_count: number;
  noise_removed_lines: number;
  needs_review: boolean;
  review_reasons: string[];
  processed_at: string | null;
};

export type ProcessingDocumentDetail = ProcessingDocument & {
  original_excerpt: string;
  clean_text: string;
  body_extraction_method: string;
  entities: EntityMention[];
  events: ExtractedEvent[];
  steps: ProcessingStep[];
  processor_version: string;
  error_message: string | null;
};

export type ProcessingOverview = {
  project_id: string;
  generated_at: string;
  summary: {
    total: number;
    processed: number;
    pending: number;
    review_required: number;
    failed: number;
    duplicates: number;
    entities: number;
    events: number;
    ocr_completed: number;
  };
  items: ProcessingDocument[];
};

export type KnowledgeItemType = "fact" | "entity" | "event" | "insight";
export type KnowledgeReviewStatus = "verified" | "review_required" | "conflict";
export type KnowledgeValidityStatus = "active" | "at_risk" | "expired" | "archived";

export type KnowledgeCollection = {
  id: string;
  project_id: string;
  name: string;
  description: string;
  color: string;
  item_count: number;
  updated_at: string;
};

export type KnowledgeItem = {
  id: string;
  project_id: string;
  document_id: string | null;
  source_id: string | null;
  item_type: KnowledgeItemType;
  title: string;
  summary: string;
  subject: string | null;
  category: string;
  language: string | null;
  tags: string[];
  confidence: number;
  quality_score: number;
  review_status: KnowledgeReviewStatus;
  validity_status: KnowledgeValidityStatus;
  source_count: number;
  source_name: string;
  source_url: string;
  evidence_excerpt: string;
  extraction_method: string;
  published_at: string | null;
  updated_at: string;
  collection_count: number;
};

export type KnowledgeItemDetail = KnowledgeItem & {
  content: string;
  source: {
    id: string | null;
    name: string;
    url: string;
    authorization_status: DataSource["authorization_status"] | null;
    retention_days: number | null;
  };
  document: {
    id: string;
    title: string;
    version: number;
    content_hash: string;
    parser_version: string;
    collected_at: string;
    published_at: string | null;
    raw_available: boolean;
  } | null;
  evidence: {
    excerpt: string;
    start: number | null;
    end: number | null;
    extraction_method: string;
  };
  collections: KnowledgeCollection[];
  revisions: Array<{
    version: number;
    action: string;
    snapshot: Record<string, unknown>;
    note: string;
    changed_by: string | null;
    created_at: string;
  }>;
};

export type KnowledgeOverview = {
  project_id: string;
  generated_at: string;
  summary: {
    knowledge_items: number;
    verified: number;
    review_required: number;
    conflicts: number;
    collections: number;
    sources: number;
    evidence_coverage: number;
    latest_update: string | null;
  };
  storage: {
    raw_documents: number;
    document_versions: number;
    processed_documents: number;
    storage_bytes: number;
  };
  type_counts: Record<KnowledgeItemType, number>;
  items: KnowledgeItem[];
  collections: KnowledgeCollection[];
};

export const defaultProcessingOptions: ProcessingOptions = {
  extract_body: true,
  denoise: true,
  deduplicate: true,
  detect_language: true,
  ocr: true,
  extract_entities: true,
  extract_events: true,
};

export type SearchResponse = {
  query: string;
  total: number;
  items: Array<{
    kind: "project" | "insight" | "report" | "evidence" | "source" | "knowledge";
    id: string;
    title: string;
    subtitle: string;
  }>;
};

export type RAGFilters = {
  competitors?: string[];
  item_types?: KnowledgeItemType[];
  categories?: string[];
  review_statuses?: KnowledgeReviewStatus[];
  collection_id?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  include_at_risk?: boolean;
  top_k?: number;
};

export type RAGCitation = {
  id: number;
  item_id: string;
  title: string;
  subject: string;
  item_type: KnowledgeItemType;
  category: string;
  summary: string;
  evidence_excerpt: string;
  source_name: string;
  source_url: string;
  published_at: string | null;
  confidence: number;
  relevance: number;
  review_status: KnowledgeReviewStatus;
  validity_status: KnowledgeValidityStatus;
};

export type RAGResponse = {
  id: string;
  project_id: string;
  question: string;
  answer: string;
  answer_type: "grounded" | "insufficient";
  confidence: number;
  data_cutoff: string;
  citations: RAGCitation[];
  trace: {
    query_terms: string[];
    candidate_count: number;
    retrieved_count: number;
    generation_mode: "extractive_grounded";
    stages: Array<{
      key: string;
      label: string;
      status: "completed" | "warning";
      detail: string;
    }>;
  };
  notices: string[];
  created_at: string;
};

export type CompetitiveDimension =
  | "capability"
  | "pricing"
  | "governance"
  | "release"
  | "market"
  | "reputation";

export type ComparisonCell = {
  competitor: string;
  dimension: CompetitiveDimension;
  dimension_label: string;
  status: "evidence" | "limited" | "conflict" | "missing";
  summary: string;
  confidence: number;
  evidence_count: number;
  citation_ids: number[];
};

export type CompetitiveAnalysisResult = {
  id: string;
  project_id: string;
  title: string;
  status: "completed" | "partial";
  competitors: string[];
  dimensions: CompetitiveDimension[];
  range_key: "7d" | "30d" | "90d" | "all";
  data_cutoff: string;
  sample_size: number;
  source_count: number;
  coverage_rate: number;
  executive_summary: string;
  matrix: ComparisonCell[];
  findings: Array<{
    type: "fact" | "inference";
    title: string;
    detail: string;
    impact_level: "high" | "medium" | "low";
    competitors: string[];
    citation_ids: number[];
  }>;
  swot: Array<{
    competitor: string;
    strengths: Array<{ text: string; citation_ids: number[] }>;
    weaknesses: Array<{ text: string; citation_ids: number[] }>;
    opportunities: Array<{ text: string; citation_ids: number[] }>;
    threats: Array<{ text: string; citation_ids: number[] }>;
  }>;
  recommendations: Array<{
    applicable_to: string;
    action: string;
    basis: string;
    expected_impact: string;
    risk: string;
    validation: string;
    citation_ids: number[];
  }>;
  citations: RAGCitation[];
  agent_steps: Array<{
    key: string;
    label: string;
    agent: string;
    status: "completed" | "warning";
    detail: string;
    evidence_count: number;
  }>;
  notices: string[];
  created_at: string;
  completed_at: string;
};

export type CompetitiveAnalysisOverview = {
  project_id: string;
  suggested_competitors: string[];
  dimensions: Record<CompetitiveDimension, string>;
  runs: Array<{
    id: string;
    title: string;
    status: "completed" | "partial";
    competitors: string[];
    dimensions: CompetitiveDimension[];
    range_key: "7d" | "30d" | "90d" | "all";
    coverage_rate: number;
    sample_size: number;
    created_at: string;
  }>;
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");
const AUTH_TOKEN = process.env.NEXT_PUBLIC_AUTH_TOKEN?.trim();

function applyAuthHeader(headers: Headers) {
  if (AUTH_TOKEN && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${AUTH_TOKEN}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  applyAuthHeader(headers);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let detail = `请求失败（${response.status}）`;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

async function requestBlob(path: string): Promise<Blob> {
  const headers = new Headers();
  applyAuthHeader(headers);
  const response = await fetch(`${API_BASE_URL}${path}`, { headers });
  if (!response.ok) {
    let detail = `导出失败（${response.status}）`;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      // Keep the status-based message for non-JSON responses.
    }
    throw new Error(detail);
  }
  return response.blob();
}

export function fetchWorkbench(projectId?: string, range: RangeKey = "7d") {
  const params = new URLSearchParams({ range });
  if (projectId) params.set("project_id", projectId);
  return request<WorkbenchData>(`/api/v1/workbench?${params.toString()}`);
}

export function createProject(payload: ProjectCreatePayload) {
  return request<Project>("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchInsight(insightId: number) {
  return request<InsightDetail>(`/api/v1/insights/${insightId}`);
}

export function claimReview(reviewId: number) {
  return request<{ item: ReviewItem; pending_count: number }>(
    `/api/v1/reviews/${reviewId}/claim`,
    { method: "POST" },
  );
}

export function generateReport(projectId: string) {
  return request<Report>("/api/v1/reports/generate", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, template: "daily" }),
  });
}

export function fetchReportingDashboard(projectId: string) {
  const params = new URLSearchParams({ project_id: projectId });
  return request<ReportingDashboard>(`/api/v1/reports?${params.toString()}`);
}

export function fetchReportDetail(reportId: string) {
  return request<ReportRecord>(`/api/v1/reports/${reportId}`);
}

export function generateConfiguredReport(payload: {
  project_id: string;
  template: ReportTemplateRecord["report_type"];
  template_id?: string;
  time_window: "24h" | "7d" | "30d" | "90d";
  language: "zh-CN" | "en-US";
  audience: "analyst" | "product" | "management" | "general";
  length: "brief" | "standard" | "detailed";
  approval_required?: boolean;
}) {
  return request<Report>("/api/v1/reports/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function approveReport(reportId: string, decision: "approve" | "reject", note = "") {
  return request<ReportRecord>(`/api/v1/reports/${reportId}/approval`, {
    method: "POST",
    body: JSON.stringify({ decision, note }),
  });
}

export function downloadReport(reportId: string, format: "docx" | "pdf") {
  const params = new URLSearchParams({ format });
  return requestBlob(`/api/v1/reports/${reportId}/export?${params.toString()}`);
}

export function updateReportSubscription(subscriptionId: string, enabled: boolean) {
  return request<ReportSubscriptionRecord>(`/api/v1/report-subscriptions/${subscriptionId}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
}

export function createAlertRule(payload: {
  project_id: string;
  name: string;
  competitors: string[];
  keywords: string[];
  event_types: string[];
  min_impact: "low" | "medium" | "high";
  min_confidence: number;
  change_threshold: number;
  quiet_minutes: number;
  escalation_minutes: number;
  channels: Array<"in_app" | "email" | "enterprise_message">;
  enabled: boolean;
}) {
  return request<AlertRuleRecord>("/api/v1/alert-rules", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAlertRule(
  ruleId: string,
  payload: Partial<Pick<AlertRuleRecord, "name" | "min_impact" | "min_confidence" | "quiet_minutes" | "escalation_minutes" | "channels" | "enabled">>,
) {
  return request<AlertRuleRecord>(`/api/v1/alert-rules/${ruleId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function actOnAlert(alertId: string, action: "acknowledge" | "resolve", note = "") {
  return request<AlertRecord>(`/api/v1/alerts/${alertId}/actions`, {
    method: "POST",
    body: JSON.stringify({ action, note }),
  });
}

export function fetchAdminDashboard() {
  return request<AdminDashboard>("/api/v1/admin");
}

export function updateAdminUserAccess(
  userId: string,
  payload: Partial<Pick<AdminDashboard["users"][number], "role_id" | "status" | "mfa_enabled" | "export_permission" | "project_scopes" | "data_domains">>,
) {
  return request<AdminDashboard["users"][number]>(`/api/v1/admin/users/${userId}/access`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function updateAdminModel(
  modelId: string,
  payload: Partial<Pick<AdminDashboard["models"][number], "status" | "routing_class" | "allowed_data_classifications" | "monthly_budget" | "quota_warning_percent" | "fallback_model">>,
) {
  return request<AdminDashboard["models"][number]>(`/api/v1/admin/models/${modelId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function updateAdminPolicy(
  policyId: string,
  payload: Partial<Pick<AdminDashboard["policies"][number], "value" | "status">>,
) {
  return request<AdminDashboard["policies"][number]>(`/api/v1/admin/policies/${policyId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function actOnIncident(incidentId: string, action: "acknowledge" | "resolve", note = "") {
  return request<AdminDashboard["incidents"][number]>(`/api/v1/admin/incidents/${incidentId}/actions`, {
    method: "POST",
    body: JSON.stringify({ action, note }),
  });
}

export function runAdminBackup() {
  return request<{ backup: AdminDashboard["backups"][number]; message: string }>("/api/v1/admin/backups", {
    method: "POST",
  });
}

export function searchWorkbench(query: string, projectId?: string) {
  const params = new URLSearchParams({ q: query });
  if (projectId) params.set("project_id", projectId);
  return request<SearchResponse>(`/api/v1/search?${params.toString()}`);
}

export function queryRAG(
  projectId: string,
  question: string,
  filters: RAGFilters = {},
) {
  return request<RAGResponse>("/api/v1/rag/query", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, question, filters }),
  });
}

export function fetchCompetitiveAnalysisOverview(projectId: string) {
  const params = new URLSearchParams({ project_id: projectId });
  return request<CompetitiveAnalysisOverview>(
    `/api/v1/competitive-analysis?${params.toString()}`,
  );
}

export function runCompetitiveAnalysis(payload: {
  project_id: string;
  competitors: string[];
  dimensions: CompetitiveDimension[];
  range_key: "7d" | "30d" | "90d" | "all";
}) {
  return request<CompetitiveAnalysisResult>("/api/v1/competitive-analysis/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchCompetitiveAnalysis(runId: string) {
  return request<CompetitiveAnalysisResult>(`/api/v1/competitive-analysis/runs/${runId}`);
}

export function fetchSources(
  projectId: string,
  filters: { status?: SourceStatus; sourceType?: SourceType; query?: string } = {},
) {
  const params = new URLSearchParams({ project_id: projectId });
  if (filters.status) params.set("status", filters.status);
  if (filters.sourceType) params.set("source_type", filters.sourceType);
  if (filters.query) params.set("q", filters.query);
  return request<SourceListResponse>(`/api/v1/sources?${params.toString()}`);
}

export function createSource(payload: SourceCreatePayload) {
  return request<DataSource>("/api/v1/sources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateSource(sourceId: string, payload: SourceUpdatePayload) {
  return request<DataSource>(`/api/v1/sources/${sourceId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function runSourceChecks(sourceId: string) {
  return request<{ item: DataSource; message: string }>(`/api/v1/sources/${sourceId}/checks`, {
    method: "POST",
  });
}

export function setSourceStatus(sourceId: string, enabled: boolean) {
  return request<{ item: DataSource; message: string }>(`/api/v1/sources/${sourceId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
}

export function runSourceNow(sourceId: string) {
  return request<CollectionRun>(
    `/api/v1/sources/${sourceId}/runs`,
    { method: "POST" },
  );
}

export function fetchCollectionRuns(
  projectId: string,
  filters: { sourceId?: string; status?: CollectionRunStatus } = {},
) {
  const params = new URLSearchParams({ project_id: projectId });
  if (filters.sourceId) params.set("source_id", filters.sourceId);
  if (filters.status) params.set("status", filters.status);
  return request<CollectionRunListResponse>(`/api/v1/collection/runs?${params.toString()}`);
}

export function fetchCollectionRun(runId: string) {
  return request<CollectionRun>(`/api/v1/collection/runs/${runId}`);
}

export function retryCollectionRun(runId: string) {
  return request<CollectionRun>(`/api/v1/collection/runs/${runId}/retry`, { method: "POST" });
}

export function cancelCollectionRun(runId: string) {
  return request<CollectionRun>(`/api/v1/collection/runs/${runId}/cancel`, { method: "POST" });
}

export function fetchOrchestration(projectId: string) {
  const params = new URLSearchParams({ project_id: projectId });
  return request<OrchestrationDashboard>(`/api/v1/orchestration?${params.toString()}`);
}

export function updateSourceSchedule(sourceId: string, payload: SourceSchedulePayload) {
  return request<DataSource>(`/api/v1/sources/${sourceId}/schedule`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function triggerOrchestrationRun(
  sourceId: string,
  triggerType: "manual" | "event" | "api" = "manual",
) {
  return request<CollectionRun>("/api/v1/orchestration/triggers", {
    method: "POST",
    body: JSON.stringify({ source_id: sourceId, trigger_type: triggerType }),
  });
}

export function bulkRetryOrchestrationRuns(runIds: string[]) {
  return request<OrchestrationActionResult>("/api/v1/orchestration/runs/retry", {
    method: "POST",
    body: JSON.stringify({ run_ids: runIds }),
  });
}

export function recoverOrchestrationRuns(projectId: string, runIds: string[] = []) {
  return request<OrchestrationActionResult>("/api/v1/orchestration/recover", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, run_ids: runIds }),
  });
}

export function fetchCollectionDocuments(
  projectId: string,
  filters: { sourceId?: string; query?: string; latestOnly?: boolean } = {},
) {
  const params = new URLSearchParams({
    project_id: projectId,
    latest_only: String(filters.latestOnly ?? true),
  });
  if (filters.sourceId) params.set("source_id", filters.sourceId);
  if (filters.query) params.set("q", filters.query);
  return request<CollectionDocumentListResponse>(`/api/v1/collection/documents?${params.toString()}`);
}

export function fetchCollectionDocument(documentId: string) {
  return request<CollectionDocumentDetail>(`/api/v1/collection/documents/${documentId}`);
}

export function collectionDocumentRawUrl(documentId: string) {
  return `${API_BASE_URL}/api/v1/collection/documents/${documentId}/raw`;
}

export function fetchProcessingOverview(
  projectId: string,
  filters: { status?: ProcessingStatus; query?: string } = {},
) {
  const params = new URLSearchParams({ project_id: projectId });
  if (filters.status) params.set("status", filters.status);
  if (filters.query) params.set("q", filters.query);
  return request<ProcessingOverview>(`/api/v1/processing?${params.toString()}`);
}

export function fetchProcessingDocument(documentId: string) {
  return request<ProcessingDocumentDetail>(`/api/v1/processing/documents/${documentId}`);
}

export function runProcessingBatch(
  projectId: string,
  documentIds: string[] = [],
  options: ProcessingOptions = defaultProcessingOptions,
) {
  return request<{
    requested: number;
    completed: number;
    review_required: number;
    failed: number;
    items: ProcessingDocument[];
  }>("/api/v1/processing/jobs", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, document_ids: documentIds, options }),
  });
}

export function runProcessingDocument(
  documentId: string,
  options: ProcessingOptions = defaultProcessingOptions,
) {
  return request<ProcessingDocumentDetail>(`/api/v1/processing/documents/${documentId}/run`, {
    method: "POST",
    body: JSON.stringify(options),
  });
}

export function fetchKnowledgeOverview(
  projectId: string,
  filters: {
    query?: string;
    itemType?: KnowledgeItemType;
    reviewStatus?: KnowledgeReviewStatus;
    sourceId?: string;
    collectionId?: string;
  } = {},
) {
  const params = new URLSearchParams({ project_id: projectId });
  if (filters.query) params.set("q", filters.query);
  if (filters.itemType) params.set("item_type", filters.itemType);
  if (filters.reviewStatus) params.set("review_status", filters.reviewStatus);
  if (filters.sourceId) params.set("source_id", filters.sourceId);
  if (filters.collectionId) params.set("collection_id", filters.collectionId);
  return request<KnowledgeOverview>(`/api/v1/knowledge?${params.toString()}`);
}

export function fetchKnowledgeItem(itemId: string) {
  return request<KnowledgeItemDetail>(`/api/v1/knowledge/items/${itemId}`);
}

export function reviewKnowledgeItem(
  itemId: string,
  reviewStatus: KnowledgeReviewStatus,
  note = "",
) {
  return request<KnowledgeItemDetail>(`/api/v1/knowledge/items/${itemId}/review`, {
    method: "PATCH",
    body: JSON.stringify({ review_status: reviewStatus, note }),
  });
}

export function createKnowledgeCollection(payload: {
  project_id: string;
  name: string;
  description: string;
  color: string;
}) {
  return request<KnowledgeCollection>("/api/v1/knowledge/collections", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function addKnowledgeItemToCollection(collectionId: string, itemId: string) {
  return request<KnowledgeCollection>(
    `/api/v1/knowledge/collections/${collectionId}/items/${itemId}`,
    { method: "POST" },
  );
}

export function removeKnowledgeItemFromCollection(collectionId: string, itemId: string) {
  return request<KnowledgeCollection>(
    `/api/v1/knowledge/collections/${collectionId}/items/${itemId}`,
    { method: "DELETE" },
  );
}

export function uploadCollectionFile(payload: {
  projectId: string;
  name: string;
  subject: string;
  authorizationBasis: string;
  retentionDays: number;
  file: File;
}) {
  const form = new FormData();
  form.set("project_id", payload.projectId);
  form.set("name", payload.name);
  form.set("subject", payload.subject);
  form.set("authorization_basis", payload.authorizationBasis);
  form.set("retention_days", String(payload.retentionDays));
  form.set("file", payload.file);
  return request<{ source: DataSource; run: CollectionRun }>("/api/v1/collection/files", {
    method: "POST",
    body: form,
  });
}

export function rotateSourceCredential(
  sourceId: string,
  credentialRef: string,
  credentialExpiresAt?: string | null,
) {
  return request<{ item: DataSource; message: string }>(
    `/api/v1/sources/${sourceId}/credentials/rotate`,
    {
      method: "POST",
      body: JSON.stringify({
        credential_ref: credentialRef,
        credential_expires_at: credentialExpiresAt ?? null,
      }),
    },
  );
}

export function deleteSource(sourceId: string) {
  return request<{ id: string; archived: true; archived_at: string }>(`/api/v1/sources/${sourceId}`, {
    method: "DELETE",
  });
}
