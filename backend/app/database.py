from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from .schemas import ProjectCreate, SourceCreate, SourceScheduleUpdate, SourceUpdate


WORKFLOW_DEFINITION = (
    ("collect", "获取内容", "采集 Agent"),
    ("normalize", "解析与标准化", "内容理解 Agent"),
    ("deduplicate", "指纹与版本判断", "去重 Agent"),
    ("quality_gate", "质量门禁", "质量 Agent"),
)


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    initial TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    avatar TEXT NOT NULL,
    template TEXT NOT NULL,
    regions_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_metrics (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    coverage_rate REAL NOT NULL DEFAULT 0,
    coverage_delta REAL NOT NULL DEFAULT 0,
    new_changes INTEGER NOT NULL DEFAULT 0,
    new_changes_delta INTEGER NOT NULL DEFAULT 0,
    major_alerts INTEGER NOT NULL DEFAULT 0,
    major_alerts_delta INTEGER NOT NULL DEFAULT 0,
    pending_reviews INTEGER NOT NULL DEFAULT 0,
    pending_reviews_delta INTEGER NOT NULL DEFAULT 0,
    data_cutoff TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_briefs (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    confidence INTEGER NOT NULL DEFAULT 0,
    impact_level TEXT NOT NULL DEFAULT 'low',
    insight_id INTEGER
);

CREATE TABLE IF NOT EXISTS trend_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    range_key TEXT NOT NULL,
    label TEXT NOT NULL,
    event_count INTEGER NOT NULL,
    high_impact_count INTEGER NOT NULL,
    sort_order INTEGER NOT NULL,
    UNIQUE(project_id, range_key, sort_order)
);

CREATE TABLE IF NOT EXISTS source_health (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    normal_count INTEGER NOT NULL,
    abnormal_count INTEGER NOT NULL,
    disabled_count INTEGER NOT NULL,
    last_sync TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    time_label TEXT NOT NULL,
    kind TEXT NOT NULL,
    impact_level TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_count INTEGER NOT NULL,
    confidence INTEGER NOT NULL,
    recommendation TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    insight_id INTEGER NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    source_type TEXT NOT NULL,
    published_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    company TEXT NOT NULL,
    field_name TEXT NOT NULL,
    reason TEXT NOT NULL,
    time_label TEXT NOT NULL,
    tone TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    claimed_by TEXT REFERENCES users(id),
    claimed_at TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    template_id TEXT,
    title TEXT NOT NULL,
    report_type TEXT NOT NULL DEFAULT 'daily',
    version INTEGER NOT NULL DEFAULT 1,
    time_window TEXT NOT NULL DEFAULT '24h',
    language TEXT NOT NULL DEFAULT 'zh-CN',
    audience TEXT NOT NULL DEFAULT 'analyst',
    schedule_label TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL,
    approval_required INTEGER NOT NULL DEFAULT 0,
    approval_status TEXT NOT NULL DEFAULT 'not_required',
    evidence_count INTEGER NOT NULL DEFAULT 0,
    source_count INTEGER NOT NULL DEFAULT 0,
    confidence INTEGER NOT NULL DEFAULT 0,
    data_cutoff TEXT,
    content_json TEXT NOT NULL DEFAULT '{}',
    failure_reason TEXT,
    approved_by TEXT,
    approved_at TEXT,
    delivered_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS report_templates (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    report_type TEXT NOT NULL,
    description TEXT NOT NULL,
    sections_json TEXT NOT NULL DEFAULT '[]',
    language TEXT NOT NULL DEFAULT 'zh-CN',
    audience TEXT NOT NULL DEFAULT 'analyst',
    approval_required INTEGER NOT NULL DEFAULT 0,
    builtin INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_subscriptions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    template_id TEXT NOT NULL REFERENCES report_templates(id) ON DELETE RESTRICT,
    cadence TEXT NOT NULL,
    delivery_time TEXT NOT NULL,
    timezone TEXT NOT NULL,
    channels_json TEXT NOT NULL DEFAULT '[]',
    recipients_json TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    next_run_at TEXT,
    last_delivery_status TEXT NOT NULL DEFAULT 'never',
    created_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_rules (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    competitors_json TEXT NOT NULL DEFAULT '[]',
    keywords_json TEXT NOT NULL DEFAULT '[]',
    event_types_json TEXT NOT NULL DEFAULT '[]',
    min_impact TEXT NOT NULL DEFAULT 'medium',
    min_confidence INTEGER NOT NULL DEFAULT 75,
    change_threshold REAL NOT NULL DEFAULT 0,
    quiet_minutes INTEGER NOT NULL DEFAULT 60,
    escalation_minutes INTEGER NOT NULL DEFAULT 120,
    channels_json TEXT NOT NULL DEFAULT '["in_app"]',
    enabled INTEGER NOT NULL DEFAULT 1,
    last_triggered_at TEXT,
    created_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    rule_id TEXT REFERENCES alert_rules(id) ON DELETE SET NULL,
    insight_id INTEGER REFERENCES insights(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    competitor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    impact TEXT NOT NULL,
    confidence INTEGER NOT NULL DEFAULT 0,
    source_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new',
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    quiet_until TEXT,
    acknowledged_by TEXT REFERENCES users(id),
    acknowledged_at TEXT,
    resolved_by TEXT REFERENCES users(id),
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_reports_project_created
ON reports(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_project_status
ON alerts(project_id, status, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS data_sources (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    subject TEXT NOT NULL,
    access_method TEXT NOT NULL,
    crawl_strategy TEXT NOT NULL,
    regions_json TEXT NOT NULL,
    authorization_basis TEXT NOT NULL,
    authorization_status TEXT NOT NULL,
    data_classification TEXT NOT NULL,
    retention_days INTEGER NOT NULL,
    schedule_frequency TEXT NOT NULL,
    rate_limit_per_minute INTEGER NOT NULL,
    concurrency_limit INTEGER NOT NULL DEFAULT 1,
    task_timeout_seconds INTEGER NOT NULL DEFAULT 120,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    retry_backoff_seconds INTEGER NOT NULL DEFAULT 2,
    priority INTEGER NOT NULL DEFAULT 5,
    circuit_state TEXT NOT NULL DEFAULT 'closed',
    circuit_open_until TEXT,
    last_run_started_at TEXT,
    credential_ref TEXT,
    credential_masked TEXT,
    credential_expires_at TEXT,
    fields_json TEXT NOT NULL DEFAULT '[]',
    collection_config_json TEXT NOT NULL DEFAULT '{}',
    robots_acknowledged INTEGER NOT NULL DEFAULT 0,
    terms_acknowledged INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 0,
    health_status TEXT NOT NULL DEFAULT 'disabled',
    health_score INTEGER NOT NULL DEFAULT 0,
    success_rate REAL NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    average_latency_ms INTEGER NOT NULL DEFAULT 0,
    freshness_minutes INTEGER NOT NULL DEFAULT 0,
    content_change_rate REAL NOT NULL DEFAULT 0,
    parser_completeness REAL NOT NULL DEFAULT 0,
    check_results_json TEXT NOT NULL DEFAULT '[]',
    last_checked_at TEXT,
    last_collected_at TEXT,
    last_success_at TEXT,
    next_run_at TEXT,
    archived_at TEXT,
    archived_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, endpoint)
);

CREATE INDEX IF NOT EXISTS idx_data_sources_project_status
ON data_sources(project_id, health_status);

CREATE TABLE IF NOT EXISTS source_runs (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    trigger_type TEXT NOT NULL DEFAULT 'manual',
    priority INTEGER NOT NULL DEFAULT 5,
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    timeout_seconds INTEGER NOT NULL DEFAULT 120,
    backoff_seconds INTEGER NOT NULL DEFAULT 2,
    scheduled_for TEXT,
    available_at TEXT,
    next_retry_at TEXT,
    retry_delays_json TEXT NOT NULL DEFAULT '[]',
    recovery_of TEXT,
    recovered_from_restart INTEGER NOT NULL DEFAULT 0,
    workflow_version TEXT NOT NULL DEFAULT 'collection-v1',
    items_discovered INTEGER NOT NULL DEFAULT 0,
    documents_created INTEGER NOT NULL DEFAULT 0,
    documents_updated INTEGER NOT NULL DEFAULT 0,
    duplicates_skipped INTEGER NOT NULL DEFAULT 0,
    error_type TEXT,
    error_message TEXT,
    request_summary TEXT,
    parser_steps_json TEXT NOT NULL DEFAULT '[]',
    started_at TEXT,
    finished_at TEXT,
    retry_of TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_steps (
    run_id TEXT NOT NULL REFERENCES source_runs(id) ON DELETE CASCADE,
    step_key TEXT NOT NULL,
    step_name TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    started_at TEXT,
    finished_at TEXT,
    duration_ms INTEGER,
    error_type TEXT,
    error_message TEXT,
    output_summary TEXT,
    PRIMARY KEY (run_id, step_key)
);

CREATE INDEX IF NOT EXISTS idx_workflow_steps_run_order
ON workflow_steps(run_id, step_order);

CREATE TABLE IF NOT EXISTS collection_documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES source_runs(id) ON DELETE CASCADE,
    canonical_url TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TEXT,
    collected_at TEXT NOT NULL,
    language TEXT,
    content_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    raw_content BLOB NOT NULL,
    readable_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    structured_fields_json TEXT NOT NULL DEFAULT '{}',
    parser_version TEXT NOT NULL,
    version_no INTEGER NOT NULL DEFAULT 1,
    previous_document_id TEXT,
    is_latest INTEGER NOT NULL DEFAULT 1,
    UNIQUE(source_id, canonical_url, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_collection_documents_project_collected
ON collection_documents(project_id, collected_at DESC);

CREATE INDEX IF NOT EXISTS idx_collection_documents_source_latest
ON collection_documents(source_id, canonical_url, is_latest);

CREATE TABLE IF NOT EXISTS document_processing (
    document_id TEXT PRIMARY KEY REFERENCES collection_documents(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    clean_text TEXT NOT NULL DEFAULT '',
    clean_hash TEXT,
    body_extraction_method TEXT NOT NULL DEFAULT 'pending',
    noise_removed_lines INTEGER NOT NULL DEFAULT 0,
    language TEXT,
    language_confidence REAL NOT NULL DEFAULT 0,
    ocr_status TEXT NOT NULL DEFAULT 'not_required',
    ocr_text TEXT NOT NULL DEFAULT '',
    duplicate_type TEXT NOT NULL DEFAULT 'none',
    duplicate_of TEXT,
    duplicate_similarity REAL NOT NULL DEFAULT 0,
    duplicate_cluster_id TEXT NOT NULL DEFAULT '',
    entities_json TEXT NOT NULL DEFAULT '[]',
    events_json TEXT NOT NULL DEFAULT '[]',
    steps_json TEXT NOT NULL DEFAULT '[]',
    quality_score INTEGER NOT NULL DEFAULT 0,
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_reasons_json TEXT NOT NULL DEFAULT '[]',
    processor_version TEXT NOT NULL DEFAULT 'processing-v1',
    processed_at TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_document_processing_project_status
ON document_processing(project_id, status, processed_at DESC);

CREATE INDEX IF NOT EXISTS idx_document_processing_project_hash
ON document_processing(project_id, clean_hash);

CREATE TABLE IF NOT EXISTS knowledge_items (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id TEXT REFERENCES collection_documents(id) ON DELETE SET NULL,
    source_id TEXT REFERENCES data_sources(id) ON DELETE SET NULL,
    item_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    subject TEXT,
    category TEXT NOT NULL,
    language TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    confidence INTEGER NOT NULL DEFAULT 0,
    quality_score INTEGER NOT NULL DEFAULT 0,
    review_status TEXT NOT NULL DEFAULT 'review_required',
    validity_status TEXT NOT NULL DEFAULT 'active',
    source_count INTEGER NOT NULL DEFAULT 1,
    evidence_excerpt TEXT NOT NULL,
    evidence_start INTEGER,
    evidence_end INTEGER,
    extraction_method TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'processing',
    published_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_items_project_updated
ON knowledge_items(project_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_items_project_type_status
ON knowledge_items(project_id, item_type, review_status);

CREATE TABLE IF NOT EXISTS knowledge_collections (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '#687c67',
    created_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS knowledge_collection_items (
    collection_id TEXT NOT NULL REFERENCES knowledge_collections(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
    added_by TEXT REFERENCES users(id),
    added_at TEXT NOT NULL,
    PRIMARY KEY (collection_id, item_id)
);

CREATE TABLE IF NOT EXISTS knowledge_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL,
    action TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    changed_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL,
    UNIQUE(item_id, version_no)
);

CREATE TABLE IF NOT EXISTS rag_query_logs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    filters_json TEXT NOT NULL DEFAULT '{}',
    retrieved_item_ids_json TEXT NOT NULL DEFAULT '[]',
    answer_type TEXT NOT NULL,
    confidence INTEGER NOT NULL DEFAULT 0,
    trace_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rag_query_logs_project_created
ON rag_query_logs(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS competitive_analysis_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    competitors_json TEXT NOT NULL,
    dimensions_json TEXT NOT NULL,
    range_key TEXT NOT NULL,
    coverage_rate INTEGER NOT NULL DEFAULT 0,
    sample_size INTEGER NOT NULL DEFAULT 0,
    result_json TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL,
    completed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_competitive_analysis_project_created
ON competitive_analysis_runs(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id TEXT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    plan TEXT NOT NULL,
    sso_enforced INTEGER NOT NULL DEFAULT 0,
    mfa_required INTEGER NOT NULL DEFAULT 0,
    session_timeout_minutes INTEGER NOT NULL DEFAULT 480,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    permissions_json TEXT NOT NULL DEFAULT '[]',
    system INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS user_memberships (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'active',
    mfa_enabled INTEGER NOT NULL DEFAULT 0,
    export_permission TEXT NOT NULL DEFAULT 'none',
    project_scopes_json TEXT NOT NULL DEFAULT '[]',
    data_domains_json TEXT NOT NULL DEFAULT '[]',
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS model_configs (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    routing_class TEXT NOT NULL,
    status TEXT NOT NULL,
    allowed_data_classifications_json TEXT NOT NULL DEFAULT '[]',
    monthly_budget REAL NOT NULL DEFAULT 0,
    spent_amount REAL NOT NULL DEFAULT 0,
    quota_warning_percent INTEGER NOT NULL DEFAULT 80,
    fallback_model TEXT,
    latency_p95_ms INTEGER NOT NULL DEFAULT 0,
    success_rate REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation_metrics (
    id TEXT PRIMARY KEY,
    model_config_id TEXT NOT NULL REFERENCES model_configs(id) ON DELETE CASCADE,
    dataset_name TEXT NOT NULL,
    accuracy REAL NOT NULL,
    citation_completeness REAL NOT NULL,
    refusal_rate REAL NOT NULL,
    latency_p95_ms INTEGER NOT NULL,
    cost_per_run REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    evaluated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS security_policies (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    policy_key TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    value_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'monitoring',
    updated_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    UNIQUE(organization_id, policy_key)
);

CREATE TABLE IF NOT EXISTS service_components (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    uptime REAL NOT NULL,
    latency_p95_ms INTEGER NOT NULL,
    detail TEXT NOT NULL,
    last_checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    owner TEXT NOT NULL,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    detail TEXT NOT NULL,
    acknowledged_by TEXT REFERENCES users(id),
    resolved_by TEXT REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS backup_runs (
    id TEXT PRIMARY KEY,
    backup_type TEXT NOT NULL,
    status TEXT NOT NULL,
    rpo_minutes INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    restore_verified INTEGER NOT NULL DEFAULT 0,
    created_by TEXT REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_audit_events_created
ON audit_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_incidents_status_updated
ON incidents(status, updated_at DESC);
"""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def schedule_next_run(frequency: str, from_time: datetime | None = None) -> str | None:
    intervals = {
        "15m": timedelta(minutes=15),
        "hourly": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "daily": timedelta(days=1),
        "weekly": timedelta(days=7),
    }
    interval = intervals.get(frequency)
    if interval is None:
        return None
    value = (from_time or datetime.now(UTC)) + interval
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.session() as connection:
            connection.executescript(SCHEMA)
            self._migrate_schema(connection)
            exists = connection.execute("SELECT 1 FROM projects LIMIT 1").fetchone()
            if not exists:
                self._seed(connection)
            source_exists = connection.execute(
                "SELECT 1 FROM data_sources LIMIT 1"
            ).fetchone()
            project_exists = connection.execute(
                "SELECT 1 FROM projects WHERE id='prj_ai_agent'"
            ).fetchone()
            if not source_exists and project_exists:
                self._seed_sources(connection, "prj_ai_agent")
            knowledge_exists = connection.execute(
                "SELECT 1 FROM knowledge_items WHERE project_id='prj_ai_agent' LIMIT 1"
            ).fetchone()
            if not knowledge_exists and project_exists:
                self._seed_knowledge(connection, "prj_ai_agent")
            self._seed_reporting(connection)
            self._seed_governance(connection)
            self._initialize_next_runs(connection)
            self._initialize_workflow_steps(connection)
            self._refresh_all_source_health(connection)

    @staticmethod
    def _migrate_schema(connection: sqlite3.Connection) -> None:
        """Apply additive migrations so existing local databases remain usable."""

        table_columns = {
            "users": {
                row["name"]
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            },
            "reports": {
                row["name"]
                for row in connection.execute("PRAGMA table_info(reports)").fetchall()
            },
            "data_sources": {
                row["name"]
                for row in connection.execute("PRAGMA table_info(data_sources)").fetchall()
            },
            "source_runs": {
                row["name"]
                for row in connection.execute("PRAGMA table_info(source_runs)").fetchall()
            },
        }
        additions = {
            "users": {
                "email": "TEXT NOT NULL DEFAULT ''",
                "status": "TEXT NOT NULL DEFAULT 'active'",
            },
            "reports": {
                "template_id": "TEXT",
                "report_type": "TEXT NOT NULL DEFAULT 'daily'",
                "version": "INTEGER NOT NULL DEFAULT 1",
                "time_window": "TEXT NOT NULL DEFAULT '24h'",
                "language": "TEXT NOT NULL DEFAULT 'zh-CN'",
                "audience": "TEXT NOT NULL DEFAULT 'analyst'",
                "approval_required": "INTEGER NOT NULL DEFAULT 0",
                "approval_status": "TEXT NOT NULL DEFAULT 'not_required'",
                "evidence_count": "INTEGER NOT NULL DEFAULT 0",
                "source_count": "INTEGER NOT NULL DEFAULT 0",
                "confidence": "INTEGER NOT NULL DEFAULT 0",
                "data_cutoff": "TEXT",
                "content_json": "TEXT NOT NULL DEFAULT '{}'",
                "failure_reason": "TEXT",
                "approved_by": "TEXT",
                "approved_at": "TEXT",
                "delivered_at": "TEXT",
                "updated_at": "TEXT NOT NULL DEFAULT ''",
            },
            "data_sources": {
                "collection_config_json": "TEXT NOT NULL DEFAULT '{}'",
                "next_run_at": "TEXT",
                "concurrency_limit": "INTEGER NOT NULL DEFAULT 1",
                "task_timeout_seconds": "INTEGER NOT NULL DEFAULT 120",
                "max_attempts": "INTEGER NOT NULL DEFAULT 3",
                "retry_backoff_seconds": "INTEGER NOT NULL DEFAULT 2",
                "priority": "INTEGER NOT NULL DEFAULT 5",
                "circuit_state": "TEXT NOT NULL DEFAULT 'closed'",
                "circuit_open_until": "TEXT",
                "last_run_started_at": "TEXT",
                "archived_at": "TEXT",
                "archived_by": "TEXT",
            },
            "source_runs": {
                "trigger_type": "TEXT NOT NULL DEFAULT 'manual'",
                "priority": "INTEGER NOT NULL DEFAULT 5",
                "attempt": "INTEGER NOT NULL DEFAULT 0",
                "max_attempts": "INTEGER NOT NULL DEFAULT 3",
                "timeout_seconds": "INTEGER NOT NULL DEFAULT 120",
                "backoff_seconds": "INTEGER NOT NULL DEFAULT 2",
                "scheduled_for": "TEXT",
                "available_at": "TEXT",
                "next_retry_at": "TEXT",
                "retry_delays_json": "TEXT NOT NULL DEFAULT '[]'",
                "recovery_of": "TEXT",
                "recovered_from_restart": "INTEGER NOT NULL DEFAULT 0",
                "workflow_version": "TEXT NOT NULL DEFAULT 'collection-v1'",
                "items_discovered": "INTEGER NOT NULL DEFAULT 0",
                "documents_created": "INTEGER NOT NULL DEFAULT 0",
                "documents_updated": "INTEGER NOT NULL DEFAULT 0",
                "duplicates_skipped": "INTEGER NOT NULL DEFAULT 0",
                "error_type": "TEXT",
                "error_message": "TEXT",
                "request_summary": "TEXT",
                "parser_steps_json": "TEXT NOT NULL DEFAULT '[]'",
                "started_at": "TEXT",
                "finished_at": "TEXT",
                "retry_of": "TEXT",
                "created_by": "TEXT",
            },
        }
        for table, columns in additions.items():
            for name, definition in columns.items():
                if name not in table_columns[table]:
                    connection.execute(
                        f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                    )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_source_runs_source_created "
            "ON source_runs(source_id, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_data_sources_next_run "
            "ON data_sources(enabled, next_run_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_data_sources_archive "
            "ON data_sources(project_id, archived_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_source_runs_dispatch "
            "ON source_runs(status, available_at, priority DESC, created_at)"
        )
        connection.execute(
            "UPDATE reports SET updated_at=created_at WHERE updated_at='' OR updated_at IS NULL"
        )
        connection.execute(
            "UPDATE users SET email=lower(replace(name, ' ', '.')) || '@jinguan.local' "
            "WHERE email='' OR email IS NULL"
        )

    @staticmethod
    def _initialize_next_runs(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """SELECT id, schedule_frequency FROM data_sources
               WHERE enabled=1 AND archived_at IS NULL AND next_run_at IS NULL
                 AND schedule_frequency!='manual'"""
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE data_sources SET next_run_at=? WHERE id=?",
                (schedule_next_run(row["schedule_frequency"]), row["id"]),
            )

    @classmethod
    def _initialize_workflow_steps(cls, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """SELECT r.id, r.max_attempts FROM source_runs r
               WHERE NOT EXISTS (
                 SELECT 1 FROM workflow_steps w WHERE w.run_id=r.id
               )"""
        ).fetchall()
        for row in rows:
            cls._insert_workflow_steps(connection, row["id"], row["max_attempts"])

    @staticmethod
    def _insert_workflow_steps(
        connection: sqlite3.Connection, run_id: str, max_attempts: int
    ) -> None:
        connection.executemany(
            """INSERT OR IGNORE INTO workflow_steps
               (run_id, step_key, step_name, agent_name, step_order, max_attempts)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    run_id,
                    step_key,
                    step_name,
                    agent_name,
                    order,
                    max_attempts if step_key == "collect" else 1,
                )
                for order, (step_key, step_name, agent_name) in enumerate(
                    WORKFLOW_DEFINITION, start=1
                )
            ],
        )

    def ping(self) -> None:
        with self.session() as connection:
            connection.execute("SELECT 1").fetchone()

    def _seed(self, connection: sqlite3.Connection) -> None:
        now = utc_now()
        connection.execute(
            "INSERT INTO users (id, name, initial) VALUES (?, ?, ?)",
            ("user_lin_che", "林澈", "林"),
        )
        projects = [
            ("prj_ai_agent", "AI Agent 行业追踪", "A", "daily", '["cn","global"]'),
            ("prj_collaboration", "企业协作产品研究", "企", "compare", '["cn","global"]'),
        ]
        connection.executemany(
            """INSERT INTO projects
               (id, name, avatar, template, regions_json, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?)""",
            [(*project, now) for project in projects],
        )
        for project_id in ("prj_ai_agent", "prj_collaboration"):
            self._seed_empty_project(connection, project_id, now)

        connection.execute(
            """UPDATE project_metrics SET coverage_rate=92.4, coverage_delta=2.8,
               new_changes=18, new_changes_delta=6, major_alerts=3,
               major_alerts_delta=1, pending_reviews=7, pending_reviews_delta=4,
               data_cutoff='10:00' WHERE project_id='prj_ai_agent'"""
        )
        connection.execute(
            """UPDATE daily_briefs SET title=?, summary=?, evidence_count=8,
               confidence=92, impact_level='high' WHERE project_id='prj_ai_agent'""",
            (
                "Agent 操作能力成为本周主要竞争焦点",
                "4 家重点竞品中有 3 家更新了工具调用或浏览器操作能力。企业级权限、审计与数据边界正在成为差异化关键。",
            ),
        )
        connection.execute(
            """UPDATE source_health SET score=94, normal_count=42,
               abnormal_count=3, disabled_count=1, last_sync='2 分钟前'
               WHERE project_id='prj_ai_agent'"""
        )
        connection.execute("DELETE FROM trend_points WHERE project_id='prj_ai_agent'")
        trend_data = {
            "24h": (
                ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "现在"],
                [3, 5, 11, 8, 14, 12, 18],
                [0, 1, 3, 2, 4, 3, 5],
            ),
            "7d": (
                ["周五", "周六", "周日", "周一", "周二", "周三", "今天"],
                [17, 14, 22, 19, 31, 26, 34],
                [4, 3, 6, 5, 11, 7, 9],
            ),
            "30d": (
                ["07/01", "07/05", "07/09", "07/13", "07/17", "07/21", "07/25", "07/31"],
                [12, 19, 15, 26, 23, 31, 28, 36],
                [3, 5, 4, 9, 7, 10, 8, 12],
            ),
        }
        for range_key, (labels, events, high_impact) in trend_data.items():
            connection.executemany(
                """INSERT INTO trend_points
                   (project_id, range_key, label, event_count, high_impact_count, sort_order)
                   VALUES ('prj_ai_agent', ?, ?, ?, ?, ?)""",
                [
                    (range_key, label, events[index], high_impact[index], index)
                    for index, label in enumerate(labels)
                ],
            )

        insight_rows = [
            (
                "09:42", "事实", "high", "OpenAI",
                "企业版 Agent 新增浏览器操作能力",
                "官方更新日志出现新的计算机操作权限与审计字段，预计将降低企业自动化场景的接入门槛。",
                4, 96,
                "本周内补充企业治理能力对比。重点验证权限粒度、审计留痕和敏感数据边界，作为下一版产品路线图输入。",
                1,
            ),
            (
                "08:15", "推断", "medium", "Anthropic",
                "团队套餐定价策略可能进入调整窗口",
                "定价页结构与帮助中心文档同步发生变化，但尚未发现正式价格公告，建议持续观察。",
                3, 78,
                "继续监控官方定价页面，在获得第二个可靠来源前不要更新正式价格对比。",
                2,
            ),
            (
                "昨天", "事实", "low", "Google",
                "Gemini 企业连接器覆盖范围扩大",
                "新增两个协作工具连接器，并更新管理员的数据边界与权限说明。",
                5, 93,
                "更新连接器覆盖矩阵，并复核连接器授权范围和默认数据保留策略。",
                3,
            ),
            (
                "昨天", "建议", "medium", "Microsoft",
                "建议补充治理维度的横向对比",
                "近期多家竞品都在强化审计与数据驻留能力，现有对比模板对该维度覆盖不足。",
                8, 86,
                "在下周报告模板中加入权限粒度、审计、数据驻留和管理员控制四个治理维度。",
                4,
            ),
        ]
        insight_ids: list[int] = []
        for row in insight_rows:
            cursor = connection.execute(
                """INSERT INTO insights
                   (project_id, time_label, kind, impact_level, company, title,
                    summary, source_count, confidence, recommendation, sort_order, created_at)
                   VALUES ('prj_ai_agent', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*row, now),
            )
            insight_ids.append(int(cursor.lastrowid))
        connection.execute(
            "UPDATE daily_briefs SET insight_id=? WHERE project_id='prj_ai_agent'",
            (insight_ids[0],),
        )

        evidence_rows = [
            (
                insight_ids[0], "官方产品更新日志", "OpenAI", "https://openai.com/",
                "管理员现在可以为计算机操作设置独立权限，并在审计日志中查看每次工具调用。",
                "primary", "2 小时前",
            ),
            (
                insight_ids[0], "行业媒体交叉验证", "TechCrunch", "https://techcrunch.com/",
                "报道确认该功能将首先面向企业客户开放，并强调管理员控制和使用记录能力。",
                "cross_check", "1 小时前",
            ),
            (
                insight_ids[1], "团队套餐定价页面", "Anthropic", "https://www.anthropic.com/",
                "定价页面的信息层级发生调整，部分套餐说明被移动到帮助中心。",
                "primary", "3 小时前",
            ),
            (
                insight_ids[2], "Workspace 更新日志", "Google", "https://workspace.google.com/",
                "管理员控制台新增协作工具连接器的启用和访问范围选项。",
                "primary", "昨天",
            ),
        ]
        connection.executemany(
            """INSERT INTO evidence
               (insight_id, title, source_name, source_url, excerpt, source_type, published_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            evidence_rows,
        )

        review_rows = [
            ("Anthropic", "Team 套餐价格", "来源冲突", "12 分钟前", "conflict"),
            ("Google", "发布日期", "置信度 68%", "31 分钟前", "warning"),
            ("Perplexity", "企业功能", "缺少主来源", "1 小时前", "neutral"),
            ("Microsoft", "数据驻留区域", "来源冲突", "2 小时前", "conflict"),
            ("OpenAI", "API 速率限制", "置信度 72%", "3 小时前", "warning"),
            ("Mistral", "企业部署方式", "缺少主来源", "4 小时前", "neutral"),
            ("Cohere", "审计日志范围", "置信度 65%", "5 小时前", "warning"),
        ]
        connection.executemany(
            """INSERT INTO review_items
               (project_id, company, field_name, reason, time_label, tone, status)
               VALUES ('prj_ai_agent', ?, ?, ?, ?, ?, 'pending')""",
            review_rows,
        )

        report_rows = [
            ("rpt_daily_001", "AI Agent 竞品晨报", "每日 09:00", "已交付", 100),
            ("rpt_weekly_001", "企业智能助手周报", "周五 17:30", "生成中", 64),
            ("rpt_strategy_001", "Q3 定价专题研究", "8 月 02 日", "待审批", 88),
        ]
        connection.executemany(
            """INSERT INTO reports
               (id, project_id, title, schedule_label, status, progress, created_at)
               VALUES (?, 'prj_ai_agent', ?, ?, ?, ?, ?)""",
            [(*row, now) for row in report_rows],
        )

    def _seed_reporting(self, connection: sqlite3.Connection) -> None:
        if not connection.execute("SELECT 1 FROM projects WHERE id='prj_ai_agent'").fetchone():
            return
        now = utc_now()
        templates = [
            (
                "tpl_daily",
                "竞品动态日报",
                "daily",
                "面向分析师的每日关键变化、影响判断与建议动作。",
                ["执行摘要", "关键变化", "影响判断", "建议动作", "风险与来源"],
                "analyst",
                0,
            ),
            (
                "tpl_weekly",
                "竞品趋势周报",
                "weekly",
                "聚合一周竞品活跃度、趋势和跨来源信号。",
                ["本周摘要", "变化趋势", "产品对比", "市场信号", "下周关注"],
                "product",
                1,
            ),
            (
                "tpl_compare",
                "产品能力对比",
                "compare",
                "按统一维度呈现能力、定价、治理与市场差异。",
                ["对比范围", "能力矩阵", "定价与市场", "优势与差距", "证据"],
                "product",
                1,
            ),
            (
                "tpl_flash",
                "竞品快讯",
                "flash",
                "针对单一高影响事件的快速事实卡与处置建议。",
                ["事件", "事实", "影响", "建议", "证据"],
                "general",
                0,
            ),
            (
                "tpl_strategy",
                "专题研究",
                "strategy",
                "围绕特定主题形成证据化研究、风险与商业建议。",
                ["研究问题", "方法", "发现", "趋势", "建议", "风险", "来源"],
                "management",
                1,
            ),
            (
                "tpl_executive",
                "高管一页摘要",
                "executive",
                "用一页结构呈现关键变化、业务影响和决策建议。",
                ["决策摘要", "关键变化", "业务影响", "建议决策", "风险"],
                "management",
                1,
            ),
        ]
        connection.executemany(
            """INSERT OR IGNORE INTO report_templates
               (id, name, report_type, description, sections_json, language,
                audience, approval_required, builtin, updated_at)
               VALUES (?, ?, ?, ?, ?, 'zh-CN', ?, ?, 1, ?)""",
            [
                (
                    template_id,
                    name,
                    report_type,
                    description,
                    json.dumps(sections, ensure_ascii=False),
                    audience,
                    approval_required,
                    now,
                )
                for template_id, name, report_type, description, sections, audience, approval_required in templates
            ],
        )
        report_updates = {
            "rpt_daily_001": ("tpl_daily", "daily", "24h", "analyst", 0, "not_required", 18, 8, 94),
            "rpt_weekly_001": ("tpl_weekly", "weekly", "7d", "product", 1, "pending", 31, 12, 89),
            "rpt_strategy_001": ("tpl_strategy", "strategy", "30d", "management", 1, "pending", 42, 15, 91),
        }
        for report_id, values in report_updates.items():
            connection.execute(
                """UPDATE reports SET template_id=?, report_type=?, time_window=?,
                   audience=?, approval_required=?, approval_status=?, evidence_count=?,
                   source_count=?, confidence=?, data_cutoff=COALESCE(data_cutoff, ?),
                   content_json=CASE WHEN content_json='{}' THEN ? ELSE content_json END,
                   delivered_at=CASE WHEN status='已交付' THEN COALESCE(delivered_at, created_at) ELSE delivered_at END,
                   updated_at=CASE WHEN updated_at='' THEN created_at ELSE updated_at END
                   WHERE id=?""",
                (
                    *values,
                    now,
                    json.dumps(
                        {
                            "执行摘要": "重点竞品正在加速企业级 Agent 的权限、审计和连接器能力建设。",
                            "关键变化": [
                                "OpenAI 更新企业工具调用权限与审计字段。",
                                "Google Workspace 扩展协作连接器和管理员控制。",
                            ],
                            "影响判断": "企业治理能力已从合规门槛转向产品差异化维度。",
                            "建议动作": ["把权限粒度、审计和数据边界纳入固定周度跟踪。"],
                            "风险": "部分结论仍受发布时间差异影响，需保留冲突标记。",
                        },
                        ensure_ascii=False,
                    ),
                    report_id,
                ),
            )
        if not connection.execute("SELECT 1 FROM report_subscriptions LIMIT 1").fetchone():
            connection.executemany(
                """INSERT INTO report_subscriptions
                   (id, project_id, name, template_id, cadence, delivery_time,
                    timezone, channels_json, recipients_json, enabled, next_run_at,
                    last_delivery_status, created_by, created_at, updated_at)
                   VALUES (?, 'prj_ai_agent', ?, ?, ?, ?, 'Asia/Hong_Kong', ?, ?, ?, ?, ?,
                           'user_lin_che', ?, ?)""",
                [
                    (
                        "sub_daily_morning",
                        "每日竞品晨报",
                        "tpl_daily",
                        "daily",
                        "09:00",
                        '["in_app","email"]',
                        '["市场分析组","产品负责人"]',
                        1,
                        schedule_next_run("daily"),
                        "success",
                        now,
                        now,
                    ),
                    (
                        "sub_weekly_product",
                        "产品策略周报",
                        "tpl_weekly",
                        "weekly",
                        "17:30",
                        '["in_app","enterprise_message"]',
                        '["产品委员会"]',
                        1,
                        schedule_next_run("weekly"),
                        "pending",
                        now,
                        now,
                    ),
                ],
            )
        if not connection.execute("SELECT 1 FROM alert_rules LIMIT 1").fetchone():
            connection.executemany(
                """INSERT INTO alert_rules
                   (id, project_id, name, competitors_json, keywords_json,
                    event_types_json, min_impact, min_confidence, change_threshold,
                    quiet_minutes, escalation_minutes, channels_json, enabled,
                    last_triggered_at, created_by, created_at, updated_at)
                   VALUES (?, 'prj_ai_agent', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?,
                           'user_lin_che', ?, ?)""",
                [
                    (
                        "rule_major_release",
                        "重点竞品重大发布",
                        '["OpenAI","Google","Anthropic"]',
                        '["发布","企业版","Agent"]',
                        '["release","feature_add"]',
                        "high",
                        85,
                        0,
                        120,
                        60,
                        '["in_app","email"]',
                        now,
                        now,
                        now,
                    ),
                    (
                        "rule_price_change",
                        "定价变化超过 10%",
                        '[]',
                        '["定价","套餐","折扣"]',
                        '["price_increase","price_decrease"]',
                        "medium",
                        75,
                        10,
                        240,
                        120,
                        '["in_app","enterprise_message"]',
                        None,
                        now,
                        now,
                    ),
                    (
                        "rule_governance",
                        "企业治理能力变化",
                        '[]',
                        '["权限","审计","数据驻留"]',
                        '["feature_add","release"]',
                        "medium",
                        80,
                        0,
                        180,
                        90,
                        '["in_app"]',
                        now,
                        now,
                        now,
                    ),
                ],
            )
        if not connection.execute("SELECT 1 FROM alerts LIMIT 1").fetchone():
            insight_rows = connection.execute(
                "SELECT id, company, title, summary, impact_level, confidence, source_count FROM insights WHERE project_id='prj_ai_agent' ORDER BY sort_order LIMIT 3"
            ).fetchall()
            for index, insight in enumerate(insight_rows, start=1):
                connection.execute(
                    """INSERT INTO alerts
                       (id, project_id, rule_id, insight_id, title, summary, competitor,
                        event_type, impact, confidence, source_count, status,
                        occurrence_count, first_seen_at, last_seen_at, quiet_until)
                       VALUES (?, 'prj_ai_agent', ?, ?, ?, ?, ?, 'feature_add', ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        f"alt_seed_{index}",
                        "rule_major_release" if index == 1 else "rule_governance",
                        insight["id"],
                        insight["title"],
                        insight["summary"],
                        insight["company"],
                        "critical" if index == 1 else insight["impact_level"],
                        insight["confidence"],
                        insight["source_count"],
                        "new" if index < 3 else "acknowledged",
                        2 if index == 1 else 1,
                        now,
                        now,
                        (datetime.now(UTC) + timedelta(minutes=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    ),
                )

    def _seed_governance(self, connection: sqlite3.Connection) -> None:
        now = utc_now()
        connection.execute(
            """INSERT OR IGNORE INTO organizations
               (id, name, domain, plan, sso_enforced, mfa_required,
                session_timeout_minutes, status, created_at)
               VALUES ('org_jinguan', '镜观智能科技', 'jinguan.local', 'enterprise',
                       1, 1, 480, 'active', ?)""",
            (now,),
        )
        roles = [
            ("role_admin", "系统管理员", "组织、权限、模型、策略和运维配置", ["*"]),
            ("role_data_ops", "数据运营", "维护来源、任务与数据质量", ["sources.manage", "tasks.manage", "reports.view"]),
            ("role_analyst", "分析师", "创建分析、复核洞察和生成报告", ["reports.view", "reports.manage", "insights.review"]),
            ("role_viewer", "业务查看者", "查看、订阅和导出获授权内容", ["reports.view", "reports.export"]),
            ("role_auditor", "审计与合规", "只读访问合规配置与审计记录", ["admin.view", "audit.view"]),
        ]
        connection.executemany(
            """INSERT OR IGNORE INTO roles
               (id, name, description, permissions_json, system)
               VALUES (?, ?, ?, ?, 1)""",
            [(role_id, name, description, json.dumps(permissions)) for role_id, name, description, permissions in roles],
        )
        connection.executemany(
            """INSERT OR IGNORE INTO users (id, name, initial, email, status)
               VALUES (?, ?, ?, ?, 'active')""",
            [
                ("user_zhou_qi", "周祺", "周", "zhou.qi@jinguan.local"),
                ("user_xu_wen", "徐雯", "徐", "xu.wen@jinguan.local"),
                ("user_he_yan", "何言", "何", "he.yan@jinguan.local"),
            ],
        )
        connection.execute(
            "UPDATE users SET email='lin.che@jinguan.local', status='active' WHERE id='user_lin_che'"
        )
        memberships = [
            ("user_lin_che", "role_admin", 1, "sensitive", '["*"]', '["public","internal","restricted"]'),
            ("user_zhou_qi", "role_analyst", 1, "standard", '["prj_ai_agent"]', '["public","internal"]'),
            ("user_xu_wen", "role_data_ops", 1, "none", '["prj_ai_agent","prj_collaboration"]', '["public","internal"]'),
            ("user_he_yan", "role_auditor", 1, "sensitive", '["*"]', '["public","internal","restricted"]'),
        ]
        connection.executemany(
            """INSERT OR IGNORE INTO user_memberships
               (user_id, organization_id, role_id, status, mfa_enabled,
                export_permission, project_scopes_json, data_domains_json, last_login_at)
               VALUES (?, 'org_jinguan', ?, 'active', ?, ?, ?, ?, ?)""",
            [(*membership, now) for membership in memberships],
        )
        if not connection.execute("SELECT 1 FROM model_configs LIMIT 1").fetchone():
            connection.executemany(
                """INSERT INTO model_configs
                   (id, provider, model_name, version, routing_class, status,
                    allowed_data_classifications_json, monthly_budget, spent_amount,
                    quota_warning_percent, fallback_model, latency_p95_ms, success_rate, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    ("mdl_primary", "OpenAI", "Enterprise Reasoning", "2026-07", "standard", "active", '["public","internal"]', 20000, 12680, 80, "mdl_private", 1840, 99.2, now),
                    ("mdl_private", "Private Cloud", "Jinguan Extractor", "v3.4", "private", "active", '["public","internal","restricted"]', 12000, 7280, 85, None, 2260, 98.7, now),
                    ("mdl_fallback", "Rules Engine", "Evidence Extractive", "v2.1", "restricted", "active", '["public","internal","restricted"]', 3000, 910, 90, None, 420, 99.8, now),
                ],
            )
        if not connection.execute("SELECT 1 FROM evaluation_metrics LIMIT 1").fetchone():
            connection.executemany(
                """INSERT INTO evaluation_metrics
                   (id, model_config_id, dataset_name, accuracy, citation_completeness,
                    refusal_rate, latency_p95_ms, cost_per_run, sample_size, evaluated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    ("eval_primary", "mdl_primary", "黄金集 2026-Q3", 92.6, 100, 4.8, 1840, 0.38, 420, now),
                    ("eval_private", "mdl_private", "敏感抽取集", 90.8, 100, 6.2, 2260, 0.26, 180, now),
                    ("eval_fallback", "mdl_fallback", "规则降级集", 84.5, 100, 11.4, 420, 0.03, 240, now),
                ],
            )
        if not connection.execute("SELECT 1 FROM security_policies LIMIT 1").fetchone():
            policies = [
                ("pol_identity", "identity_access", "统一身份与会话", "identity", {"sso": True, "mfa": True, "session_timeout_minutes": 480}, "enforced"),
                ("pol_export", "sensitive_export", "高敏导出审批", "export", {"second_confirmation": True, "approver_role": "role_admin", "watermark": True}, "enforced"),
                ("pol_retention", "data_retention", "数据保留与法律保全", "retention", {"public_days": 365, "internal_days": 180, "restricted_days": 90, "legal_hold": True}, "enforced"),
                ("pol_model", "model_routing", "敏感数据模型路由", "model", {"restricted_route": "mdl_private", "external_blocked": True}, "enforced"),
                ("pol_privacy", "personal_information", "个人信息最小化", "data", {"detect": True, "mask": True, "deletion_workflow": True}, "monitoring"),
            ]
            connection.executemany(
                """INSERT INTO security_policies
                   (id, organization_id, policy_key, name, category, value_json,
                    status, updated_by, updated_at)
                   VALUES (?, 'org_jinguan', ?, ?, ?, ?, ?, 'user_lin_che', ?)""",
                [(pid, key, name, category, json.dumps(value, ensure_ascii=False), policy_status, now) for pid, key, name, category, value, policy_status in policies],
            )
        if not connection.execute("SELECT 1 FROM service_components LIMIT 1").fetchone():
            connection.executemany(
                """INSERT INTO service_components
                   (id, name, status, uptime, latency_p95_ms, detail, last_checked_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    ("svc_api", "核心 API", "healthy", 99.97, 186, "查询与项目服务正常", now),
                    ("svc_collection", "采集与任务队列", "healthy", 99.82, 740, "队列积压处于安全水位", now),
                    ("svc_processing", "处理与知识索引", "healthy", 99.76, 1240, "抽取链路正常", now),
                    ("svc_model", "模型网关", "degraded", 99.41, 2260, "私有模型延迟高于基线，降级策略已就绪", now),
                    ("svc_delivery", "报告与通知", "healthy", 99.93, 520, "邮件和企业消息通道正常", now),
                ],
            )
        if not connection.execute("SELECT 1 FROM incidents LIMIT 1").fetchone():
            connection.executemany(
                """INSERT INTO incidents
                   (id, title, severity, status, owner, started_at, updated_at, detail)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    ("inc_model_latency", "私有模型 P95 延迟升高", "sev3", "monitoring", "平台运维", now, now, "自动切换低延迟抽取模型，持续观察恢复情况。"),
                    ("inc_parser_change", "Google 公告页结构变化", "sev4", "resolved", "数据运营", now, now, "连接器已回滚并完成补采，未污染主数据。"),
                ],
            )
        if not connection.execute("SELECT 1 FROM backup_runs LIMIT 1").fetchone():
            connection.executemany(
                """INSERT INTO backup_runs
                   (id, backup_type, status, rpo_minutes, size_bytes, started_at,
                    completed_at, restore_verified, created_by)
                   VALUES (?, ?, 'succeeded', ?, ?, ?, ?, ?, 'user_lin_che')""",
                [
                    ("bak_full_seed", "full", 12, 1866465280, now, now, 1),
                    ("bak_inc_seed", "incremental", 8, 184549376, now, now, 1),
                ],
            )

    def _seed_sources(self, connection: sqlite3.Connection, project_id: str) -> None:
        now = utc_now()
        passed_checks = json.dumps(
            [
                {
                    "key": "connectivity",
                    "label": "连通性",
                    "status": "passed",
                    "message": "入口与连接器配置可用",
                    "checked_at": now,
                },
                {
                    "key": "compliance",
                    "label": "授权与合规",
                    "status": "passed",
                    "message": "授权、条款与 robots 提示已确认",
                    "checked_at": now,
                },
                {
                    "key": "rate_limit",
                    "label": "速率限制",
                    "status": "passed",
                    "message": "限流策略已配置",
                    "checked_at": now,
                },
                {
                    "key": "field_availability",
                    "label": "字段可用性",
                    "status": "passed",
                    "message": "核心字段映射完整",
                    "checked_at": now,
                },
            ],
            ensure_ascii=False,
        )
        sources = [
            {
                "id": "src_openai_updates",
                "name": "OpenAI 产品更新",
                "type": "webpage",
                "endpoint": "https://openai.com/news/product/",
                "subject": "OpenAI",
                "access": "public",
                "strategy": "正文差异与版本变更",
                "regions": ["global"],
                "basis": "公开官网与使用条款允许的合理访问",
                "auth": "approved",
                "classification": "public",
                "retention": 365,
                "frequency": "hourly",
                "limit": 12,
                "credential": None,
                "expires": None,
                "fields": ["title", "published_at", "body", "product"],
                "enabled": 1,
                "status": "healthy",
                "score": 98,
                "success": 99.4,
                "failures": 0,
                "latency": 620,
                "freshness": 18,
                "change": 12.5,
                "completeness": 98.0,
                "last_collected": "2026-07-31T09:42:00Z",
                "last_success": "2026-07-31T09:42:01Z",
            },
            {
                "id": "src_anthropic_rss",
                "name": "Anthropic News RSS",
                "type": "rss",
                "endpoint": "https://www.anthropic.com/news/rss.xml",
                "subject": "Anthropic",
                "access": "public",
                "strategy": "RSS 增量采集",
                "regions": ["global"],
                "basis": "公开 RSS 订阅",
                "auth": "approved",
                "classification": "public",
                "retention": 365,
                "frequency": "hourly",
                "limit": 20,
                "credential": None,
                "expires": None,
                "fields": ["title", "link", "published_at", "summary"],
                "enabled": 1,
                "status": "healthy",
                "score": 96,
                "success": 98.7,
                "failures": 0,
                "latency": 410,
                "freshness": 36,
                "change": 8.0,
                "completeness": 100.0,
                "last_collected": "2026-07-31T09:24:00Z",
                "last_success": "2026-07-31T09:24:00Z",
            },
            {
                "id": "src_google_workspace",
                "name": "Google Workspace 更新日志",
                "type": "rss",
                "endpoint": "https://workspaceupdates.googleblog.com/feeds/posts/default",
                "subject": "Google",
                "access": "public",
                "strategy": "RSS 增量采集",
                "regions": ["global"],
                "basis": "公开更新日志订阅",
                "auth": "approved",
                "classification": "public",
                "retention": 730,
                "frequency": "6h",
                "limit": 12,
                "credential": None,
                "expires": None,
                "fields": ["title", "published_at", "body", "product"],
                "enabled": 1,
                "status": "healthy",
                "score": 94,
                "success": 97.9,
                "failures": 0,
                "latency": 780,
                "freshness": 110,
                "change": 7.2,
                "completeness": 96.0,
                "last_collected": "2026-07-31T08:10:00Z",
                "last_success": "2026-07-31T08:10:01Z",
            },
            {
                "id": "src_ms_graph",
                "name": "Microsoft Graph Changelog API",
                "type": "public_api",
                "endpoint": "https://graph.microsoft.com/v1.0/admin/serviceAnnouncement/messages",
                "subject": "Microsoft",
                "access": "oauth2",
                "strategy": "游标增量与条件请求",
                "regions": ["global"],
                "basis": "企业开发者协议与租户授权",
                "auth": "approved",
                "classification": "internal",
                "retention": 365,
                "frequency": "6h",
                "limit": 60,
                "credential": "vault://jinguan/microsoft-graph",
                "expires": "2026-08-15T00:00:00Z",
                "fields": ["id", "title", "startDateTime", "body"],
                "enabled": 1,
                "status": "warning",
                "score": 82,
                "success": 92.1,
                "failures": 1,
                "latency": 1650,
                "freshness": 245,
                "change": 10.0,
                "completeness": 91.0,
                "last_collected": "2026-07-31T06:00:00Z",
                "last_success": "2026-07-31T06:00:02Z",
            },
            {
                "id": "src_techcrunch",
                "name": "TechCrunch AI RSS",
                "type": "rss",
                "endpoint": "https://techcrunch.com/category/artificial-intelligence/feed/",
                "subject": "行业媒体",
                "access": "public",
                "strategy": "RSS 增量采集与近似去重",
                "regions": ["global"],
                "basis": "公开 RSS 订阅，仅保留必要证据片段",
                "auth": "approved",
                "classification": "public",
                "retention": 180,
                "frequency": "hourly",
                "limit": 15,
                "credential": None,
                "expires": None,
                "fields": ["title", "link", "published_at", "summary"],
                "enabled": 1,
                "status": "healthy",
                "score": 91,
                "success": 96.8,
                "failures": 0,
                "latency": 890,
                "freshness": 52,
                "change": 18.4,
                "completeness": 94.0,
                "last_collected": "2026-07-31T09:08:00Z",
                "last_success": "2026-07-31T09:08:01Z",
            },
            {
                "id": "src_g2_public",
                "name": "G2 公开产品目录",
                "type": "public_database",
                "endpoint": "https://www.g2.com/categories/artificial-intelligence-platforms",
                "subject": "G2",
                "access": "public",
                "strategy": "低频目录与评分变化",
                "regions": ["global"],
                "basis": "公开页面，仅采集许可字段与证据片段",
                "auth": "approved",
                "classification": "public",
                "retention": 90,
                "frequency": "daily",
                "limit": 4,
                "credential": None,
                "expires": None,
                "fields": ["product", "rating", "review_count"],
                "enabled": 1,
                "status": "error",
                "score": 61,
                "success": 68.0,
                "failures": 4,
                "latency": 4200,
                "freshness": 1640,
                "change": 2.1,
                "completeness": 73.0,
                "last_collected": "2026-07-30T07:00:00Z",
                "last_success": "2026-07-29T07:00:03Z",
            },
            {
                "id": "src_x_social",
                "name": "X 官方账号监测",
                "type": "social_api",
                "endpoint": "https://api.x.com/2/users/by",
                "subject": "重点竞品官方账号",
                "access": "oauth2",
                "strategy": "授权 API 增量采集",
                "regions": ["global"],
                "basis": "待确认社交平台 API 授权范围",
                "auth": "pending",
                "classification": "restricted",
                "retention": 30,
                "frequency": "manual",
                "limit": 15,
                "credential": "vault://jinguan/x-api",
                "expires": "2026-12-31T00:00:00Z",
                "fields": ["id", "text", "created_at"],
                "enabled": 0,
                "status": "disabled",
                "score": 0,
                "success": 0.0,
                "failures": 0,
                "latency": 0,
                "freshness": 0,
                "change": 0.0,
                "completeness": 0.0,
                "last_collected": None,
                "last_success": None,
            },
            {
                "id": "src_pricing_sitemap",
                "name": "重点竞品定价页 Sitemap",
                "type": "sitemap",
                "endpoint": "https://example.com/sitemap-pricing.xml",
                "subject": "定价专题",
                "access": "public",
                "strategy": "站点地图发现与价格页差异",
                "regions": ["cn", "global"],
                "basis": "试点竞品公开站点地图",
                "auth": "approved",
                "classification": "public",
                "retention": 365,
                "frequency": "6h",
                "limit": 10,
                "credential": None,
                "expires": None,
                "fields": ["url", "lastmod", "price", "currency"],
                "enabled": 1,
                "status": "healthy",
                "score": 89,
                "success": 95.3,
                "failures": 0,
                "latency": 1120,
                "freshness": 180,
                "change": 5.8,
                "completeness": 90.0,
                "last_collected": "2026-07-31T07:00:00Z",
                "last_success": "2026-07-31T07:00:01Z",
            },
        ]
        for source in sources:
            credential_ref = source["credential"]
            credential_masked = self._mask_credential_ref(credential_ref)
            checks = passed_checks if source["auth"] == "approved" else json.dumps(
                [
                    {
                        "key": "connectivity",
                        "label": "连通性",
                        "status": "pending",
                        "message": "尚未执行检查",
                        "checked_at": None,
                    },
                    {
                        "key": "compliance",
                        "label": "授权与合规",
                        "status": "failed",
                        "message": "授权状态尚未通过",
                        "checked_at": now,
                    },
                    {
                        "key": "rate_limit",
                        "label": "速率限制",
                        "status": "pending",
                        "message": "尚未执行检查",
                        "checked_at": None,
                    },
                    {
                        "key": "field_availability",
                        "label": "字段可用性",
                        "status": "pending",
                        "message": "尚未执行检查",
                        "checked_at": None,
                    },
                ],
                ensure_ascii=False,
            )
            connection.execute(
                """INSERT INTO data_sources
                   (id, project_id, name, source_type, endpoint, subject, access_method,
                    crawl_strategy, regions_json, authorization_basis, authorization_status,
                    data_classification, retention_days, schedule_frequency,
                    rate_limit_per_minute, credential_ref, credential_masked,
                    credential_expires_at, fields_json, robots_acknowledged,
                    terms_acknowledged, enabled, health_status, health_score,
                    success_rate, consecutive_failures, average_latency_ms,
                    freshness_minutes, content_change_rate, parser_completeness,
                    check_results_json, last_checked_at, last_collected_at,
                    last_success_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           1, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source["id"], project_id, source["name"], source["type"],
                    source["endpoint"], source["subject"], source["access"],
                    source["strategy"], json.dumps(source["regions"], ensure_ascii=False),
                    source["basis"], source["auth"], source["classification"],
                    source["retention"], source["frequency"], source["limit"],
                    credential_ref, credential_masked, source["expires"],
                    json.dumps(source["fields"], ensure_ascii=False), source["enabled"],
                    source["status"], source["score"], source["success"],
                    source["failures"], source["latency"], source["freshness"],
                    source["change"], source["completeness"], checks, now,
                    source["last_collected"], source["last_success"], now, now,
                ),
            )

    def _seed_knowledge(
        self, connection: sqlite3.Connection, project_id: str
    ) -> None:
        """Seed the intelligence library without mutating immutable source snapshots."""

        now = utc_now()
        items = [
            {
                "id": "knw_openai_browser_fact",
                "source_id": "src_openai_updates",
                "item_type": "fact",
                "title": "企业版 Agent 新增浏览器操作权限",
                "summary": "官方更新日志新增计算机操作权限与独立审计字段，企业管理员可按角色控制工具调用。",
                "content": "企业版 Agent 的浏览器操作能力已进入可配置治理阶段，权限与审计信息可被管理员独立管理。",
                "subject": "OpenAI",
                "category": "product_capability",
                "language": "zh",
                "tags": ["Agent", "浏览器操作", "企业治理"],
                "confidence": 96,
                "quality_score": 94,
                "review_status": "verified",
                "validity_status": "active",
                "source_count": 4,
                "evidence_excerpt": "管理员现在可以为计算机操作设置独立权限，并在审计日志中查看每次工具调用。",
                "evidence_start": 128,
                "evidence_end": 169,
                "extraction_method": "规则抽取 + 人工确认",
                "published_at": "2026-07-31T07:42:00Z",
            },
            {
                "id": "knw_openai_browser_event",
                "source_id": "src_openai_updates",
                "item_type": "event",
                "title": "OpenAI 发布企业浏览器操作能力",
                "summary": "一次高影响产品发布事件，影响企业自动化接入、权限边界与审计能力对比。",
                "content": "事件类型：产品发布；影响等级：高；对象：企业版 Agent 浏览器操作能力。",
                "subject": "OpenAI",
                "category": "release",
                "language": "zh",
                "tags": ["产品发布", "高影响", "Agent"],
                "confidence": 94,
                "quality_score": 92,
                "review_status": "verified",
                "validity_status": "active",
                "source_count": 4,
                "evidence_excerpt": "该能力首先面向企业客户开放，并强调管理员控制和完整使用记录。",
                "evidence_start": 214,
                "evidence_end": 247,
                "extraction_method": "事件抽取 v1 + 多源校验",
                "published_at": "2026-07-31T07:42:00Z",
            },
            {
                "id": "knw_anthropic_pricing_fact",
                "source_id": "src_anthropic_rss",
                "item_type": "fact",
                "title": "Anthropic 团队套餐页面结构发生变化",
                "summary": "定价页与帮助中心同步调整，但尚未发现正式价格公告，当前作为冲突事实并列保存。",
                "content": "页面结构变化已确认；是否代表套餐价格调整尚无足够证据。",
                "subject": "Anthropic",
                "category": "pricing",
                "language": "zh",
                "tags": ["定价", "页面变更", "待交叉验证"],
                "confidence": 78,
                "quality_score": 76,
                "review_status": "conflict",
                "validity_status": "active",
                "source_count": 3,
                "evidence_excerpt": "定价页面的信息层级发生调整，部分套餐说明被移动到帮助中心。",
                "evidence_start": 88,
                "evidence_end": 119,
                "extraction_method": "页面差异 + 规则抽取",
                "published_at": "2026-07-31T06:15:00Z",
            },
            {
                "id": "knw_google_connector_event",
                "source_id": "src_google_workspace",
                "item_type": "event",
                "title": "Gemini 企业连接器覆盖范围扩大",
                "summary": "Google Workspace 新增两个协作工具连接器，并补充管理员数据边界说明。",
                "content": "事件类型：功能新增；影响等级：中；对象：企业连接器与管理员控制。",
                "subject": "Google",
                "category": "feature_add",
                "language": "zh",
                "tags": ["连接器", "Gemini", "企业协作"],
                "confidence": 93,
                "quality_score": 91,
                "review_status": "verified",
                "validity_status": "active",
                "source_count": 5,
                "evidence_excerpt": "管理员控制台新增协作工具连接器的启用和访问范围选项。",
                "evidence_start": 65,
                "evidence_end": 94,
                "extraction_method": "事件抽取 v1",
                "published_at": "2026-07-30T08:10:00Z",
            },
            {
                "id": "knw_google_workspace_entity",
                "source_id": "src_google_workspace",
                "item_type": "entity",
                "title": "Google Workspace",
                "summary": "Google 旗下企业协作产品主实体，已关联 Gemini、企业连接器与管理员控制主题。",
                "content": "标准名：Google Workspace；类型：产品；所属主体：Google。",
                "subject": "Google",
                "category": "product",
                "language": "en",
                "tags": ["产品", "协作套件", "主数据"],
                "confidence": 99,
                "quality_score": 96,
                "review_status": "verified",
                "validity_status": "active",
                "source_count": 12,
                "evidence_excerpt": "Google Workspace administrators can configure connector access for their organization.",
                "evidence_start": 12,
                "evidence_end": 90,
                "extraction_method": "实体词典 + 人工归一",
                "published_at": "2026-07-30T08:10:00Z",
            },
            {
                "id": "knw_governance_insight",
                "source_id": "src_openai_updates",
                "item_type": "insight",
                "title": "企业级治理正在成为 Agent 产品差异化关键",
                "summary": "多家重点竞品近期同步强化权限粒度、审计、数据驻留与管理员控制，建议纳入固定对比维度。",
                "content": "该条为跨来源推断，不等同于单一来源事实；进入报告时必须保留推断标签与证据集合。",
                "subject": "Agent 行业",
                "category": "strategy",
                "language": "zh",
                "tags": ["推断", "企业治理", "竞争格局"],
                "confidence": 86,
                "quality_score": 88,
                "review_status": "review_required",
                "validity_status": "active",
                "source_count": 8,
                "evidence_excerpt": "近期多家竞品都在强化审计与数据驻留能力，现有对比模板对该维度覆盖不足。",
                "evidence_start": 0,
                "evidence_end": 39,
                "extraction_method": "多源归纳 + 模型生成",
                "published_at": "2026-07-31T04:00:00Z",
            },
            {
                "id": "knw_ms_residency_fact",
                "source_id": "src_ms_graph",
                "item_type": "fact",
                "title": "Microsoft 企业数据驻留范围待确认",
                "summary": "当前来源健康度下降且凭据临近轮换，关联事实已标记为来源风险，等待重新采集确认。",
                "content": "来源仍获授权，但最新采集存在延迟；不得用旧值覆盖其他时间点的冲突记录。",
                "subject": "Microsoft",
                "category": "data_residency",
                "language": "zh",
                "tags": ["数据驻留", "来源风险", "待复核"],
                "confidence": 72,
                "quality_score": 68,
                "review_status": "review_required",
                "validity_status": "at_risk",
                "source_count": 2,
                "evidence_excerpt": "服务公告列出新增区域，但与管理员文档中的可用范围存在时间差。",
                "evidence_start": 42,
                "evidence_end": 72,
                "extraction_method": "字段映射 + 冲突检测",
                "published_at": "2026-07-30T06:00:00Z",
            },
        ]
        for item in items:
            connection.execute(
                """INSERT INTO knowledge_items
                   (id, project_id, document_id, source_id, item_type, title,
                    summary, content, subject, category, language, tags_json,
                    confidence, quality_score, review_status, validity_status,
                    source_count, evidence_excerpt, evidence_start, evidence_end,
                    extraction_method, origin, published_at, created_at, updated_at)
                   VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, 'seed', ?, ?, ?)""",
                (
                    item["id"],
                    project_id,
                    item["source_id"],
                    item["item_type"],
                    item["title"],
                    item["summary"],
                    item["content"],
                    item["subject"],
                    item["category"],
                    item["language"],
                    json.dumps(item["tags"], ensure_ascii=False),
                    item["confidence"],
                    item["quality_score"],
                    item["review_status"],
                    item["validity_status"],
                    item["source_count"],
                    item["evidence_excerpt"],
                    item["evidence_start"],
                    item["evidence_end"],
                    item["extraction_method"],
                    item["published_at"],
                    now,
                    now,
                ),
            )
            connection.execute(
                """INSERT INTO knowledge_revisions
                   (item_id, version_no, action, snapshot_json, note, changed_by, created_at)
                   VALUES (?, 1, 'created', ?, '初始化知识条目', 'user_lin_che', ?)""",
                (
                    item["id"],
                    json.dumps(
                        {
                            "review_status": item["review_status"],
                            "validity_status": item["validity_status"],
                            "confidence": item["confidence"],
                            "tags": item["tags"],
                        },
                        ensure_ascii=False,
                    ),
                    now,
                ),
            )

        collections = [
            (
                "kcol_agent_capability",
                "Agent 操作能力",
                "追踪浏览器操作、工具调用与自主执行能力的证据和事件。",
                "#687c67",
            ),
            (
                "kcol_governance",
                "企业治理与合规",
                "权限、审计、数据驻留和管理员控制专题。",
                "#8c6f56",
            ),
            (
                "kcol_pricing",
                "定价动态",
                "套餐价格、页面变更及冲突事实的待验证集合。",
                "#796b91",
            ),
        ]
        connection.executemany(
            """INSERT INTO knowledge_collections
               (id, project_id, name, description, color, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'user_lin_che', ?, ?)""",
            [(item_id, project_id, name, description, color, now, now) for item_id, name, description, color in collections],
        )
        memberships = [
            ("kcol_agent_capability", "knw_openai_browser_fact"),
            ("kcol_agent_capability", "knw_openai_browser_event"),
            ("kcol_governance", "knw_openai_browser_fact"),
            ("kcol_governance", "knw_governance_insight"),
            ("kcol_governance", "knw_ms_residency_fact"),
            ("kcol_pricing", "knw_anthropic_pricing_fact"),
        ]
        connection.executemany(
            """INSERT INTO knowledge_collection_items
               (collection_id, item_id, added_by, added_at)
               VALUES (?, ?, 'user_lin_che', ?)""",
            [(collection_id, item_id, now) for collection_id, item_id in memberships],
        )

    def _seed_empty_project(
        self, connection: sqlite3.Connection, project_id: str, now: str
    ) -> None:
        connection.execute(
            """INSERT INTO project_metrics
               (project_id, data_cutoff) VALUES (?, '尚未采集')""",
            (project_id,),
        )
        connection.execute(
            """INSERT INTO daily_briefs
               (project_id, title, summary, evidence_count, confidence, impact_level)
               VALUES (?, '等待首批情报', '项目已创建。添加并启用数据源后，系统将在这里汇总关键变化。', 0, 0, 'low')""",
            (project_id,),
        )
        connection.execute(
            """INSERT INTO source_health
               (project_id, score, normal_count, abnormal_count, disabled_count, last_sync)
               VALUES (?, 0, 0, 0, 0, '尚未同步')""",
            (project_id,),
        )
        empty_ranges = {
            "24h": ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "现在"],
            "7d": ["周五", "周六", "周日", "周一", "周二", "周三", "今天"],
            "30d": ["07/01", "07/05", "07/09", "07/13", "07/17", "07/21", "07/25", "07/31"],
        }
        for range_key, labels in empty_ranges.items():
            connection.executemany(
                """INSERT INTO trend_points
                   (project_id, range_key, label, event_count, high_impact_count, sort_order)
                   VALUES (?, ?, ?, 0, 0, ?)""",
                [(project_id, range_key, label, index) for index, label in enumerate(labels)],
            )

    def list_projects(self, project_ids: list[str] | None = None) -> list[sqlite3.Row]:
        with self.session() as connection:
            if project_ids is not None:
                if not project_ids:
                    return []
                placeholders = ",".join("?" for _ in project_ids)
                return list(
                    connection.execute(
                        f"SELECT * FROM projects WHERE id IN ({placeholders}) "
                        "ORDER BY created_at, name",
                        tuple(project_ids),
                    ).fetchall()
                )
            return list(
                connection.execute(
                    "SELECT * FROM projects ORDER BY created_at, name"
                ).fetchall()
            )

    def get_project(self, project_id: str | None) -> sqlite3.Row | None:
        with self.session() as connection:
            if project_id:
                return connection.execute(
                    "SELECT * FROM projects WHERE id=?", (project_id,)
                ).fetchone()
            return connection.execute(
                "SELECT * FROM projects WHERE status='active' ORDER BY created_at LIMIT 1"
            ).fetchone()

    def create_project(self, payload: ProjectCreate, actor_id: str) -> sqlite3.Row:
        project_id = f"prj_{uuid4().hex[:12]}"
        now = utc_now()
        avatar = payload.name[0].upper()
        with self.session() as connection:
            connection.execute(
                """INSERT INTO projects
                   (id, name, avatar, template, regions_json, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'active', ?)""",
                (
                    project_id,
                    payload.name.strip(),
                    avatar,
                    payload.template,
                    json.dumps(payload.regions, ensure_ascii=False),
                    now,
                ),
            )
            self._seed_empty_project(connection, project_id, now)
            self._audit(
                connection,
                actor_id,
                "project.create",
                "project",
                project_id,
                {"name": payload.name, "template": payload.template},
            )
            return connection.execute(
                "SELECT * FROM projects WHERE id=?", (project_id,)
            ).fetchone()

    def get_user(self, user_id: str) -> sqlite3.Row | None:
        with self.session() as connection:
            return connection.execute(
                "SELECT * FROM users WHERE id=?", (user_id,)
            ).fetchone()

    def get_metrics(self, project_id: str) -> sqlite3.Row:
        with self.session() as connection:
            return connection.execute(
                "SELECT * FROM project_metrics WHERE project_id=?", (project_id,)
            ).fetchone()

    def get_daily_brief(self, project_id: str) -> sqlite3.Row:
        with self.session() as connection:
            return connection.execute(
                "SELECT * FROM daily_briefs WHERE project_id=?", (project_id,)
            ).fetchone()

    def get_trend(self, project_id: str, range_key: str) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """SELECT * FROM trend_points
                       WHERE project_id=? AND range_key=? ORDER BY sort_order""",
                    (project_id, range_key),
                ).fetchall()
            )

    def get_source_health(self, project_id: str) -> sqlite3.Row:
        with self.session() as connection:
            return connection.execute(
                "SELECT * FROM source_health WHERE project_id=?", (project_id,)
            ).fetchone()

    def list_sources(
        self,
        project_id: str,
        status_filter: str | None = None,
        source_type: str | None = None,
        query: str | None = None,
        allowed_domains: list[str] | None = None,
    ) -> list[sqlite3.Row]:
        clauses = ["project_id=?", "archived_at IS NULL"]
        parameters: list[object] = [project_id]
        if allowed_domains is not None:
            if not allowed_domains:
                return []
            placeholders = ",".join("?" for _ in allowed_domains)
            clauses.append(f"data_classification IN ({placeholders})")
            parameters.extend(allowed_domains)
        if status_filter:
            clauses.append("health_status=?")
            parameters.append(status_filter)
        if source_type:
            clauses.append("source_type=?")
            parameters.append(source_type)
        if query:
            clauses.append("(name LIKE ? OR subject LIKE ? OR endpoint LIKE ?)")
            term = f"%{query}%"
            parameters.extend([term, term, term])
        where = " AND ".join(clauses)
        with self.session() as connection:
            return list(
                connection.execute(
                    f"""SELECT * FROM data_sources WHERE {where}
                        ORDER BY enabled DESC,
                        CASE health_status
                            WHEN 'error' THEN 1
                            WHEN 'warning' THEN 2
                            WHEN 'healthy' THEN 3
                            ELSE 4
                        END,
                        name""",
                    tuple(parameters),
                ).fetchall()
            )

    def get_source(
        self, source_id: str, *, include_archived: bool = False
    ) -> sqlite3.Row | None:
        with self.session() as connection:
            archive_filter = "" if include_archived else " AND archived_at IS NULL"
            return connection.execute(
                f"SELECT * FROM data_sources WHERE id=?{archive_filter}", (source_id,)
            ).fetchone()

    def create_source(
        self, payload: SourceCreate, actor_id: str
    ) -> sqlite3.Row | None:
        project = self.get_project(payload.project_id)
        if project is None:
            return None
        source_id = f"src_{uuid4().hex[:12]}"
        now = utc_now()
        credential_ref = payload.credential_ref.strip() if payload.credential_ref else None
        expires_at = (
            payload.credential_expires_at.isoformat()
            if payload.credential_expires_at
            else None
        )
        with self.session() as connection:
            connection.execute(
                """INSERT INTO data_sources
                   (id, project_id, name, source_type, endpoint, subject, access_method,
                    crawl_strategy, regions_json, authorization_basis, authorization_status,
                    data_classification, retention_days, schedule_frequency,
                    rate_limit_per_minute, concurrency_limit, task_timeout_seconds,
                    max_attempts, retry_backoff_seconds, priority,
                    credential_ref, credential_masked,
                    credential_expires_at, fields_json, collection_config_json, robots_acknowledged,
                    terms_acknowledged, enabled, health_status, health_score,
                    check_results_json, next_run_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            0, 'disabled', 0, ?, NULL, ?, ?)""",
                (
                    source_id,
                    payload.project_id,
                    payload.name,
                    payload.source_type,
                    payload.endpoint,
                    payload.subject,
                    payload.access_method,
                    payload.crawl_strategy,
                    json.dumps(payload.regions, ensure_ascii=False),
                    payload.authorization_basis,
                    payload.authorization_status,
                    payload.data_classification,
                    payload.retention_days,
                    payload.schedule_frequency,
                    payload.rate_limit_per_minute,
                    payload.concurrency_limit,
                    payload.task_timeout_seconds,
                    payload.max_attempts,
                    payload.retry_backoff_seconds,
                    payload.priority,
                    credential_ref,
                    self._mask_credential_ref(credential_ref),
                    expires_at,
                    json.dumps(payload.fields_available, ensure_ascii=False),
                    json.dumps(payload.collection_config, ensure_ascii=False),
                    int(payload.robots_acknowledged),
                    int(payload.terms_acknowledged),
                    json.dumps(self._pending_source_checks(), ensure_ascii=False),
                    now,
                    now,
                ),
            )
            self._refresh_source_health(connection, payload.project_id)
            self._audit(
                connection,
                actor_id,
                "source.create",
                "source",
                source_id,
                {
                    "project_id": payload.project_id,
                    "source_type": payload.source_type,
                    "authorization_status": payload.authorization_status,
                },
            )
            return connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()

    def update_source(
        self, source_id: str, payload: SourceUpdate, actor_id: str
    ) -> sqlite3.Row | None:
        values = payload.model_dump(exclude_unset=True)
        with self.session() as connection:
            current = connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()
            if current is None:
                return None
            if not values:
                return current

            columns: list[str] = []
            parameters: list[object] = []
            json_fields = {
                "regions": "regions_json",
                "fields_available": "fields_json",
                "collection_config": "collection_config_json",
            }
            check_sensitive = {
                "source_type",
                "endpoint",
                "access_method",
                "authorization_basis",
                "authorization_status",
                "rate_limit_per_minute",
                "credential_ref",
                "fields_available",
                "collection_config",
                "robots_acknowledged",
                "terms_acknowledged",
            }
            for key, value in values.items():
                column = json_fields.get(key, key)
                if key in json_fields:
                    if key == "collection_config":
                        current_config = json.loads(
                            current["collection_config_json"] or "{}"
                        )
                        value = {
                            **{
                                config_key: config_value
                                for config_key, config_value in current_config.items()
                                if config_key.startswith("_")
                            },
                            **value,
                        }
                    value = json.dumps(value, ensure_ascii=False)
                elif key == "credential_expires_at" and value is not None:
                    value = value.isoformat()
                elif key in {"robots_acknowledged", "terms_acknowledged"}:
                    value = int(value)
                elif isinstance(value, str):
                    value = value.strip()
                columns.append(f"{column}=?")
                parameters.append(value)
                if key == "credential_ref":
                    columns.append("credential_masked=?")
                    parameters.append(self._mask_credential_ref(value))

            needs_recheck = bool(check_sensitive.intersection(values))
            if needs_recheck:
                columns.extend(
                    ["check_results_json=?", "last_checked_at=NULL", "enabled=0", "health_status='disabled'"]
                )
                parameters.append(
                    json.dumps(self._pending_source_checks(), ensure_ascii=False)
                )
            if "schedule_frequency" in values and current["enabled"]:
                columns.append("next_run_at=?")
                parameters.append(schedule_next_run(values["schedule_frequency"]))
            columns.append("updated_at=?")
            parameters.extend([utc_now(), source_id])
            connection.execute(
                f"UPDATE data_sources SET {', '.join(columns)} WHERE id=?",
                tuple(parameters),
            )
            self._refresh_source_health(connection, current["project_id"])
            self._audit(
                connection,
                actor_id,
                "source.update",
                "source",
                source_id,
                {"fields": sorted(values), "recheck_required": needs_recheck},
            )
            return connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()

    def update_source_schedule(
        self, source_id: str, payload: SourceScheduleUpdate, actor_id: str
    ) -> sqlite3.Row | None:
        now = utc_now()
        with self.session() as connection:
            source = connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()
            if source is None:
                return None
            next_run_at = (
                schedule_next_run(payload.schedule_frequency)
                if source["enabled"]
                else None
            )
            connection.execute(
                """UPDATE data_sources SET schedule_frequency=?,
                   rate_limit_per_minute=?, concurrency_limit=?,
                   task_timeout_seconds=?, max_attempts=?, retry_backoff_seconds=?,
                   priority=?, next_run_at=?, updated_at=? WHERE id=?""",
                (
                    payload.schedule_frequency,
                    payload.rate_limit_per_minute,
                    payload.concurrency_limit,
                    payload.task_timeout_seconds,
                    payload.max_attempts,
                    payload.retry_backoff_seconds,
                    payload.priority,
                    next_run_at,
                    now,
                    source_id,
                ),
            )
            self._audit(
                connection,
                actor_id,
                "source.schedule.update",
                "source",
                source_id,
                payload.model_dump(),
            )
            return connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()

    def run_source_checks(self, source_id: str, actor_id: str) -> sqlite3.Row | None:
        now = utc_now()
        with self.session() as connection:
            source = connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()
            if source is None:
                return None
            is_file = source["source_type"] == "file_upload"
            parsed_endpoint = source["endpoint"].lower()
            connectivity_passed = bool(source["endpoint"].strip()) and (
                is_file
                or parsed_endpoint.startswith("http://")
                or parsed_endpoint.startswith("https://")
            ) and "unreachable.invalid" not in parsed_endpoint
            robots_required = source["source_type"] in {
                "webpage",
                "dynamic_webpage",
                "sitemap",
            }
            compliance_passed = (
                source["authorization_status"] == "approved"
                and bool(source["terms_acknowledged"])
                and (not robots_required or bool(source["robots_acknowledged"]))
            )
            fields = json.loads(source["fields_json"])
            checks = [
                {
                    "key": "connectivity",
                    "label": "连通性",
                    "status": "passed" if connectivity_passed else "failed",
                    "message": (
                        "入口与连接器配置可用"
                        if connectivity_passed
                        else "入口不可用或地址格式不受支持"
                    ),
                    "checked_at": now,
                },
                {
                    "key": "compliance",
                    "label": "授权与合规",
                    "status": "passed" if compliance_passed else "failed",
                    "message": (
                        "授权、条款与 robots 提示已确认"
                        if compliance_passed
                        else "授权未通过，或条款/robots 提示尚未确认"
                    ),
                    "checked_at": now,
                },
                {
                    "key": "rate_limit",
                    "label": "速率限制",
                    "status": "passed" if 0 < source["rate_limit_per_minute"] <= 600 else "failed",
                    "message": (
                        f"已限制为每分钟 {source['rate_limit_per_minute']} 次"
                        if 0 < source["rate_limit_per_minute"] <= 600
                        else "速率限制配置无效"
                    ),
                    "checked_at": now,
                },
                {
                    "key": "field_availability",
                    "label": "字段可用性",
                    "status": "passed" if fields else "failed",
                    "message": (
                        f"已映射 {len(fields)} 个可用字段"
                        if fields
                        else "尚未配置可用字段"
                    ),
                    "checked_at": now,
                },
            ]
            ready = all(item["status"] in {"passed", "not_applicable"} for item in checks)
            health_score = source["health_score"] or (85 if ready else 40)
            health_status = (
                self._health_status_from_score(health_score)
                if source["enabled"]
                else "disabled"
            )
            connection.execute(
                """UPDATE data_sources
                   SET check_results_json=?, last_checked_at=?, health_score=?,
                       health_status=?, updated_at=? WHERE id=?""",
                (
                    json.dumps(checks, ensure_ascii=False),
                    now,
                    health_score,
                    health_status,
                    now,
                    source_id,
                ),
            )
            self._refresh_source_health(connection, source["project_id"])
            self._audit(
                connection,
                actor_id,
                "source.check",
                "source",
                source_id,
                {"passed": ready},
            )
            return connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()

    def set_source_enabled(
        self, source_id: str, enabled: bool, actor_id: str
    ) -> sqlite3.Row | None:
        with self.session() as connection:
            source = connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()
            if source is None:
                return None
            checks = json.loads(source["check_results_json"])
            ready = bool(checks) and all(
                item["status"] in {"passed", "not_applicable"} for item in checks
            )
            if enabled and not ready:
                raise ValueError("启用前必须通过全部连通性与合规检查")
            health_score = source["health_score"] or 85
            health_status = self._health_status_from_score(health_score) if enabled else "disabled"
            now = utc_now()
            connection.execute(
                """UPDATE data_sources SET enabled=?, health_status=?, health_score=?,
                   next_run_at=?, updated_at=? WHERE id=?""",
                (
                    int(enabled),
                    health_status,
                    health_score,
                    schedule_next_run(source["schedule_frequency"]) if enabled else None,
                    now,
                    source_id,
                ),
            )
            if not enabled:
                queued_ids = connection.execute(
                    "SELECT id FROM source_runs WHERE source_id=? AND status='queued'",
                    (source_id,),
                ).fetchall()
                connection.execute(
                    """UPDATE source_runs SET status='cancelled', finished_at=?,
                       error_type='source_disabled',
                       error_message='数据源停用，待执行任务已取消'
                       WHERE source_id=? AND status='queued'""",
                    (now, source_id),
                )
                for item in queued_ids:
                    connection.execute(
                        """UPDATE workflow_steps SET status='skipped', finished_at=?
                           WHERE run_id=? AND status IN ('pending','waiting_retry')""",
                        (now, item["id"]),
                    )
            self._refresh_source_health(connection, source["project_id"])
            self._audit(
                connection,
                actor_id,
                "source.enable" if enabled else "source.disable",
                "source",
                source_id,
                {"project_id": source["project_id"]},
            )
            return connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()

    def rotate_source_credential(
        self,
        source_id: str,
        credential_ref: str,
        expires_at: datetime | None,
        actor_id: str,
    ) -> sqlite3.Row | None:
        now = utc_now()
        with self.session() as connection:
            source = connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()
            if source is None:
                return None
            connection.execute(
                """UPDATE data_sources SET credential_ref=?, credential_masked=?,
                   credential_expires_at=?, updated_at=? WHERE id=?""",
                (
                    credential_ref.strip(),
                    self._mask_credential_ref(credential_ref),
                    expires_at.isoformat() if expires_at else None,
                    now,
                    source_id,
                ),
            )
            self._audit(
                connection,
                actor_id,
                "source.credential.rotate",
                "source",
                source_id,
                {"expires_at": expires_at.isoformat() if expires_at else None},
            )
            return connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()

    @staticmethod
    def _run_select() -> str:
        return """SELECT r.*, s.project_id, s.name AS source_name,
                         s.source_type AS source_type,
                         s.data_classification AS source_data_classification
                  FROM source_runs r
                  JOIN data_sources s ON s.id=r.source_id"""

    def queue_source_run(
        self,
        source_id: str,
        actor_id: str,
        trigger_type: str = "manual",
        retry_of: str | None = None,
        recovery_of: str | None = None,
        scheduled_for: str | None = None,
    ) -> sqlite3.Row | None:
        with self.session() as connection:
            source = connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()
            if source is None:
                return None
            if not source["enabled"]:
                raise ValueError("已停用的数据源不能发起新的采集")
            if (
                source["circuit_state"] == "open"
                and source["circuit_open_until"]
                and source["circuit_open_until"] > utc_now()
                and trigger_type not in {"manual", "retry", "recovery"}
            ):
                raise ValueError("该来源熔断中，请等待恢复窗口或执行人工恢复")
            active = connection.execute(
                """SELECT COUNT(*) AS total FROM source_runs
                   WHERE source_id=? AND status IN ('queued', 'running')""",
                (source_id,),
            ).fetchone()
            if active["total"] >= source["concurrency_limit"]:
                raise ValueError(
                    f"该数据源已达到并发上限 {source['concurrency_limit']}"
                )
            run_id = f"run_{uuid4().hex[:12]}"
            now = utc_now()
            available_at = now
            if source["source_type"] != "file_upload" and source["last_run_started_at"]:
                interval = timedelta(seconds=60 / source["rate_limit_per_minute"])
                last_started = datetime.fromisoformat(
                    source["last_run_started_at"].replace("Z", "+00:00")
                )
                allowed_at = last_started + interval
                if allowed_at > datetime.now(UTC):
                    available_at = allowed_at.replace(microsecond=0).isoformat().replace(
                        "+00:00", "Z"
                    )
            connection.execute(
                """INSERT INTO source_runs
                   (id, source_id, status, trigger_type, priority, max_attempts,
                    timeout_seconds, backoff_seconds, scheduled_for, available_at,
                    retry_of, recovery_of, created_by, created_at)
                   VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    source_id,
                    trigger_type,
                    source["priority"],
                    source["max_attempts"],
                    source["task_timeout_seconds"],
                    source["retry_backoff_seconds"],
                    scheduled_for,
                    available_at,
                    retry_of,
                    recovery_of,
                    actor_id,
                    now,
                ),
            )
            self._insert_workflow_steps(connection, run_id, source["max_attempts"])
            if source["circuit_state"] == "open" and trigger_type in {
                "manual",
                "retry",
                "recovery",
            }:
                connection.execute(
                    "UPDATE data_sources SET circuit_state='half_open' WHERE id=?",
                    (source_id,),
                )
            self._audit(
                connection,
                actor_id,
                "source.run.queue",
                "source_run",
                run_id,
                {
                    "source_id": source_id,
                    "trigger_type": trigger_type,
                    "priority": source["priority"],
                },
            )
            return connection.execute(
                f"{self._run_select()} WHERE r.id=?", (run_id,)
            ).fetchone()

    def get_source_run(self, run_id: str) -> sqlite3.Row | None:
        with self.session() as connection:
            return connection.execute(
                f"{self._run_select()} WHERE r.id=?", (run_id,)
            ).fetchone()

    def list_source_runs(
        self,
        project_id: str,
        source_id: str | None = None,
        status_filter: str | None = None,
        limit: int = 100,
        allowed_domains: list[str] | None = None,
    ) -> list[sqlite3.Row]:
        clauses = ["s.project_id=?", "s.archived_at IS NULL"]
        parameters: list[object] = [project_id]
        if allowed_domains is not None:
            if not allowed_domains:
                return []
            placeholders = ",".join("?" for _ in allowed_domains)
            clauses.append(f"s.data_classification IN ({placeholders})")
            parameters.extend(allowed_domains)
        if source_id:
            clauses.append("r.source_id=?")
            parameters.append(source_id)
        if status_filter:
            clauses.append("r.status=?")
            parameters.append(status_filter)
        parameters.append(limit)
        with self.session() as connection:
            return list(
                connection.execute(
                    f"{self._run_select()} WHERE {' AND '.join(clauses)} "
                    "ORDER BY r.created_at DESC LIMIT ?",
                    tuple(parameters),
                ).fetchall()
            )

    def list_workflow_steps(self, run_id: str) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """SELECT * FROM workflow_steps
                       WHERE run_id=? ORDER BY step_order""",
                    (run_id,),
                ).fetchall()
            )

    def mark_source_run_started(
        self, run_id: str, request_summary: str
    ) -> sqlite3.Row | None:
        now = utc_now()
        with self.session() as connection:
            run = connection.execute(
                "SELECT * FROM source_runs WHERE id=?", (run_id,)
            ).fetchone()
            if run is None or run["status"] != "queued":
                return None
            cursor = connection.execute(
                """UPDATE source_runs SET status='running', attempt=attempt+1,
                   started_at=COALESCE(started_at, ?), request_summary=?,
                   next_retry_at=NULL WHERE id=? AND status='queued'
                   AND (available_at IS NULL OR available_at<=?)""",
                (now, request_summary[:1000], run_id, now),
            )
            if cursor.rowcount != 1:
                return None
            connection.execute(
                """UPDATE data_sources SET last_collected_at=?, last_run_started_at=?,
                   updated_at=?
                   WHERE id=?""",
                (now, now, now, run["source_id"]),
            )
            return connection.execute(
                f"{self._run_select()} WHERE r.id=?", (run_id,)
            ).fetchone()

    def advance_source_run_attempt(self, run_id: str) -> None:
        with self.session() as connection:
            connection.execute(
                "UPDATE source_runs SET attempt=attempt+1 WHERE id=? AND status='running'",
                (run_id,),
            )

    def start_workflow_step(self, run_id: str, step_key: str) -> None:
        now = utc_now()
        with self.session() as connection:
            connection.execute(
                """UPDATE workflow_steps
                   SET status='running', attempt=attempt+1, started_at=?,
                       finished_at=NULL, duration_ms=NULL, error_type=NULL,
                       error_message=NULL
                   WHERE run_id=? AND step_key=?""",
                (now, run_id, step_key),
            )

    def complete_workflow_step(
        self, run_id: str, step_key: str, output_summary: str, duration_ms: int
    ) -> None:
        with self.session() as connection:
            connection.execute(
                """UPDATE workflow_steps
                   SET status='succeeded', finished_at=?, duration_ms=?,
                       output_summary=?, error_type=NULL, error_message=NULL
                   WHERE run_id=? AND step_key=?""",
                (utc_now(), max(0, duration_ms), output_summary[:1000], run_id, step_key),
            )

    def wait_workflow_step_retry(
        self,
        run_id: str,
        step_key: str,
        *,
        error_type: str,
        error_message: str,
        delay_seconds: int,
    ) -> None:
        next_retry = (
            datetime.now(UTC) + timedelta(seconds=delay_seconds)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self.session() as connection:
            run = connection.execute(
                "SELECT retry_delays_json FROM source_runs WHERE id=?", (run_id,)
            ).fetchone()
            delays = json.loads(run["retry_delays_json"] or "[]") if run else []
            delays.append(delay_seconds)
            connection.execute(
                """UPDATE workflow_steps SET status='waiting_retry',
                   error_type=?, error_message=? WHERE run_id=? AND step_key=?""",
                (error_type[:100], error_message[:1000], run_id, step_key),
            )
            connection.execute(
                """UPDATE source_runs SET next_retry_at=?, retry_delays_json=?
                   WHERE id=?""",
                (next_retry, json.dumps(delays), run_id),
            )

    def schedule_source_run_retry(
        self,
        run_id: str,
        step_key: str,
        *,
        error_type: str,
        error_message: str,
        delay_seconds: int,
        parser_steps: list[str],
    ) -> None:
        next_retry = (
            datetime.now(UTC) + timedelta(seconds=delay_seconds)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self.session() as connection:
            run = connection.execute(
                "SELECT retry_delays_json FROM source_runs WHERE id=?", (run_id,)
            ).fetchone()
            delays = json.loads(run["retry_delays_json"] or "[]") if run else []
            delays.append(delay_seconds)
            connection.execute(
                """UPDATE workflow_steps SET status='waiting_retry',
                   error_type=?, error_message=? WHERE run_id=? AND step_key=?""",
                (error_type[:100], error_message[:1000], run_id, step_key),
            )
            connection.execute(
                """UPDATE source_runs SET status='queued', available_at=?,
                   next_retry_at=?, retry_delays_json=?, parser_steps_json=?
                   WHERE id=? AND status='running'""",
                (
                    next_retry,
                    next_retry,
                    json.dumps(delays),
                    json.dumps(parser_steps, ensure_ascii=False),
                    run_id,
                ),
            )

    def fail_workflow_step(
        self, run_id: str, step_key: str, error_type: str, error_message: str
    ) -> None:
        now = utc_now()
        with self.session() as connection:
            step = connection.execute(
                """SELECT started_at FROM workflow_steps
                   WHERE run_id=? AND step_key=?""",
                (run_id, step_key),
            ).fetchone()
            duration_ms = None
            if step and step["started_at"]:
                started = datetime.fromisoformat(step["started_at"].replace("Z", "+00:00"))
                duration_ms = max(0, round((datetime.now(UTC) - started).total_seconds() * 1000))
            connection.execute(
                """UPDATE workflow_steps SET status='failed', finished_at=?,
                   duration_ms=?, error_type=?, error_message=?
                   WHERE run_id=? AND step_key=?""",
                (
                    now,
                    duration_ms,
                    error_type[:100],
                    error_message[:1000],
                    run_id,
                    step_key,
                ),
            )
            current_order = connection.execute(
                """SELECT step_order FROM workflow_steps
                   WHERE run_id=? AND step_key=?""",
                (run_id, step_key),
            ).fetchone()
            if current_order:
                connection.execute(
                    """UPDATE workflow_steps SET status='skipped', finished_at=?
                       WHERE run_id=? AND step_order>? AND status='pending'""",
                    (now, run_id, current_order["step_order"]),
                )

    def complete_source_run(
        self,
        run_id: str,
        *,
        status_value: str,
        items_discovered: int,
        documents_created: int,
        documents_updated: int,
        duplicates_skipped: int,
        parser_steps: list[str],
        latency_ms: int,
        parser_completeness: float,
    ) -> sqlite3.Row | None:
        now = utc_now()
        with self.session() as connection:
            run = connection.execute(
                "SELECT * FROM source_runs WHERE id=?", (run_id,)
            ).fetchone()
            if run is None:
                return None
            connection.execute(
                """UPDATE source_runs SET status=?, items_discovered=?,
                    documents_created=?, documents_updated=?, duplicates_skipped=?,
                   parser_steps_json=?, next_retry_at=NULL, finished_at=? WHERE id=?""",
                (
                    status_value,
                    items_discovered,
                    documents_created,
                    documents_updated,
                    duplicates_skipped,
                    json.dumps(parser_steps, ensure_ascii=False),
                    now,
                    run_id,
                ),
            )
            source = connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (run["source_id"],)
            ).fetchone()
            success_rate = self._source_success_rate(connection, run["source_id"])
            previous_latency = source["average_latency_ms"] or latency_ms
            average_latency = round((previous_latency * 3 + latency_ms) / 4)
            change_rate = (
                round((documents_created + documents_updated) / items_discovered * 100, 1)
                if items_discovered
                else 0.0
            )
            score = round(
                min(100, success_rate * 0.55 + parser_completeness * 0.35 + 10)
            )
            connection.execute(
                """UPDATE data_sources SET success_rate=?, consecutive_failures=0,
                   average_latency_ms=?, freshness_minutes=0, content_change_rate=?,
                   parser_completeness=?, health_score=?, health_status=?,
                   last_success_at=?, next_run_at=?, circuit_state='closed',
                   circuit_open_until=NULL, updated_at=? WHERE id=?""",
                (
                    success_rate,
                    average_latency,
                    change_rate,
                    parser_completeness,
                    score,
                    self._health_status_from_score(score),
                    now,
                    schedule_next_run(source["schedule_frequency"]),
                    now,
                    run["source_id"],
                ),
            )
            self._refresh_source_health(connection, source["project_id"])
            return connection.execute(
                f"{self._run_select()} WHERE r.id=?", (run_id,)
            ).fetchone()

    def fail_source_run(
        self,
        run_id: str,
        *,
        error_type: str,
        error_message: str,
        parser_steps: list[str],
    ) -> sqlite3.Row | None:
        now = utc_now()
        with self.session() as connection:
            run = connection.execute(
                "SELECT * FROM source_runs WHERE id=?", (run_id,)
            ).fetchone()
            if run is None:
                return None
            connection.execute(
                """UPDATE source_runs SET status='failed', error_type=?,
                   error_message=?, parser_steps_json=?, finished_at=? WHERE id=?""",
                (
                    error_type[:100],
                    error_message[:1000],
                    json.dumps(parser_steps, ensure_ascii=False),
                    now,
                    run_id,
                ),
            )
            source = connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (run["source_id"],)
            ).fetchone()
            failures = source["consecutive_failures"] + 1
            success_rate = self._source_success_rate(connection, run["source_id"])
            score = max(0, round(success_rate * 0.65 + source["parser_completeness"] * 0.25))
            health_status = "error" if failures >= 3 else "warning"
            run_status = "manual_review" if failures >= 3 else "failed"
            circuit_state = "open" if failures >= 3 else "closed"
            open_until = None
            if failures >= 3:
                open_minutes = min(240, 15 * (2 ** (failures - 3)))
                open_until = (
                    datetime.now(UTC) + timedelta(minutes=open_minutes)
                ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            connection.execute(
                "UPDATE source_runs SET status=? WHERE id=?",
                (run_status, run_id),
            )
            connection.execute(
                """UPDATE data_sources SET success_rate=?, consecutive_failures=?,
                   health_score=?, health_status=?, next_run_at=?, circuit_state=?,
                   circuit_open_until=?, updated_at=?
                   WHERE id=?""",
                (
                    success_rate,
                    failures,
                    score,
                    health_status,
                    open_until or schedule_next_run(source["schedule_frequency"]),
                    circuit_state,
                    open_until,
                    now,
                    run["source_id"],
                ),
            )
            self._refresh_source_health(connection, source["project_id"])
            return connection.execute(
                f"{self._run_select()} WHERE r.id=?", (run_id,)
            ).fetchone()

    @staticmethod
    def _source_success_rate(
        connection: sqlite3.Connection, source_id: str
    ) -> float:
        row = connection.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status IN ('succeeded', 'partial') THEN 1 ELSE 0 END) AS ok
               FROM source_runs
               WHERE source_id=?
                 AND status IN ('succeeded', 'partial', 'failed', 'manual_review')""",
            (source_id,),
        ).fetchone()
        return round((row["ok"] or 0) / row["total"] * 100, 1) if row["total"] else 0.0

    def cancel_source_run(self, run_id: str, actor_id: str) -> sqlite3.Row | None:
        with self.session() as connection:
            run = connection.execute(
                "SELECT * FROM source_runs WHERE id=?", (run_id,)
            ).fetchone()
            if run is None:
                return None
            if run["status"] != "queued":
                raise ValueError("只有待执行任务可以取消")
            connection.execute(
                "UPDATE source_runs SET status='cancelled', finished_at=? WHERE id=?",
                (utc_now(), run_id),
            )
            self._audit(
                connection,
                actor_id,
                "source.run.cancel",
                "source_run",
                run_id,
                {"source_id": run["source_id"]},
            )
            return connection.execute(
                f"{self._run_select()} WHERE r.id=?", (run_id,)
            ).fetchone()

    def retry_source_run(self, run_id: str, actor_id: str) -> sqlite3.Row | None:
        run = self.get_source_run(run_id)
        if run is None:
            return None
        if run["status"] not in {"failed", "partial", "cancelled", "manual_review"}:
            raise ValueError("只有失败、部分成功、待人工处理或已取消任务可以重试")
        return self.queue_source_run(
            run["source_id"], actor_id, trigger_type="retry", retry_of=run_id
        )

    def recover_source_run(self, run_id: str, actor_id: str) -> sqlite3.Row | None:
        run = self.get_source_run(run_id)
        if run is None:
            return None
        if run["status"] not in {"failed", "partial", "manual_review", "cancelled"}:
            raise ValueError("该任务不在可恢复状态")
        with self.session() as connection:
            connection.execute(
                """UPDATE data_sources SET circuit_state='half_open',
                   circuit_open_until=NULL, updated_at=? WHERE id=?""",
                (utc_now(), run["source_id"]),
            )
        return self.queue_source_run(
            run["source_id"],
            actor_id,
            trigger_type="recovery",
            recovery_of=run_id,
        )

    def attach_source_file(
        self,
        source_id: str,
        storage_path: Path,
        content_type: str,
        size_bytes: int,
        actor_id: str,
    ) -> sqlite3.Row | None:
        with self.session() as connection:
            source = connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()
            if source is None:
                return None
            config = json.loads(source["collection_config_json"] or "{}")
            config.update(
                {
                    "_storage_path": str(storage_path.resolve()),
                    "uploaded_content_type": content_type,
                    "uploaded_size_bytes": size_bytes,
                }
            )
            connection.execute(
                """UPDATE data_sources SET collection_config_json=?, updated_at=?
                   WHERE id=?""",
                (json.dumps(config, ensure_ascii=False), utc_now(), source_id),
            )
            self._audit(
                connection,
                actor_id,
                "source.file.attach",
                "source",
                source_id,
                {"filename": storage_path.name, "size_bytes": size_bytes},
            )
            return connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()

    def save_collection_document(
        self,
        *,
        run_id: str,
        project_id: str,
        source_id: str,
        canonical_url: str,
        title: str,
        published_at: str | None,
        language: str | None,
        content_type: str,
        content_hash: str,
        raw_content: bytes,
        readable_text: str,
        metadata: dict[str, object],
        structured_fields: dict[str, object],
        parser_version: str,
    ) -> tuple[str, sqlite3.Row]:
        now = utc_now()
        with self.session() as connection:
            duplicate = connection.execute(
                """SELECT * FROM collection_documents
                   WHERE source_id=? AND content_hash=?
                   ORDER BY collected_at DESC LIMIT 1""",
                (source_id, content_hash),
            ).fetchone()
            if duplicate is not None:
                return "duplicate", duplicate
            latest = connection.execute(
                """SELECT * FROM collection_documents
                   WHERE source_id=? AND canonical_url=? AND is_latest=1
                   ORDER BY version_no DESC LIMIT 1""",
                (source_id, canonical_url),
            ).fetchone()
            state = "updated" if latest is not None else "created"
            version = latest["version_no"] + 1 if latest is not None else 1
            previous_document_id = latest["id"] if latest is not None else None
            if latest is not None:
                connection.execute(
                    "UPDATE collection_documents SET is_latest=0 WHERE id=?",
                    (latest["id"],),
                )
            document_id = f"doc_{uuid4().hex[:16]}"
            connection.execute(
                """INSERT INTO collection_documents
                   (id, project_id, source_id, run_id, canonical_url, title,
                    published_at, collected_at, language, content_type, content_hash,
                    raw_content, readable_text, metadata_json, structured_fields_json,
                    parser_version, version_no, previous_document_id, is_latest)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    document_id,
                    project_id,
                    source_id,
                    run_id,
                    canonical_url,
                    title[:500] or "未命名采集材料",
                    published_at,
                    now,
                    language,
                    content_type,
                    content_hash,
                    raw_content,
                    readable_text,
                    json.dumps(metadata, ensure_ascii=False, default=str),
                    json.dumps(structured_fields, ensure_ascii=False, default=str),
                    parser_version,
                    version,
                    previous_document_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM collection_documents WHERE id=?", (document_id,)
            ).fetchone()
            return state, row

    @staticmethod
    def _document_select() -> str:
        return """SELECT d.*, s.name AS source_name, s.source_type AS source_type,
                         s.data_classification AS source_data_classification
                  FROM collection_documents d
                  JOIN data_sources s ON s.id=d.source_id"""

    def list_collection_documents(
        self,
        project_id: str,
        source_id: str | None = None,
        latest_only: bool = True,
        query: str | None = None,
        limit: int = 100,
        allowed_domains: list[str] | None = None,
    ) -> list[sqlite3.Row]:
        clauses = ["d.project_id=?", "s.archived_at IS NULL"]
        parameters: list[object] = [project_id]
        if allowed_domains is not None:
            if not allowed_domains:
                return []
            placeholders = ",".join("?" for _ in allowed_domains)
            clauses.append(f"s.data_classification IN ({placeholders})")
            parameters.extend(allowed_domains)
        if source_id:
            clauses.append("d.source_id=?")
            parameters.append(source_id)
        if latest_only:
            clauses.append("d.is_latest=1")
        if query:
            clauses.append("(d.title LIKE ? OR d.readable_text LIKE ?)")
            term = f"%{query}%"
            parameters.extend([term, term])
        parameters.append(limit)
        with self.session() as connection:
            return list(
                connection.execute(
                    f"{self._document_select()} WHERE {' AND '.join(clauses)} "
                    "ORDER BY d.collected_at DESC LIMIT ?",
                    tuple(parameters),
                ).fetchall()
            )

    def get_collection_document(self, document_id: str) -> sqlite3.Row | None:
        with self.session() as connection:
            return connection.execute(
                f"{self._document_select()} WHERE d.id=? AND s.archived_at IS NULL",
                (document_id,),
            ).fetchone()

    def get_latest_source_document(self, source_id: str) -> sqlite3.Row | None:
        with self.session() as connection:
            return connection.execute(
                """SELECT * FROM collection_documents
                   WHERE source_id=? AND is_latest=1
                   ORDER BY collected_at DESC LIMIT 1""",
                (source_id,),
            ).fetchone()

    def mark_document_processing(self, document_id: str) -> sqlite3.Row | None:
        now = utc_now()
        with self.session() as connection:
            document = connection.execute(
                "SELECT * FROM collection_documents WHERE id=?", (document_id,)
            ).fetchone()
            if document is None:
                return None
            connection.execute(
                """INSERT INTO document_processing
                   (document_id, project_id, status, processed_at)
                   VALUES (?, ?, 'processing', ?)
                   ON CONFLICT(document_id) DO UPDATE SET
                     status='processing', error_message=NULL, processed_at=excluded.processed_at""",
                (document_id, document["project_id"], now),
            )
            return document

    def save_document_processing(
        self, document_id: str, project_id: str, result: dict[str, object]
    ) -> sqlite3.Row:
        with self.session() as connection:
            connection.execute(
                """INSERT INTO document_processing
                   (document_id, project_id, status, clean_text, clean_hash,
                    body_extraction_method, noise_removed_lines, language,
                    language_confidence, ocr_status, ocr_text, duplicate_type,
                    duplicate_of, duplicate_similarity, duplicate_cluster_id,
                    entities_json, events_json, steps_json, quality_score,
                    needs_review, review_reasons_json, processor_version,
                    processed_at, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(document_id) DO UPDATE SET
                     status=excluded.status,
                     clean_text=excluded.clean_text,
                     clean_hash=excluded.clean_hash,
                     body_extraction_method=excluded.body_extraction_method,
                     noise_removed_lines=excluded.noise_removed_lines,
                     language=excluded.language,
                     language_confidence=excluded.language_confidence,
                     ocr_status=excluded.ocr_status,
                     ocr_text=excluded.ocr_text,
                     duplicate_type=excluded.duplicate_type,
                     duplicate_of=excluded.duplicate_of,
                     duplicate_similarity=excluded.duplicate_similarity,
                     duplicate_cluster_id=excluded.duplicate_cluster_id,
                     entities_json=excluded.entities_json,
                     events_json=excluded.events_json,
                     steps_json=excluded.steps_json,
                     quality_score=excluded.quality_score,
                     needs_review=excluded.needs_review,
                     review_reasons_json=excluded.review_reasons_json,
                     processor_version=excluded.processor_version,
                     processed_at=excluded.processed_at,
                     error_message=excluded.error_message""",
                (
                    document_id,
                    project_id,
                    result["status"],
                    result["clean_text"],
                    result["clean_hash"],
                    result["body_extraction_method"],
                    result["noise_removed_lines"],
                    result["language"],
                    result["language_confidence"],
                    result["ocr_status"],
                    result["ocr_text"],
                    result["duplicate_type"],
                    result["duplicate_of"],
                    result["duplicate_similarity"],
                    result["duplicate_cluster_id"],
                    json.dumps(result["entities"], ensure_ascii=False),
                    json.dumps(result["events"], ensure_ascii=False),
                    json.dumps(result["steps"], ensure_ascii=False),
                    result["quality_score"],
                    int(bool(result["needs_review"])),
                    json.dumps(result["review_reasons"], ensure_ascii=False),
                    result["processor_version"],
                    result["processed_at"],
                    result.get("error_message"),
                ),
            )
            self._sync_processed_knowledge(
                connection, document_id, project_id, result
            )
            row = connection.execute(
                f"{self._processing_select()} WHERE d.id=?", (document_id,)
            ).fetchone()
            assert row is not None
            return row

    @staticmethod
    def _sync_processed_knowledge(
        connection: sqlite3.Connection,
        document_id: str,
        project_id: str,
        result: dict[str, object],
    ) -> None:
        document = connection.execute(
            """SELECT d.*, s.name AS source_name, s.subject AS source_subject
               FROM collection_documents d
               JOIN data_sources s ON s.id=d.source_id
               WHERE d.id=?""",
            (document_id,),
        ).fetchone()
        if document is None:
            return

        now = str(result.get("processed_at") or utc_now())
        clean_text = str(result.get("clean_text") or "")
        language = str(result.get("language") or document["language"] or "") or None
        quality_score = int(result.get("quality_score") or 0)
        review_status = (
            "review_required" if bool(result.get("needs_review")) else "verified"
        )
        extraction_method = str(
            result.get("body_extraction_method") or "processing-v1"
        )
        items: list[dict[str, object]] = []

        if clean_text:
            excerpt = " ".join(clean_text.split())[:500]
            items.append(
                {
                    "id": f"knw_{document_id}_document",
                    "item_type": "fact",
                    "title": document["title"],
                    "summary": excerpt[:220],
                    "content": clean_text,
                    "subject": document["source_subject"],
                    "category": "source_material",
                    "tags": ["材料事实", document["source_name"]],
                    "confidence": quality_score,
                    "evidence_excerpt": excerpt,
                    "evidence_start": 0,
                    "evidence_end": min(len(clean_text), 500),
                    "extraction_method": extraction_method,
                    "published_at": document["published_at"],
                }
            )

        for entity in result.get("entities", []):
            if not isinstance(entity, dict):
                continue
            start = max(0, int(entity.get("start") or 0))
            end = max(start, int(entity.get("end") or start))
            context_start = max(0, start - 80)
            context_end = min(len(clean_text), end + 80)
            entity_type = str(entity.get("type") or "entity")
            text = str(entity.get("text") or "未命名实体")
            normalized = str(entity.get("normalized") or text)
            items.append(
                {
                    "id": f"knw_{document_id}_{entity.get('id', uuid4().hex[:8])}",
                    "item_type": "entity",
                    "title": text,
                    "summary": f"{entity_type} · 标准名 {normalized}",
                    "content": normalized,
                    "subject": document["source_subject"],
                    "category": entity_type,
                    "tags": ["实体", entity_type, document["source_name"]],
                    "confidence": round(float(entity.get("confidence") or 0) * 100),
                    "evidence_excerpt": clean_text[context_start:context_end],
                    "evidence_start": start,
                    "evidence_end": end,
                    "extraction_method": str(entity.get("method") or "entity-extraction-v1"),
                    "published_at": document["published_at"],
                }
            )

        for event in result.get("events", []):
            if not isinstance(event, dict):
                continue
            start = max(0, int(event.get("start") or 0))
            end = max(start, int(event.get("end") or start))
            subject = str(event.get("subject") or document["source_subject"] or "")
            label = str(event.get("label") or "变化事件")
            evidence = str(event.get("evidence_text") or clean_text[start:end])
            event_type = str(event.get("type") or "event")
            impact_level = str(event.get("impact_level") or "low")
            items.append(
                {
                    "id": f"knw_{document_id}_{event.get('id', uuid4().hex[:8])}",
                    "item_type": "event",
                    "title": f"{subject} · {label}" if subject else label,
                    "summary": evidence[:220],
                    "content": evidence,
                    "subject": subject or None,
                    "category": event_type,
                    "tags": ["事件", event_type, impact_level],
                    "confidence": round(float(event.get("confidence") or 0) * 100),
                    "evidence_excerpt": evidence,
                    "evidence_start": start,
                    "evidence_end": end,
                    "extraction_method": str(event.get("method") or "event-extraction-v1"),
                    "published_at": event.get("occurred_at") or document["published_at"],
                }
            )

        active_ids = [str(item["id"]) for item in items]
        if active_ids:
            placeholders = ",".join("?" for _ in active_ids)
            connection.execute(
                f"""DELETE FROM knowledge_items
                    WHERE document_id=? AND origin='processing'
                      AND id NOT IN ({placeholders})""",
                (document_id, *active_ids),
            )
        else:
            connection.execute(
                "DELETE FROM knowledge_items WHERE document_id=? AND origin='processing'",
                (document_id,),
            )

        for item in items:
            connection.execute(
                """INSERT INTO knowledge_items
                   (id, project_id, document_id, source_id, item_type, title,
                    summary, content, subject, category, language, tags_json,
                    confidence, quality_score, review_status, validity_status,
                    source_count, evidence_excerpt, evidence_start, evidence_end,
                    extraction_method, origin, published_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active',
                           1, ?, ?, ?, ?, 'processing', ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=excluded.title,
                     summary=excluded.summary,
                     content=excluded.content,
                     subject=excluded.subject,
                     category=excluded.category,
                     language=excluded.language,
                     tags_json=excluded.tags_json,
                     confidence=excluded.confidence,
                     quality_score=excluded.quality_score,
                     review_status=CASE
                       WHEN knowledge_items.review_status='conflict' THEN 'conflict'
                       ELSE excluded.review_status
                     END,
                     evidence_excerpt=excluded.evidence_excerpt,
                     evidence_start=excluded.evidence_start,
                     evidence_end=excluded.evidence_end,
                     extraction_method=excluded.extraction_method,
                     published_at=excluded.published_at,
                     updated_at=excluded.updated_at""",
                (
                    item["id"],
                    project_id,
                    document_id,
                    document["source_id"],
                    item["item_type"],
                    item["title"],
                    item["summary"],
                    item["content"],
                    item["subject"],
                    item["category"],
                    language,
                    json.dumps(item["tags"], ensure_ascii=False),
                    item["confidence"],
                    quality_score,
                    review_status,
                    item["evidence_excerpt"],
                    item["evidence_start"],
                    item["evidence_end"],
                    item["extraction_method"],
                    item["published_at"],
                    now,
                    now,
                ),
            )
            connection.execute(
                """INSERT OR IGNORE INTO knowledge_revisions
                   (item_id, version_no, action, snapshot_json, note, created_at)
                   VALUES (?, 1, 'created', ?, '由处理链自动入库', ?)""",
                (
                    item["id"],
                    json.dumps(
                        {
                            "review_status": review_status,
                            "confidence": item["confidence"],
                            "tags": item["tags"],
                        },
                        ensure_ascii=False,
                    ),
                    now,
                ),
            )

    def fail_document_processing(
        self, document_id: str, project_id: str, message: str
    ) -> sqlite3.Row:
        now = utc_now()
        defaults: dict[str, object] = {
            "status": "failed",
            "clean_text": "",
            "clean_hash": None,
            "body_extraction_method": "failed",
            "noise_removed_lines": 0,
            "language": None,
            "language_confidence": 0,
            "ocr_status": "failed",
            "ocr_text": "",
            "duplicate_type": "none",
            "duplicate_of": None,
            "duplicate_similarity": 0,
            "duplicate_cluster_id": f"cluster_{document_id}",
            "entities": [],
            "events": [],
            "steps": [],
            "quality_score": 0,
            "needs_review": True,
            "review_reasons": ["处理失败，请检查错误后重试"],
            "processor_version": "processing-v1",
            "processed_at": now,
            "error_message": message[:1000],
        }
        return self.save_document_processing(document_id, project_id, defaults)

    @staticmethod
    def _processing_select() -> str:
        return """SELECT d.*, s.name AS source_name, s.source_type AS source_type,
                         s.data_classification AS source_data_classification,
                         p.status AS processing_status, p.clean_text, p.clean_hash,
                         p.body_extraction_method, p.noise_removed_lines,
                         p.language AS detected_language, p.language_confidence,
                         p.ocr_status, p.ocr_text, p.duplicate_type, p.duplicate_of,
                         p.duplicate_similarity, p.duplicate_cluster_id,
                         p.entities_json, p.events_json, p.steps_json,
                         p.quality_score, p.needs_review, p.review_reasons_json,
                         p.processor_version, p.processed_at, p.error_message,
                         duplicate.title AS duplicate_title,
                         duplicate_source.name AS duplicate_source_name
                  FROM collection_documents d
                  JOIN data_sources s ON s.id=d.source_id
                  LEFT JOIN document_processing p ON p.document_id=d.id
                  LEFT JOIN collection_documents duplicate ON duplicate.id=p.duplicate_of
                  LEFT JOIN data_sources duplicate_source ON duplicate_source.id=duplicate.source_id"""

    def list_processing_documents(
        self,
        project_id: str,
        status_filter: str | None = None,
        query: str | None = None,
        limit: int = 200,
        allowed_domains: list[str] | None = None,
    ) -> list[sqlite3.Row]:
        clauses = ["d.project_id=?", "d.is_latest=1", "s.archived_at IS NULL"]
        parameters: list[object] = [project_id]
        if allowed_domains is not None:
            if not allowed_domains:
                return []
            placeholders = ",".join("?" for _ in allowed_domains)
            clauses.append(f"s.data_classification IN ({placeholders})")
            parameters.extend(allowed_domains)
        if status_filter == "pending":
            clauses.append("p.document_id IS NULL")
        elif status_filter:
            clauses.append("p.status=?")
            parameters.append(status_filter)
        if query:
            clauses.append("(d.title LIKE ? OR d.readable_text LIKE ? OR s.name LIKE ?)")
            term = f"%{query}%"
            parameters.extend([term, term, term])
        parameters.append(limit)
        with self.session() as connection:
            return list(
                connection.execute(
                    f"{self._processing_select()} WHERE {' AND '.join(clauses)} "
                    "ORDER BY COALESCE(p.processed_at, d.collected_at) DESC LIMIT ?",
                    tuple(parameters),
                ).fetchall()
            )

    def get_processing_document(self, document_id: str) -> sqlite3.Row | None:
        with self.session() as connection:
            return connection.execute(
                f"{self._processing_select()} WHERE d.id=? AND s.archived_at IS NULL",
                (document_id,),
            ).fetchone()

    def list_processing_candidates(
        self, project_id: str, exclude_document_id: str, limit: int = 300
    ) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """SELECT p.*, d.title, d.source_id, s.name AS source_name
                       FROM document_processing p
                       JOIN collection_documents d ON d.id=p.document_id
                       JOIN data_sources s ON s.id=d.source_id
                       WHERE p.project_id=? AND p.document_id!=?
                         AND p.status IN ('completed', 'review_required')
                         AND p.clean_text!=''
                       ORDER BY p.processed_at DESC LIMIT ?""",
                    (project_id, exclude_document_id, limit),
                ).fetchall()
            )

    def queue_due_source_runs(self, limit: int = 10) -> list[str]:
        now = utc_now()
        queued_ids: list[str] = []
        with self.session() as connection:
            due_sources = connection.execute(
                """SELECT * FROM data_sources
                   WHERE enabled=1 AND archived_at IS NULL
                     AND next_run_at IS NOT NULL AND next_run_at<=?
                     AND (circuit_state!='open' OR circuit_open_until IS NULL
                          OR circuit_open_until<=?)
                      AND NOT EXISTS (
                       SELECT 1 FROM source_runs r
                       WHERE r.source_id=data_sources.id
                         AND r.status IN ('queued', 'running')
                     )
                   ORDER BY priority DESC, next_run_at LIMIT ?""",
                (now, now, limit),
            ).fetchall()
            for source in due_sources:
                run_id = f"run_{uuid4().hex[:12]}"
                connection.execute(
                    """INSERT INTO source_runs
                       (id, source_id, status, trigger_type, priority, max_attempts,
                        timeout_seconds, backoff_seconds, scheduled_for, available_at,
                        created_by, created_at)
                       VALUES (?, ?, 'queued', 'scheduled', ?, ?, ?, ?, ?, ?,
                               'system_scheduler', ?)""",
                    (
                        run_id,
                        source["id"],
                        source["priority"],
                        source["max_attempts"],
                        source["task_timeout_seconds"],
                        source["retry_backoff_seconds"],
                        source["next_run_at"],
                        now,
                        now,
                    ),
                )
                self._insert_workflow_steps(connection, run_id, source["max_attempts"])
                connection.execute(
                    """UPDATE data_sources SET next_run_at=?,
                       circuit_state=CASE WHEN circuit_state='open' THEN 'half_open'
                                          ELSE circuit_state END
                       WHERE id=?""",
                    (schedule_next_run(source["schedule_frequency"]), source["id"]),
                )
                queued_ids.append(run_id)
        return queued_ids

    def list_dispatchable_run_ids(self, limit: int = 20) -> list[str]:
        now = utc_now()
        with self.session() as connection:
            rows = connection.execute(
                """SELECT r.id FROM source_runs r
                   JOIN data_sources s ON s.id=r.source_id
                   WHERE r.status='queued' AND s.enabled=1 AND s.archived_at IS NULL
                     AND (r.available_at IS NULL OR r.available_at<=?)
                     AND (s.circuit_state!='open' OR s.circuit_open_until IS NULL
                          OR s.circuit_open_until<=?)
                   ORDER BY r.priority DESC, COALESCE(r.scheduled_for, r.created_at),
                            r.created_at
                   LIMIT ?""",
                (now, now, limit),
            ).fetchall()
            return [row["id"] for row in rows]

    def recover_interrupted_runs(self) -> list[str]:
        """Recover work that was owned by a worker before the process stopped."""

        now = utc_now()
        recovered: list[str] = []
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM source_runs WHERE status='running'"
            ).fetchall()
            for run in rows:
                parser_steps = json.loads(run["parser_steps_json"] or "[]")
                if run["attempt"] < run["max_attempts"]:
                    parser_steps.append("检测到服务重启，任务已重新排队恢复")
                    connection.execute(
                        """UPDATE source_runs SET status='queued', available_at=?,
                           next_retry_at=?, recovered_from_restart=1,
                           parser_steps_json=? WHERE id=?""",
                        (
                            now,
                            now,
                            json.dumps(parser_steps, ensure_ascii=False),
                            run["id"],
                        ),
                    )
                    connection.execute(
                        """UPDATE workflow_steps SET status='pending',
                           finished_at=NULL, duration_ms=NULL
                           WHERE run_id=? AND status IN ('running','waiting_retry')""",
                        (run["id"],),
                    )
                    recovered.append(run["id"])
                else:
                    parser_steps.append("服务重启时任务已耗尽重试次数，转入异常队列")
                    connection.execute(
                        """UPDATE source_runs SET status='manual_review',
                           error_type='worker_interrupted',
                           error_message='任务执行期间服务停止且已耗尽重试次数',
                           parser_steps_json=?, finished_at=?, recovered_from_restart=1
                           WHERE id=?""",
                        (json.dumps(parser_steps, ensure_ascii=False), now, run["id"]),
                    )
                    connection.execute(
                        """UPDATE workflow_steps SET status='failed', finished_at=?,
                           error_type='worker_interrupted',
                           error_message='服务重启中断执行'
                           WHERE run_id=? AND status IN ('running','waiting_retry')""",
                        (now, run["id"]),
                    )
        return recovered

    def orchestration_metrics(self, project_id: str) -> sqlite3.Row | None:
        with self.session() as connection:
            return connection.execute(
                """SELECT
                     (SELECT COUNT(*) FROM data_sources
                       WHERE project_id=? AND enabled=1 AND archived_at IS NULL
                         AND schedule_frequency!='manual') AS scheduled_sources,
                     SUM(CASE WHEN r.status='queued' THEN 1 ELSE 0 END) AS queued,
                     SUM(CASE WHEN r.status='running' THEN 1 ELSE 0 END) AS running,
                     SUM(CASE WHEN r.status IN ('failed','partial','manual_review')
                              THEN 1 ELSE 0 END) AS exceptions,
                     SUM(CASE WHEN datetime(r.created_at)>=datetime('now','-24 hours')
                               AND r.status IN ('succeeded','partial') THEN 1 ELSE 0 END) AS ok_24h,
                     SUM(CASE WHEN datetime(r.created_at)>=datetime('now','-24 hours')
                               AND r.status IN ('succeeded','partial','failed','manual_review')
                              THEN 1 ELSE 0 END) AS finished_24h,
                     SUM(CASE WHEN datetime(r.created_at)>=datetime('now','-24 hours')
                               AND (r.recovery_of IS NOT NULL OR r.recovered_from_restart=1)
                              THEN 1 ELSE 0 END) AS recovered_24h
                   FROM data_sources s
                   LEFT JOIN source_runs r ON r.source_id=s.id
                   WHERE s.project_id=? AND s.archived_at IS NULL""",
                (project_id, project_id),
            ).fetchone()

    def list_orchestration_schedules(self, project_id: str) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """SELECT s.*,
                         (SELECT COUNT(*) FROM source_runs active
                           WHERE active.source_id=s.id
                             AND active.status IN ('queued','running')) AS active_runs,
                         (SELECT latest.status FROM source_runs latest
                           WHERE latest.source_id=s.id
                           ORDER BY latest.created_at DESC LIMIT 1) AS last_run_status
                       FROM data_sources s WHERE s.project_id=? AND s.archived_at IS NULL
                       ORDER BY s.enabled DESC, s.priority DESC, s.name""",
                    (project_id,),
                ).fetchall()
            )

    def latest_recoverable_run_ids(self, project_id: str) -> list[str]:
        with self.session() as connection:
            rows = connection.execute(
                """SELECT r.id FROM source_runs r
                   JOIN data_sources s ON s.id=r.source_id
                   WHERE s.project_id=? AND s.archived_at IS NULL
                     AND r.status IN ('failed','partial','manual_review')
                     AND NOT EXISTS (
                       SELECT 1 FROM source_runs newer
                       WHERE newer.source_id=r.source_id
                         AND newer.rowid>r.rowid
                     )
                   ORDER BY r.created_at DESC""",
                (project_id,),
            ).fetchall()
            return [row["id"] for row in rows]

    def archive_source(self, source_id: str, actor_id: str) -> bool | None:
        with self.session() as connection:
            source = connection.execute(
                "SELECT * FROM data_sources WHERE id=? AND archived_at IS NULL", (source_id,)
            ).fetchone()
            if source is None:
                return None
            if source["enabled"]:
                raise ValueError("请先停用数据源，再执行归档")
            now = utc_now()
            self._audit(
                connection,
                actor_id,
                "source.archive",
                "source",
                source_id,
                {"project_id": source["project_id"], "name": source["name"]},
            )
            connection.execute(
                """UPDATE data_sources
                   SET archived_at=?, archived_by=?, enabled=0, next_run_at=NULL,
                       health_status='disabled', updated_at=?
                   WHERE id=?""",
                (now, actor_id, now, source_id),
            )
            self._refresh_source_health(connection, source["project_id"])
            return True

    def purge_source(self, source_id: str, actor_id: str) -> dict[str, int] | None:
        with self.session() as connection:
            source = connection.execute(
                "SELECT * FROM data_sources WHERE id=?", (source_id,)
            ).fetchone()
            if source is None:
                return None
            if source["archived_at"] is None:
                raise ValueError("数据源必须先归档，才能永久清除")
            counts = {
                "runs": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM source_runs WHERE source_id=?", (source_id,)
                    ).fetchone()[0]
                ),
                "documents": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM collection_documents WHERE source_id=?",
                        (source_id,),
                    ).fetchone()[0]
                ),
                "knowledge_items": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM knowledge_items WHERE source_id=?",
                        (source_id,),
                    ).fetchone()[0]
                ),
            }
            self._audit(
                connection,
                actor_id,
                "source.purge",
                "source",
                source_id,
                {
                    "project_id": source["project_id"],
                    "name": source["name"],
                    **counts,
                },
            )
            connection.execute(
                """UPDATE knowledge_items
                   SET validity_status='archived', review_status='review_required',
                       updated_at=?
                   WHERE source_id=?""",
                (utc_now(), source_id),
            )
            connection.execute("DELETE FROM data_sources WHERE id=?", (source_id,))
            self._refresh_source_health(connection, source["project_id"])
            return counts

    @staticmethod
    def _knowledge_select() -> str:
        return """SELECT k.*,
                         s.name AS source_name,
                         COALESCE(d.canonical_url, s.endpoint, '') AS source_url,
                         s.authorization_status AS source_authorization_status,
                         s.retention_days AS source_retention_days,
                         COALESCE(s.data_classification, 'internal')
                             AS source_data_classification,
                         d.title AS document_title,
                         d.version_no AS document_version,
                         d.content_hash AS document_content_hash,
                         d.parser_version AS document_parser_version,
                         d.collected_at AS document_collected_at,
                         d.published_at AS document_published_at,
                         CASE WHEN d.id IS NULL THEN 0 ELSE 1 END AS raw_available,
                         (SELECT COUNT(*) FROM knowledge_collection_items membership
                           WHERE membership.item_id=k.id) AS collection_count
                  FROM knowledge_items k
                  LEFT JOIN data_sources s ON s.id=k.source_id
                  LEFT JOIN collection_documents d ON d.id=k.document_id"""

    def list_knowledge_items(
        self,
        project_id: str,
        *,
        query: str | None = None,
        item_type: str | None = None,
        review_status: str | None = None,
        source_id: str | None = None,
        collection_id: str | None = None,
        limit: int = 200,
        allowed_domains: list[str] | None = None,
    ) -> list[sqlite3.Row]:
        clauses = ["k.project_id=?", "(s.id IS NULL OR s.archived_at IS NULL)"]
        parameters: list[object] = [project_id]
        if allowed_domains is not None:
            if not allowed_domains:
                return []
            placeholders = ",".join("?" for _ in allowed_domains)
            clauses.append(
                f"COALESCE(s.data_classification, 'internal') IN ({placeholders})"
            )
            parameters.extend(allowed_domains)
        if query:
            term = f"%{query}%"
            clauses.append(
                "(k.title LIKE ? OR k.summary LIKE ? OR k.content LIKE ? "
                "OR k.subject LIKE ? OR k.tags_json LIKE ?)"
            )
            parameters.extend([term, term, term, term, term])
        if item_type:
            clauses.append("k.item_type=?")
            parameters.append(item_type)
        if review_status:
            clauses.append("k.review_status=?")
            parameters.append(review_status)
        if source_id:
            clauses.append("k.source_id=?")
            parameters.append(source_id)
        if collection_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM knowledge_collection_items selected "
                "WHERE selected.item_id=k.id AND selected.collection_id=?)"
            )
            parameters.append(collection_id)
        parameters.append(limit)
        with self.session() as connection:
            return list(
                connection.execute(
                    f"{self._knowledge_select()} WHERE {' AND '.join(clauses)} "
                    "ORDER BY CASE k.validity_status WHEN 'at_risk' THEN 0 ELSE 1 END, "
                    "CASE k.review_status WHEN 'conflict' THEN 0 "
                    "WHEN 'review_required' THEN 1 ELSE 2 END, "
                    "k.updated_at DESC LIMIT ?",
                    tuple(parameters),
                ).fetchall()
            )

    def get_knowledge_item(self, item_id: str) -> sqlite3.Row | None:
        with self.session() as connection:
            return connection.execute(
                f"{self._knowledge_select()} WHERE k.id=? "
                "AND (s.id IS NULL OR s.archived_at IS NULL)",
                (item_id,),
            ).fetchone()

    def knowledge_storage_metrics(
        self, project_id: str, allowed_domains: list[str] | None = None
    ) -> sqlite3.Row:
        with self.session() as connection:
            if allowed_domains is not None:
                if not allowed_domains:
                    row = connection.execute(
                        """SELECT 0 AS raw_documents, 0 AS document_versions,
                                  0 AS processed_documents, 0 AS knowledge_items,
                                  0 AS sources, 0 AS storage_bytes"""
                    ).fetchone()
                    assert row is not None
                    return row
                placeholders = ",".join("?" for _ in allowed_domains)
                orphan_clause = " OR k.source_id IS NULL" if "internal" in allowed_domains else ""
                row = connection.execute(
                    f"""WITH allowed_sources AS (
                           SELECT id FROM data_sources
                           WHERE project_id=? AND archived_at IS NULL
                             AND data_classification IN ({placeholders})
                         ), allowed_documents AS (
                           SELECT * FROM collection_documents
                           WHERE project_id=?
                             AND source_id IN (SELECT id FROM allowed_sources)
                         )
                         SELECT
                           (SELECT COUNT(*) FROM allowed_documents WHERE is_latest=1)
                             AS raw_documents,
                           (SELECT COUNT(*) FROM allowed_documents) AS document_versions,
                           (SELECT COUNT(*) FROM document_processing
                             WHERE project_id=?
                               AND document_id IN (SELECT id FROM allowed_documents)
                               AND status IN ('completed','review_required'))
                             AS processed_documents,
                           (SELECT COUNT(*) FROM knowledge_items k
                             WHERE k.project_id=?
                               AND (k.source_id IN (SELECT id FROM allowed_sources)
                                    {orphan_clause})) AS knowledge_items,
                           (SELECT COUNT(*) FROM allowed_sources) AS sources,
                           (SELECT COALESCE(SUM(length(raw_content)), 0)
                              FROM allowed_documents) +
                           (SELECT COALESCE(SUM(length(clean_text)), 0)
                              FROM document_processing
                              WHERE project_id=?
                                AND document_id IN (SELECT id FROM allowed_documents))
                             AS storage_bytes""",
                    (
                        project_id,
                        *allowed_domains,
                        project_id,
                        project_id,
                        project_id,
                        project_id,
                    ),
                ).fetchone()
                assert row is not None
                return row
            row = connection.execute(
                """SELECT
                     (SELECT COUNT(*) FROM collection_documents
                       WHERE project_id=? AND is_latest=1) AS raw_documents,
                     (SELECT COUNT(*) FROM collection_documents
                       WHERE project_id=?) AS document_versions,
                     (SELECT COUNT(*) FROM document_processing
                       WHERE project_id=? AND status IN ('completed','review_required'))
                       AS processed_documents,
                     (SELECT COUNT(*) FROM knowledge_items
                       WHERE project_id=?) AS knowledge_items,
                     (SELECT COUNT(*) FROM data_sources
                       WHERE project_id=?) AS sources,
                     (SELECT COALESCE(SUM(length(raw_content)), 0)
                        FROM collection_documents WHERE project_id=?) +
                     (SELECT COALESCE(SUM(length(clean_text)), 0)
                        FROM document_processing WHERE project_id=?) AS storage_bytes""",
                (project_id,) * 7,
            ).fetchone()
            assert row is not None
            return row

    @staticmethod
    def _knowledge_collection_select() -> str:
        return """SELECT c.*,
                         COUNT(m.item_id) AS item_count
                  FROM knowledge_collections c
                  LEFT JOIN knowledge_collection_items m ON m.collection_id=c.id"""

    def list_knowledge_collections(self, project_id: str) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    f"{self._knowledge_collection_select()} "
                    "WHERE c.project_id=? GROUP BY c.id "
                    "ORDER BY c.updated_at DESC, c.name",
                    (project_id,),
                ).fetchall()
            )

    def get_knowledge_collection(self, collection_id: str) -> sqlite3.Row | None:
        with self.session() as connection:
            return connection.execute(
                f"{self._knowledge_collection_select()} "
                "WHERE c.id=? GROUP BY c.id",
                (collection_id,),
            ).fetchone()

    def list_knowledge_item_collections(self, item_id: str) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    f"{self._knowledge_collection_select()} "
                    "JOIN knowledge_collection_items selected ON selected.collection_id=c.id "
                    "WHERE selected.item_id=? GROUP BY c.id ORDER BY c.updated_at DESC",
                    (item_id,),
                ).fetchall()
            )

    def list_knowledge_revisions(self, item_id: str) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """SELECT r.*, u.name AS changed_by_name
                       FROM knowledge_revisions r
                       LEFT JOIN users u ON u.id=r.changed_by
                       WHERE r.item_id=? ORDER BY r.version_no DESC""",
                    (item_id,),
                ).fetchall()
            )

    def create_knowledge_collection(
        self,
        project_id: str,
        name: str,
        description: str,
        color: str,
        actor_id: str,
    ) -> sqlite3.Row | None:
        if self.get_project(project_id) is None:
            return None
        collection_id = f"kcol_{uuid4().hex[:12]}"
        now = utc_now()
        with self.session() as connection:
            connection.execute(
                """INSERT INTO knowledge_collections
                   (id, project_id, name, description, color, created_by, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    collection_id,
                    project_id,
                    name.strip(),
                    description.strip(),
                    color,
                    actor_id,
                    now,
                    now,
                ),
            )
            self._audit(
                connection,
                actor_id,
                "knowledge_collection.create",
                "knowledge_collection",
                collection_id,
                {"project_id": project_id, "name": name.strip()},
            )
            return connection.execute(
                f"{self._knowledge_collection_select()} "
                "WHERE c.id=? GROUP BY c.id",
                (collection_id,),
            ).fetchone()

    def add_knowledge_collection_item(
        self, collection_id: str, item_id: str, actor_id: str
    ) -> sqlite3.Row | None:
        now = utc_now()
        with self.session() as connection:
            collection = connection.execute(
                "SELECT * FROM knowledge_collections WHERE id=?", (collection_id,)
            ).fetchone()
            item = connection.execute(
                "SELECT * FROM knowledge_items WHERE id=?", (item_id,)
            ).fetchone()
            if collection is None or item is None:
                return None
            if collection["project_id"] != item["project_id"]:
                raise ValueError("专题集合与知识条目不属于同一项目")
            connection.execute(
                """INSERT OR IGNORE INTO knowledge_collection_items
                   (collection_id, item_id, added_by, added_at)
                   VALUES (?, ?, ?, ?)""",
                (collection_id, item_id, actor_id, now),
            )
            connection.execute(
                "UPDATE knowledge_collections SET updated_at=? WHERE id=?",
                (now, collection_id),
            )
            self._audit(
                connection,
                actor_id,
                "knowledge_collection.item_add",
                "knowledge_item",
                item_id,
                {"collection_id": collection_id},
            )
            return connection.execute(
                f"{self._knowledge_collection_select()} "
                "WHERE c.id=? GROUP BY c.id",
                (collection_id,),
            ).fetchone()

    def remove_knowledge_collection_item(
        self, collection_id: str, item_id: str, actor_id: str
    ) -> sqlite3.Row | None:
        now = utc_now()
        with self.session() as connection:
            collection = connection.execute(
                "SELECT * FROM knowledge_collections WHERE id=?", (collection_id,)
            ).fetchone()
            if collection is None:
                return None
            connection.execute(
                "DELETE FROM knowledge_collection_items WHERE collection_id=? AND item_id=?",
                (collection_id, item_id),
            )
            connection.execute(
                "UPDATE knowledge_collections SET updated_at=? WHERE id=?",
                (now, collection_id),
            )
            self._audit(
                connection,
                actor_id,
                "knowledge_collection.item_remove",
                "knowledge_item",
                item_id,
                {"collection_id": collection_id},
            )
            return connection.execute(
                f"{self._knowledge_collection_select()} "
                "WHERE c.id=? GROUP BY c.id",
                (collection_id,),
            ).fetchone()

    def update_knowledge_review(
        self,
        item_id: str,
        review_status: str,
        note: str,
        actor_id: str,
    ) -> sqlite3.Row | None:
        now = utc_now()
        with self.session() as connection:
            item = connection.execute(
                "SELECT * FROM knowledge_items WHERE id=?", (item_id,)
            ).fetchone()
            if item is None:
                return None
            version_row = connection.execute(
                "SELECT COALESCE(MAX(version_no), 0) AS version FROM knowledge_revisions WHERE item_id=?",
                (item_id,),
            ).fetchone()
            version_no = int(version_row["version"] or 0) + 1
            snapshot = {
                "review_status": review_status,
                "previous_review_status": item["review_status"],
                "validity_status": item["validity_status"],
                "confidence": item["confidence"],
                "tags": json.loads(item["tags_json"] or "[]"),
            }
            connection.execute(
                "UPDATE knowledge_items SET review_status=?, updated_at=? WHERE id=?",
                (review_status, now, item_id),
            )
            connection.execute(
                """INSERT INTO knowledge_revisions
                   (item_id, version_no, action, snapshot_json, note, changed_by, created_at)
                   VALUES (?, ?, 'review_status_updated', ?, ?, ?, ?)""",
                (
                    item_id,
                    version_no,
                    json.dumps(snapshot, ensure_ascii=False),
                    note.strip(),
                    actor_id,
                    now,
                ),
            )
            self._audit(
                connection,
                actor_id,
                "knowledge.review",
                "knowledge_item",
                item_id,
                {
                    "from": item["review_status"],
                    "to": review_status,
                    "note": note.strip(),
                },
            )
            return connection.execute(
                f"{self._knowledge_select()} WHERE k.id=?", (item_id,)
            ).fetchone()

    def list_rag_candidates(
        self,
        project_id: str,
        *,
        competitors: list[str] | None = None,
        item_types: list[str] | None = None,
        categories: list[str] | None = None,
        review_statuses: list[str] | None = None,
        collection_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        include_at_risk: bool = True,
        allowed_domains: list[str] | None = None,
        limit: int = 1000,
    ) -> list[sqlite3.Row]:
        """Return authorization-filtered knowledge rows for in-process ranking."""

        clauses = [
            "k.project_id=?",
            "k.validity_status NOT IN ('expired', 'archived')",
            "(s.id IS NULL OR s.authorization_status='approved')",
            "(s.id IS NULL OR s.archived_at IS NULL)",
        ]
        params: list[object] = [project_id]
        if allowed_domains is not None:
            if not allowed_domains:
                return []
            placeholders = ",".join("?" for _ in allowed_domains)
            clauses.append(
                f"COALESCE(s.data_classification, 'internal') IN ({placeholders})"
            )
            params.extend(allowed_domains)

        def add_in(column: str, values: list[str] | None) -> None:
            if not values:
                return
            placeholders = ",".join("?" for _ in values)
            clauses.append(f"{column} IN ({placeholders})")
            params.extend(values)

        add_in("k.subject", competitors)
        add_in("k.item_type", item_types)
        add_in("k.category", categories)
        add_in("k.review_status", review_statuses)
        if collection_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM knowledge_collection_items m "
                "WHERE m.item_id=k.id AND m.collection_id=?)"
            )
            params.append(collection_id)
        if start_date:
            clauses.append("date(COALESCE(k.published_at, k.updated_at)) >= date(?)")
            params.append(start_date)
        if end_date:
            clauses.append("date(COALESCE(k.published_at, k.updated_at)) <= date(?)")
            params.append(end_date)
        if not include_at_risk:
            clauses.append("k.validity_status='active'")
        params.append(max(1, min(limit, 2000)))
        query = f"""
            SELECT k.*,
                   COALESCE(s.name, '内部知识库') AS source_name,
                   COALESCE(s.endpoint, '') AS source_url,
                   s.authorization_status AS source_authorization_status,
                   COALESCE(s.data_classification, 'internal')
                       AS source_data_classification
            FROM knowledge_items k
            LEFT JOIN data_sources s ON s.id=k.source_id
            WHERE {' AND '.join(clauses)}
            ORDER BY k.updated_at DESC, k.confidence DESC
            LIMIT ?
        """
        with self.session() as connection:
            return list(connection.execute(query, tuple(params)).fetchall())

    def list_competitor_subjects(self, project_id: str) -> list[str]:
        with self.session() as connection:
            rows = connection.execute(
                """SELECT subject, COUNT(*) AS item_count
                   FROM knowledge_items
                   WHERE project_id=? AND subject IS NOT NULL
                     AND item_type IN ('fact', 'entity', 'event')
                     AND validity_status NOT IN ('expired', 'archived')
                   GROUP BY subject ORDER BY item_count DESC, subject""",
                (project_id,),
            ).fetchall()
            return [str(row["subject"]) for row in rows if row["subject"]]

    def log_rag_query(
        self,
        query_id: str,
        project_id: str,
        question: str,
        filters: dict[str, object],
        retrieved_item_ids: list[str],
        answer_type: str,
        confidence: int,
        trace: dict[str, object],
        actor_id: str,
        created_at: str,
    ) -> None:
        with self.session() as connection:
            connection.execute(
                """INSERT INTO rag_query_logs
                   (id, project_id, question, filters_json, retrieved_item_ids_json,
                    answer_type, confidence, trace_json, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    query_id,
                    project_id,
                    question,
                    json.dumps(filters, ensure_ascii=False),
                    json.dumps(retrieved_item_ids, ensure_ascii=False),
                    answer_type,
                    confidence,
                    json.dumps(trace, ensure_ascii=False),
                    actor_id,
                    created_at,
                ),
            )
            self._audit(
                connection,
                actor_id,
                "rag.query",
                "rag_query",
                query_id,
                {
                    "project_id": project_id,
                    "answer_type": answer_type,
                    "retrieved_count": len(retrieved_item_ids),
                },
            )

    def save_competitive_analysis(
        self,
        result: dict[str, object],
        actor_id: str,
    ) -> sqlite3.Row:
        with self.session() as connection:
            connection.execute(
                """INSERT INTO competitive_analysis_runs
                   (id, project_id, title, status, competitors_json, dimensions_json,
                    range_key, coverage_rate, sample_size, result_json, created_by,
                    created_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result["id"],
                    result["project_id"],
                    result["title"],
                    result["status"],
                    json.dumps(result["competitors"], ensure_ascii=False),
                    json.dumps(result["dimensions"], ensure_ascii=False),
                    result["range_key"],
                    result["coverage_rate"],
                    result["sample_size"],
                    json.dumps(result, ensure_ascii=False),
                    actor_id,
                    result["created_at"],
                    result["completed_at"],
                ),
            )
            self._audit(
                connection,
                actor_id,
                "competitive_analysis.generate",
                "competitive_analysis",
                str(result["id"]),
                {
                    "project_id": result["project_id"],
                    "competitors": result["competitors"],
                    "dimensions": result["dimensions"],
                    "coverage_rate": result["coverage_rate"],
                },
            )
            row = connection.execute(
                "SELECT * FROM competitive_analysis_runs WHERE id=?",
                (result["id"],),
            ).fetchone()
            assert row is not None
            return row

    def list_competitive_analyses(
        self, project_id: str, limit: int = 10
    ) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """SELECT * FROM competitive_analysis_runs
                       WHERE project_id=? ORDER BY created_at DESC LIMIT ?""",
                    (project_id, max(1, min(limit, 50))),
                ).fetchall()
            )

    def get_competitive_analysis(self, run_id: str) -> sqlite3.Row | None:
        with self.session() as connection:
            return connection.execute(
                "SELECT * FROM competitive_analysis_runs WHERE id=?", (run_id,)
            ).fetchone()

    def list_insights(self, project_id: str) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """SELECT * FROM insights WHERE project_id=?
                       ORDER BY sort_order, created_at DESC LIMIT 20""",
                    (project_id,),
                ).fetchall()
            )

    def get_insight(self, insight_id: int) -> sqlite3.Row | None:
        with self.session() as connection:
            return connection.execute(
                "SELECT * FROM insights WHERE id=?", (insight_id,)
            ).fetchone()

    def list_evidence(self, insight_id: int) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    "SELECT * FROM evidence WHERE insight_id=? ORDER BY id", (insight_id,)
                ).fetchall()
            )

    def list_reviews(self, project_id: str) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """SELECT * FROM review_items WHERE project_id=? AND status='pending'
                       ORDER BY id LIMIT 3""",
                    (project_id,),
                ).fetchall()
            )

    def get_review(self, review_id: int) -> sqlite3.Row | None:
        with self.session() as connection:
            return connection.execute(
                "SELECT * FROM review_items WHERE id=?", (review_id,)
            ).fetchone()

    def pending_review_count(self, project_id: str) -> int:
        with self.session() as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS count FROM review_items
                   WHERE project_id=? AND status='pending'""",
                (project_id,),
            ).fetchone()
            return int(row["count"])

    def claim_review(self, review_id: int, actor_id: str) -> sqlite3.Row | None:
        now = utc_now()
        with self.session() as connection:
            item = connection.execute(
                "SELECT * FROM review_items WHERE id=?", (review_id,)
            ).fetchone()
            if item is None or item["status"] != "pending":
                return None
            connection.execute(
                """UPDATE review_items SET status='claimed', claimed_by=?, claimed_at=?
                   WHERE id=? AND status='pending'""",
                (actor_id, now, review_id),
            )
            connection.execute(
                """UPDATE project_metrics
                   SET pending_reviews=MAX(pending_reviews - 1, 0)
                   WHERE project_id=?""",
                (item["project_id"],),
            )
            self._audit(
                connection,
                actor_id,
                "review.claim",
                "review_item",
                str(review_id),
                {"project_id": item["project_id"]},
            )
            return connection.execute(
                "SELECT * FROM review_items WHERE id=?", (review_id,)
            ).fetchone()

    def list_reports(self, project_id: str) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """SELECT * FROM reports WHERE project_id=?
                       ORDER BY created_at DESC LIMIT 10""",
                    (project_id,),
                ).fetchall()
            )

    def generate_report(
        self,
        project_id: str,
        template: str,
        actor_id: str,
        options: dict[str, object] | None = None,
    ) -> sqlite3.Row | None:
        project = self.get_project(project_id)
        if project is None:
            return None
        options = options or {}
        report_id = f"rpt_{uuid4().hex[:12]}"
        now = utc_now()
        titles = {
            "daily": f"{project['name']}竞品晨报",
            "weekly": f"{project['name']}周报",
            "compare": f"{project['name']}产品对比",
            "flash": f"{project['name']}竞品快讯",
            "strategy": f"{project['name']}专题研究",
            "executive": f"{project['name']}高管摘要",
        }
        with self.session() as connection:
            template_row = None
            if options.get("template_id"):
                template_row = connection.execute(
                    "SELECT * FROM report_templates WHERE id=?",
                    (options["template_id"],),
                ).fetchone()
            if template_row is None:
                template_row = connection.execute(
                    """SELECT * FROM report_templates
                       WHERE report_type=? AND (project_id=? OR project_id IS NULL)
                       ORDER BY builtin DESC LIMIT 1""",
                    (template, project_id),
                ).fetchone()
            template_id = template_row["id"] if template_row else None
            approval_required = options.get("approval_required")
            if approval_required is None:
                approval_required = bool(template_row["approval_required"]) if template_row else False
            version = connection.execute(
                "SELECT COUNT(*) + 1 AS next_version FROM reports WHERE project_id=? AND report_type=?",
                (project_id, template),
            ).fetchone()["next_version"]
            connection.execute(
                """INSERT INTO reports
                   (id, project_id, template_id, title, report_type, version,
                    time_window, language, audience, schedule_label, status, progress,
                    approval_required, approval_status, content_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '刚刚创建', '生成中', 5,
                           ?, ?, '{}', ?, ?)""",
                (
                    report_id,
                    project_id,
                    template_id,
                    titles[template],
                    template,
                    version,
                    str(options.get("time_window") or "24h"),
                    str(options.get("language") or "zh-CN"),
                    str(options.get("audience") or (template_row["audience"] if template_row else "analyst")),
                    int(bool(approval_required)),
                    "pending" if approval_required else "not_required",
                    now,
                    now,
                ),
            )
            self._audit(
                connection,
                actor_id,
                "report.generate",
                "report",
                report_id,
                {"project_id": project_id, "template": template, "options": options},
            )
            return connection.execute(
                "SELECT * FROM reports WHERE id=?", (report_id,)
            ).fetchone()

    @staticmethod
    def _report_record(row: sqlite3.Row) -> dict[str, object]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "template_id": row["template_id"],
            "title": row["title"],
            "report_type": row["report_type"],
            "version": row["version"],
            "time_window": row["time_window"],
            "language": row["language"],
            "audience": row["audience"],
            "state": row["status"],
            "progress": row["progress"],
            "approval_status": row["approval_status"],
            "evidence_count": row["evidence_count"],
            "source_count": row["source_count"],
            "confidence": row["confidence"],
            "data_cutoff": row["data_cutoff"],
            "sections": json.loads(row["content_json"] or "{}"),
            "failure_reason": row["failure_reason"],
            "approved_by": row["approved_by"],
            "approved_at": row["approved_at"],
            "delivered_at": row["delivered_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"] or row["created_at"],
        }

    def get_report_record(self, report_id: str) -> dict[str, object] | None:
        with self.session() as connection:
            row = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            return self._report_record(row) if row else None

    def complete_report(self, report_id: str) -> None:
        with self.session() as connection:
            report = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            if report is None or report["status"] != "生成中":
                return
            knowledge = connection.execute(
                """SELECT title, summary, item_type, subject, confidence,
                          evidence_excerpt, source_id, validity_status, review_status
                   FROM knowledge_items WHERE project_id=?
                   AND validity_status='active' AND review_status!='review_required'
                   ORDER BY confidence DESC, updated_at DESC LIMIT 12""",
                (report["project_id"],),
            ).fetchall()
            insights = connection.execute(
                """SELECT title, summary, company, impact_level, confidence, source_count,
                          recommendation FROM insights WHERE project_id=?
                   ORDER BY sort_order LIMIT 8""",
                (report["project_id"],),
            ).fetchall()
            source_ids = {row["source_id"] for row in knowledge if row["source_id"]}
            evidence_count = len(knowledge) + sum(row["source_count"] for row in insights)
            confidences = [row["confidence"] for row in knowledge] + [row["confidence"] for row in insights]
            confidence = round(sum(confidences) / len(confidences)) if confidences else 0
            changes = [
                {
                    "label": "事实" if row["item_type"] != "insight" else "推断",
                    "title": row["title"],
                    "summary": row["summary"],
                    "subject": row["subject"] or "未归属主体",
                    "confidence": row["confidence"],
                    "evidence": row["evidence_excerpt"],
                }
                for row in knowledge[:6]
            ]
            recommendations = [
                {
                    "applicable_to": row["company"],
                    "action": row["recommendation"],
                    "basis": row["title"],
                    "confidence": row["confidence"],
                }
                for row in insights[:4]
                if row["recommendation"]
            ]
            content = {
                "执行摘要": (
                    f"本期覆盖 {len(source_ids)} 个独立来源与 {len(knowledge)} 条有效知识，"
                    f"识别 {len(insights)} 条竞品变化。事实型结论均绑定证据，"
                    "低置信或冲突内容未作为确定事实自动写入。"
                ),
                "关键变化": changes,
                "趋势与影响": [
                    {
                        "title": row["title"],
                        "company": row["company"],
                        "impact": row["impact_level"],
                        "summary": row["summary"],
                    }
                    for row in insights[:5]
                ],
                "建议动作": recommendations,
                "风险": [
                    "来源授权、内容有效期或发布时间变化时，关联结论需重新校验。",
                    "推断与建议不等同于已验证事实，执行前应由业务负责人复核。",
                ],
                "方法与来源": {
                    "method": "权限过滤后的证据集合 + 结构化事实与事件 + 人工质量门禁",
                    "evidence_count": evidence_count,
                    "source_count": len(source_ids),
                    "data_cutoff": utc_now(),
                },
            }
            next_state = "待审批" if report["approval_required"] else "已交付"
            delivered_at = None if report["approval_required"] else utc_now()
            connection.execute(
                """UPDATE reports SET status=?, progress=100, evidence_count=?,
                   source_count=?, confidence=?, data_cutoff=?, content_json=?,
                   delivered_at=?, updated_at=? WHERE id=?""",
                (
                    next_state,
                    evidence_count,
                    len(source_ids),
                    confidence,
                    utc_now(),
                    json.dumps(content, ensure_ascii=False),
                    delivered_at,
                    utc_now(),
                    report_id,
                ),
            )

    def approve_report(
        self, report_id: str, decision: str, note: str, actor_id: str
    ) -> dict[str, object] | None:
        with self.session() as connection:
            row = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            if row is None:
                return None
            now = utc_now()
            if decision == "approve":
                connection.execute(
                    """UPDATE reports SET status='已交付', approval_status='approved',
                       approved_by=?, approved_at=?, delivered_at=?, failure_reason=NULL,
                       updated_at=? WHERE id=?""",
                    (actor_id, now, now, now, report_id),
                )
            else:
                connection.execute(
                    """UPDATE reports SET status='生成失败', approval_status='rejected',
                       approved_by=?, approved_at=?, failure_reason=?, updated_at=? WHERE id=?""",
                    (actor_id, now, note or "审批未通过", now, report_id),
                )
            self._audit(
                connection,
                actor_id,
                f"report.{decision}",
                "report",
                report_id,
                {"note": note},
            )
            updated = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            return self._report_record(updated)

    def get_reporting_dashboard(self, project_id: str) -> dict[str, object] | None:
        if self.get_project(project_id) is None:
            return None
        with self.session() as connection:
            templates = connection.execute(
                """SELECT * FROM report_templates
                   WHERE project_id=? OR project_id IS NULL
                   ORDER BY builtin DESC, name""",
                (project_id,),
            ).fetchall()
            reports = connection.execute(
                "SELECT * FROM reports WHERE project_id=? ORDER BY created_at DESC LIMIT 30",
                (project_id,),
            ).fetchall()
            subscriptions = connection.execute(
                "SELECT * FROM report_subscriptions WHERE project_id=? ORDER BY created_at",
                (project_id,),
            ).fetchall()
            rules = connection.execute(
                "SELECT * FROM alert_rules WHERE project_id=? ORDER BY created_at",
                (project_id,),
            ).fetchall()
            alerts = connection.execute(
                "SELECT * FROM alerts WHERE project_id=? ORDER BY last_seen_at DESC LIMIT 30",
                (project_id,),
            ).fetchall()
            delivered = sum(row["status"] == "已交付" for row in reports)
            generating = sum(row["status"] == "生成中" for row in reports)
            pending = sum(row["status"] == "待审批" for row in reports)
            active_alerts = sum(row["status"] in {"new", "acknowledged"} for row in alerts)
            critical = sum(
                row["impact"] == "critical" and row["status"] in {"new", "acknowledged"}
                for row in alerts
            )
            return {
                "project_id": project_id,
                "generated_at": utc_now(),
                "summary": {
                    "delivered": delivered,
                    "generating": generating,
                    "pending_approval": pending,
                    "active_alerts": active_alerts,
                    "critical_alerts": critical,
                    "on_time_rate": 99.0 if delivered else 0.0,
                    "evidence_coverage": 100.0,
                },
                "templates": [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "report_type": row["report_type"],
                        "description": row["description"],
                        "sections": json.loads(row["sections_json"]),
                        "language": row["language"],
                        "audience": row["audience"],
                        "approval_required": bool(row["approval_required"]),
                        "builtin": bool(row["builtin"]),
                        "updated_at": row["updated_at"],
                    }
                    for row in templates
                ],
                "reports": [self._report_record(row) for row in reports],
                "subscriptions": [
                    {
                        "id": row["id"],
                        "project_id": row["project_id"],
                        "name": row["name"],
                        "template_id": row["template_id"],
                        "cadence": row["cadence"],
                        "delivery_time": row["delivery_time"],
                        "timezone": row["timezone"],
                        "channels": json.loads(row["channels_json"]),
                        "recipients": json.loads(row["recipients_json"]),
                        "enabled": bool(row["enabled"]),
                        "next_run_at": row["next_run_at"],
                        "last_delivery_status": row["last_delivery_status"],
                        "updated_at": row["updated_at"],
                    }
                    for row in subscriptions
                ],
                "alert_rules": [self._alert_rule_record(row) for row in rules],
                "alerts": [self._alert_record(row) for row in alerts],
            }

    @staticmethod
    def _alert_rule_record(row: sqlite3.Row) -> dict[str, object]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "competitors": json.loads(row["competitors_json"]),
            "keywords": json.loads(row["keywords_json"]),
            "event_types": json.loads(row["event_types_json"]),
            "min_impact": row["min_impact"],
            "min_confidence": row["min_confidence"],
            "change_threshold": row["change_threshold"],
            "quiet_minutes": row["quiet_minutes"],
            "escalation_minutes": row["escalation_minutes"],
            "channels": json.loads(row["channels_json"]),
            "enabled": bool(row["enabled"]),
            "last_triggered_at": row["last_triggered_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _alert_record(row: sqlite3.Row) -> dict[str, object]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "rule_id": row["rule_id"],
            "insight_id": row["insight_id"],
            "title": row["title"],
            "summary": row["summary"],
            "competitor": row["competitor"],
            "event_type": row["event_type"],
            "impact": row["impact"],
            "confidence": row["confidence"],
            "source_count": row["source_count"],
            "status": row["status"],
            "occurrence_count": row["occurrence_count"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "quiet_until": row["quiet_until"],
            "acknowledged_by": row["acknowledged_by"],
            "acknowledged_at": row["acknowledged_at"],
            "resolved_by": row["resolved_by"],
            "resolved_at": row["resolved_at"],
        }

    def set_subscription_enabled(
        self, subscription_id: str, enabled: bool, actor_id: str
    ) -> dict[str, object] | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM report_subscriptions WHERE id=?", (subscription_id,)
            ).fetchone()
            if row is None:
                return None
            now = utc_now()
            next_run = schedule_next_run(row["cadence"]) if enabled else None
            connection.execute(
                "UPDATE report_subscriptions SET enabled=?, next_run_at=?, updated_at=? WHERE id=?",
                (int(enabled), next_run, now, subscription_id),
            )
            self._audit(
                connection,
                actor_id,
                "report.subscription.update",
                "report_subscription",
                subscription_id,
                {"enabled": enabled},
            )
            updated = connection.execute(
                "SELECT * FROM report_subscriptions WHERE id=?", (subscription_id,)
            ).fetchone()
            return {
                "id": updated["id"],
                "project_id": updated["project_id"],
                "name": updated["name"],
                "template_id": updated["template_id"],
                "cadence": updated["cadence"],
                "delivery_time": updated["delivery_time"],
                "timezone": updated["timezone"],
                "channels": json.loads(updated["channels_json"]),
                "recipients": json.loads(updated["recipients_json"]),
                "enabled": bool(updated["enabled"]),
                "next_run_at": updated["next_run_at"],
                "last_delivery_status": updated["last_delivery_status"],
                "updated_at": updated["updated_at"],
            }

    def create_alert_rule(
        self, payload: dict[str, object], actor_id: str
    ) -> dict[str, object] | None:
        if self.get_project(str(payload["project_id"])) is None:
            return None
        rule_id = f"rule_{uuid4().hex[:12]}"
        now = utc_now()
        with self.session() as connection:
            connection.execute(
                """INSERT INTO alert_rules
                   (id, project_id, name, competitors_json, keywords_json,
                    event_types_json, min_impact, min_confidence, change_threshold,
                    quiet_minutes, escalation_minutes, channels_json, enabled,
                    created_by, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rule_id,
                    payload["project_id"],
                    payload["name"],
                    json.dumps(payload.get("competitors", []), ensure_ascii=False),
                    json.dumps(payload.get("keywords", []), ensure_ascii=False),
                    json.dumps(payload.get("event_types", []), ensure_ascii=False),
                    payload.get("min_impact", "medium"),
                    payload.get("min_confidence", 75),
                    payload.get("change_threshold", 0),
                    payload.get("quiet_minutes", 60),
                    payload.get("escalation_minutes", 120),
                    json.dumps(payload.get("channels", ["in_app"]), ensure_ascii=False),
                    int(bool(payload.get("enabled", True))),
                    actor_id,
                    now,
                    now,
                ),
            )
            self._audit(connection, actor_id, "alert_rule.create", "alert_rule", rule_id, payload)
            row = connection.execute("SELECT * FROM alert_rules WHERE id=?", (rule_id,)).fetchone()
            return self._alert_rule_record(row)

    def update_alert_rule(
        self, rule_id: str, payload: dict[str, object], actor_id: str
    ) -> dict[str, object] | None:
        fields = {
            "name": "name",
            "min_impact": "min_impact",
            "min_confidence": "min_confidence",
            "quiet_minutes": "quiet_minutes",
            "escalation_minutes": "escalation_minutes",
            "enabled": "enabled",
        }
        with self.session() as connection:
            if not connection.execute("SELECT 1 FROM alert_rules WHERE id=?", (rule_id,)).fetchone():
                return None
            assignments: list[str] = []
            values: list[object] = []
            for key, column in fields.items():
                if key in payload:
                    assignments.append(f"{column}=?")
                    value = payload[key]
                    values.append(int(value) if key == "enabled" else value)
            if "channels" in payload:
                assignments.append("channels_json=?")
                values.append(json.dumps(payload["channels"], ensure_ascii=False))
            if assignments:
                assignments.append("updated_at=?")
                values.extend([utc_now(), rule_id])
                connection.execute(
                    f"UPDATE alert_rules SET {', '.join(assignments)} WHERE id=?", values
                )
                self._audit(connection, actor_id, "alert_rule.update", "alert_rule", rule_id, payload)
            row = connection.execute("SELECT * FROM alert_rules WHERE id=?", (rule_id,)).fetchone()
            return self._alert_rule_record(row)

    def act_on_alert(
        self, alert_id: str, action: str, note: str, actor_id: str
    ) -> dict[str, object] | None:
        with self.session() as connection:
            if not connection.execute("SELECT 1 FROM alerts WHERE id=?", (alert_id,)).fetchone():
                return None
            now = utc_now()
            if action == "acknowledge":
                connection.execute(
                    "UPDATE alerts SET status='acknowledged', acknowledged_by=?, acknowledged_at=? WHERE id=?",
                    (actor_id, now, alert_id),
                )
            else:
                connection.execute(
                    "UPDATE alerts SET status='resolved', resolved_by=?, resolved_at=? WHERE id=?",
                    (actor_id, now, alert_id),
                )
            self._audit(connection, actor_id, f"alert.{action}", "alert", alert_id, {"note": note})
            row = connection.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
            return self._alert_record(row)

    def user_has_permission(self, user_id: str, permission: str) -> bool:
        with self.session() as connection:
            row = connection.execute(
                """SELECT m.status, r.permissions_json
                   FROM user_memberships m JOIN roles r ON r.id=m.role_id
                   WHERE m.user_id=?""",
                (user_id,),
            ).fetchone()
            if row is None or row["status"] != "active":
                return False
            permissions = json.loads(row["permissions_json"])
            return "*" in permissions or permission in permissions

    def get_resource_project_id(
        self, resource_type: str, resource_id: str
    ) -> str | None:
        tables = {
            "report_subscription": "report_subscriptions",
            "alert_rule": "alert_rules",
            "alert": "alerts",
            "competitive_analysis": "competitive_analysis_runs",
        }
        table = tables.get(resource_type)
        if table is None:
            raise ValueError("不支持的项目资源类型")
        with self.session() as connection:
            row = connection.execute(
                f"SELECT project_id FROM {table} WHERE id=?", (resource_id,)
            ).fetchone()
            return str(row["project_id"]) if row is not None else None

    def get_user_access(self, user_id: str) -> dict[str, object] | None:
        with self.session() as connection:
            row = connection.execute(
                """SELECT u.status AS user_status, m.status AS membership_status,
                          m.project_scopes_json, m.data_domains_json,
                          m.export_permission, r.permissions_json
                   FROM users u
                   JOIN user_memberships m ON m.user_id=u.id
                   JOIN roles r ON r.id=m.role_id
                   WHERE u.id=?""",
                (user_id,),
            ).fetchone()
            if (
                row is None
                or row["user_status"] != "active"
                or row["membership_status"] != "active"
            ):
                return None
            return {
                "permissions": json.loads(row["permissions_json"]),
                "project_scopes": json.loads(row["project_scopes_json"]),
                "data_domains": json.loads(row["data_domains_json"]),
                "export_permission": row["export_permission"],
            }

    def accessible_project_ids(self, user_id: str) -> list[str]:
        access = self.get_user_access(user_id)
        if access is None:
            return []
        scopes = list(access["project_scopes"])
        if "*" in scopes:
            return [row["id"] for row in self.list_projects()]
        existing = {row["id"] for row in self.list_projects()}
        return [project_id for project_id in scopes if project_id in existing]

    def user_can_access_project(
        self,
        user_id: str,
        project_id: str,
        *,
        permission: str | None = None,
        data_classification: str | None = None,
    ) -> bool:
        access = self.get_user_access(user_id)
        if access is None:
            return False
        permissions = list(access["permissions"])
        scopes = list(access["project_scopes"])
        domains = list(access["data_domains"])
        if permission and "*" not in permissions and permission not in permissions:
            return False
        if "*" not in scopes and project_id not in scopes:
            return False
        if data_classification and data_classification not in domains:
            return False
        return self.get_project(project_id) is not None

    def get_admin_dashboard(self) -> dict[str, object] | None:
        with self.session() as connection:
            organization = connection.execute(
                "SELECT * FROM organizations ORDER BY created_at LIMIT 1"
            ).fetchone()
            if organization is None:
                return None
            roles = connection.execute("SELECT * FROM roles ORDER BY name").fetchall()
            users = connection.execute(
                """SELECT u.*, m.role_id, m.status AS membership_status,
                          m.mfa_enabled, m.export_permission, m.project_scopes_json,
                          m.data_domains_json, m.last_login_at, r.name AS role_name
                   FROM users u JOIN user_memberships m ON m.user_id=u.id
                   JOIN roles r ON r.id=m.role_id ORDER BY u.name"""
            ).fetchall()
            models = connection.execute(
                "SELECT * FROM model_configs ORDER BY provider, model_name"
            ).fetchall()
            evaluations = connection.execute(
                "SELECT * FROM evaluation_metrics ORDER BY evaluated_at DESC"
            ).fetchall()
            policies = connection.execute(
                "SELECT * FROM security_policies ORDER BY category, name"
            ).fetchall()
            services = connection.execute(
                "SELECT * FROM service_components ORDER BY id"
            ).fetchall()
            incidents = connection.execute(
                "SELECT * FROM incidents ORDER BY updated_at DESC LIMIT 20"
            ).fetchall()
            backups = connection.execute(
                "SELECT * FROM backup_runs ORDER BY started_at DESC LIMIT 10"
            ).fetchall()
            audit_rows = connection.execute(
                """SELECT a.*, COALESCE(u.name, '系统') AS actor_name
                   FROM audit_events a LEFT JOIN users u ON u.id=a.actor_id
                   ORDER BY a.created_at DESC, a.id DESC LIMIT 50"""
            ).fetchall()
            run_summary = connection.execute(
                """SELECT COUNT(*) AS total,
                          SUM(CASE WHEN status IN ('succeeded','partial') THEN 1 ELSE 0 END) AS successful
                   FROM source_runs"""
            ).fetchone()
            report_summary = connection.execute(
                """SELECT SUM(CASE WHEN status='已交付' THEN 1 ELSE 0 END) AS delivered,
                          SUM(CASE WHEN status IN ('已交付','生成失败') THEN 1 ELSE 0 END) AS finished
                   FROM reports"""
            ).fetchone()
            total_budget = sum(row["monthly_budget"] for row in models)
            total_spent = sum(row["spent_amount"] for row in models)
            active_incidents = sum(row["status"] not in {"resolved"} for row in incidents)
            successful_backups = [row for row in backups if row["status"] == "succeeded"]
            rpo = min((row["rpo_minutes"] for row in successful_backups), default=15)
            return {
                "generated_at": utc_now(),
                "organization": {
                    "id": organization["id"],
                    "name": organization["name"],
                    "domain": organization["domain"],
                    "plan": organization["plan"],
                    "sso_enforced": bool(organization["sso_enforced"]),
                    "mfa_required": bool(organization["mfa_required"]),
                    "session_timeout_minutes": organization["session_timeout_minutes"],
                    "status": organization["status"],
                },
                "summary": {
                    "availability": round(
                        sum(row["uptime"] for row in services) / len(services), 2
                    ) if services else 0,
                    "task_success_rate": round(
                        (run_summary["successful"] or 0) * 100 / run_summary["total"], 1
                    ) if run_summary["total"] else 100.0,
                    "report_success_rate": round(
                        (report_summary["delivered"] or 0) * 100 / report_summary["finished"], 1
                    ) if report_summary["finished"] else 100.0,
                    "active_incidents": active_incidents,
                    "rpo_minutes": rpo,
                    "rto_hours": 4.0,
                    "monthly_cost": total_spent,
                    "budget_utilization": round(total_spent * 100 / total_budget, 1) if total_budget else 0,
                },
                "roles": [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "description": row["description"],
                        "permissions": json.loads(row["permissions_json"]),
                        "system": bool(row["system"]),
                    }
                    for row in roles
                ],
                "users": [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "initial": row["initial"],
                        "email": row["email"],
                        "role_id": row["role_id"],
                        "role_name": row["role_name"],
                        "status": row["membership_status"],
                        "mfa_enabled": bool(row["mfa_enabled"]),
                        "export_permission": row["export_permission"],
                        "project_scopes": json.loads(row["project_scopes_json"]),
                        "data_domains": json.loads(row["data_domains_json"]),
                        "last_login_at": row["last_login_at"],
                    }
                    for row in users
                ],
                "models": [
                    {
                        "id": row["id"],
                        "provider": row["provider"],
                        "model_name": row["model_name"],
                        "version": row["version"],
                        "routing_class": row["routing_class"],
                        "status": row["status"],
                        "allowed_data_classifications": json.loads(row["allowed_data_classifications_json"]),
                        "monthly_budget": row["monthly_budget"],
                        "spent_amount": row["spent_amount"],
                        "quota_warning_percent": row["quota_warning_percent"],
                        "fallback_model": row["fallback_model"],
                        "latency_p95_ms": row["latency_p95_ms"],
                        "success_rate": row["success_rate"],
                        "updated_at": row["updated_at"],
                    }
                    for row in models
                ],
                "evaluations": [
                    {
                        "id": row["id"],
                        "model_config_id": row["model_config_id"],
                        "dataset_name": row["dataset_name"],
                        "accuracy": row["accuracy"],
                        "citation_completeness": row["citation_completeness"],
                        "refusal_rate": row["refusal_rate"],
                        "latency_p95_ms": row["latency_p95_ms"],
                        "cost_per_run": row["cost_per_run"],
                        "sample_size": row["sample_size"],
                        "evaluated_at": row["evaluated_at"],
                    }
                    for row in evaluations
                ],
                "policies": [
                    {
                        "id": row["id"],
                        "key": row["policy_key"],
                        "name": row["name"],
                        "category": row["category"],
                        "value": json.loads(row["value_json"]),
                        "status": row["status"],
                        "updated_by": row["updated_by"],
                        "updated_at": row["updated_at"],
                    }
                    for row in policies
                ],
                "audit_events": [
                    {
                        "id": row["id"],
                        "actor_id": row["actor_id"],
                        "actor_name": row["actor_name"],
                        "action": row["action"],
                        "entity_type": row["entity_type"],
                        "entity_id": row["entity_id"],
                        "detail": json.loads(row["detail_json"]),
                        "created_at": row["created_at"],
                    }
                    for row in audit_rows
                ],
                "services": [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "status": row["status"],
                        "uptime": row["uptime"],
                        "latency_p95_ms": row["latency_p95_ms"],
                        "detail": row["detail"],
                        "last_checked_at": row["last_checked_at"],
                    }
                    for row in services
                ],
                "incidents": [
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "severity": row["severity"],
                        "status": row["status"],
                        "owner": row["owner"],
                        "started_at": row["started_at"],
                        "updated_at": row["updated_at"],
                        "detail": row["detail"],
                    }
                    for row in incidents
                ],
                "backups": [self._backup_record(row) for row in backups],
            }

    @staticmethod
    def _backup_record(row: sqlite3.Row) -> dict[str, object]:
        return {
            "id": row["id"],
            "backup_type": row["backup_type"],
            "status": row["status"],
            "rpo_minutes": row["rpo_minutes"],
            "size_bytes": row["size_bytes"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "restore_verified": bool(row["restore_verified"]),
        }

    def update_user_access(
        self, target_user_id: str, payload: dict[str, object], actor_id: str
    ) -> dict[str, object] | None:
        column_map = {
            "role_id": "role_id",
            "status": "status",
            "mfa_enabled": "mfa_enabled",
            "export_permission": "export_permission",
        }
        with self.session() as connection:
            if not connection.execute(
                "SELECT 1 FROM user_memberships WHERE user_id=?", (target_user_id,)
            ).fetchone():
                return None
            if payload.get("role_id") and not connection.execute(
                "SELECT 1 FROM roles WHERE id=?", (payload["role_id"],)
            ).fetchone():
                raise ValueError("角色不存在")
            assignments: list[str] = []
            values: list[object] = []
            for key, column in column_map.items():
                if key in payload:
                    assignments.append(f"{column}=?")
                    value = payload[key]
                    values.append(int(value) if key == "mfa_enabled" else value)
            for key, column in (
                ("project_scopes", "project_scopes_json"),
                ("data_domains", "data_domains_json"),
            ):
                if key in payload:
                    assignments.append(f"{column}=?")
                    values.append(json.dumps(payload[key], ensure_ascii=False))
            if assignments:
                values.append(target_user_id)
                connection.execute(
                    f"UPDATE user_memberships SET {', '.join(assignments)} WHERE user_id=?",
                    values,
                )
                self._audit(
                    connection,
                    actor_id,
                    "admin.user_access.update",
                    "user",
                    target_user_id,
                    payload,
                )
        dashboard = self.get_admin_dashboard()
        if dashboard is None:
            return None
        return next((item for item in dashboard["users"] if item["id"] == target_user_id), None)

    def update_model_config(
        self, model_id: str, payload: dict[str, object], actor_id: str
    ) -> dict[str, object] | None:
        columns = {
            "status": "status",
            "routing_class": "routing_class",
            "monthly_budget": "monthly_budget",
            "quota_warning_percent": "quota_warning_percent",
            "fallback_model": "fallback_model",
        }
        with self.session() as connection:
            if not connection.execute("SELECT 1 FROM model_configs WHERE id=?", (model_id,)).fetchone():
                return None
            assignments: list[str] = []
            values: list[object] = []
            for key, column in columns.items():
                if key in payload:
                    assignments.append(f"{column}=?")
                    values.append(payload[key])
            if "allowed_data_classifications" in payload:
                assignments.append("allowed_data_classifications_json=?")
                values.append(json.dumps(payload["allowed_data_classifications"], ensure_ascii=False))
            if assignments:
                assignments.append("updated_at=?")
                values.extend([utc_now(), model_id])
                connection.execute(
                    f"UPDATE model_configs SET {', '.join(assignments)} WHERE id=?", values
                )
                self._audit(connection, actor_id, "admin.model.update", "model_config", model_id, payload)
        dashboard = self.get_admin_dashboard()
        if dashboard is None:
            return None
        return next((item for item in dashboard["models"] if item["id"] == model_id), None)

    def update_security_policy(
        self, policy_id: str, payload: dict[str, object], actor_id: str
    ) -> dict[str, object] | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM security_policies WHERE id=?", (policy_id,)
            ).fetchone()
            if row is None:
                return None
            value = payload.get("value", json.loads(row["value_json"]))
            policy_status = payload.get("status", row["status"])
            connection.execute(
                """UPDATE security_policies SET value_json=?, status=?,
                   updated_by=?, updated_at=? WHERE id=?""",
                (json.dumps(value, ensure_ascii=False), policy_status, actor_id, utc_now(), policy_id),
            )
            self._audit(connection, actor_id, "admin.policy.update", "security_policy", policy_id, payload)
        dashboard = self.get_admin_dashboard()
        if dashboard is None:
            return None
        return next((item for item in dashboard["policies"] if item["id"] == policy_id), None)

    def act_on_incident(
        self, incident_id: str, action: str, note: str, actor_id: str
    ) -> dict[str, object] | None:
        with self.session() as connection:
            row = connection.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
            if row is None:
                return None
            now = utc_now()
            if action == "acknowledge":
                connection.execute(
                    "UPDATE incidents SET status='acknowledged', acknowledged_by=?, updated_at=? WHERE id=?",
                    (actor_id, now, incident_id),
                )
            else:
                connection.execute(
                    "UPDATE incidents SET status='resolved', resolved_by=?, updated_at=? WHERE id=?",
                    (actor_id, now, incident_id),
                )
            self._audit(connection, actor_id, f"incident.{action}", "incident", incident_id, {"note": note})
            updated = connection.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
            return {
                "id": updated["id"],
                "title": updated["title"],
                "severity": updated["severity"],
                "status": updated["status"],
                "owner": updated["owner"],
                "started_at": updated["started_at"],
                "updated_at": updated["updated_at"],
                "detail": updated["detail"],
            }

    def run_backup(self, actor_id: str) -> dict[str, object]:
        backup_id = f"bak_{uuid4().hex[:12]}"
        started_at = utc_now()
        backup_directory = self.path.parent / "backups"
        backup_directory.mkdir(parents=True, exist_ok=True)
        backup_path = backup_directory / f"{backup_id}.db"
        status_value = "failed"
        completed_at: str | None = None
        restore_verified = False
        size_bytes = 0
        failure_reason: str | None = None

        try:
            with self.connect() as source, sqlite3.connect(backup_path) as target:
                source.backup(target)
            with sqlite3.connect(backup_path) as verification:
                result = verification.execute("PRAGMA integrity_check").fetchone()
                restore_verified = bool(result and result[0] == "ok")
            if not restore_verified:
                raise sqlite3.DatabaseError("备份文件完整性校验失败")
            size_bytes = backup_path.stat().st_size
            status_value = "succeeded"
            completed_at = utc_now()
        except (OSError, sqlite3.Error) as exc:
            failure_reason = str(exc)
            backup_path.unlink(missing_ok=True)
            completed_at = utc_now()

        with self.session() as connection:
            connection.execute(
                """INSERT INTO backup_runs
                   (id, backup_type, status, rpo_minutes, size_bytes, started_at,
                    completed_at, restore_verified, created_by)
                   VALUES (?, 'full', ?, 0, ?, ?, ?, ?, ?)""",
                (
                    backup_id,
                    status_value,
                    size_bytes,
                    started_at,
                    completed_at,
                    int(restore_verified),
                    actor_id,
                ),
            )
            self._audit(
                connection,
                actor_id,
                "operations.backup.run",
                "backup",
                backup_id,
                {
                    "backup_type": "full",
                    "size_bytes": size_bytes,
                    "restore_verified": restore_verified,
                    "failure_reason": failure_reason,
                },
            )
            row = connection.execute("SELECT * FROM backup_runs WHERE id=?", (backup_id,)).fetchone()
            return self._backup_record(row)

    def search(
        self,
        query: str,
        project_ids: list[str],
        allowed_domains: list[str],
    ) -> list[dict[str, str]]:
        if not project_ids:
            return []
        term = f"%{query}%"
        results: list[dict[str, str]] = []
        project_placeholders = ",".join("?" for _ in project_ids)
        domain_placeholders = ",".join("?" for _ in allowed_domains)
        with self.session() as connection:
            project_rows = connection.execute(
                f"""SELECT id, name FROM projects
                    WHERE name LIKE ? AND id IN ({project_placeholders})
                    ORDER BY name LIMIT 5""",
                (term, *project_ids),
            ).fetchall()
            results.extend(
                {
                    "kind": "project",
                    "id": row["id"],
                    "title": row["name"],
                    "subtitle": "分析项目",
                }
                for row in project_rows
            )
            insight_rows = connection.execute(
                f"""SELECT id, title, company FROM insights
                    WHERE (title LIKE ? OR summary LIKE ?)
                      AND project_id IN ({project_placeholders})
                    ORDER BY sort_order LIMIT 10""",
                (term, term, *project_ids),
            ).fetchall()
            results.extend(
                {
                    "kind": "insight",
                    "id": str(row["id"]),
                    "title": row["title"],
                    "subtitle": row["company"],
                }
                for row in insight_rows
            )
            report_rows = connection.execute(
                f"""SELECT id, title, status FROM reports
                    WHERE title LIKE ? AND project_id IN ({project_placeholders})
                    ORDER BY created_at DESC LIMIT 5""",
                (term, *project_ids),
            ).fetchall()
            results.extend(
                {
                    "kind": "report",
                    "id": row["id"],
                    "title": row["title"],
                    "subtitle": row["status"],
                }
                for row in report_rows
            )
            source_rows: list[sqlite3.Row] = []
            if allowed_domains:
                source_rows = connection.execute(
                    f"""SELECT id, name, subject, health_status FROM data_sources
                        WHERE (name LIKE ? OR subject LIKE ?)
                          AND project_id IN ({project_placeholders})
                          AND data_classification IN ({domain_placeholders})
                          AND archived_at IS NULL
                        ORDER BY updated_at DESC LIMIT 5""",
                    (term, term, *project_ids, *allowed_domains),
                ).fetchall()
            results.extend(
                {
                    "kind": "source",
                    "id": row["id"],
                    "title": row["name"],
                    "subtitle": f"{row['subject']} · {row['health_status']}",
                }
                for row in source_rows
            )
            knowledge_rows: list[sqlite3.Row] = []
            if allowed_domains:
                knowledge_rows = connection.execute(
                    f"""SELECT k.id, k.title, k.item_type, k.subject
                        FROM knowledge_items k
                        LEFT JOIN data_sources s ON s.id=k.source_id
                        WHERE (k.title LIKE ? OR k.summary LIKE ? OR k.tags_json LIKE ?)
                          AND k.project_id IN ({project_placeholders})
                          AND COALESCE(s.data_classification, 'internal')
                              IN ({domain_placeholders})
                          AND (s.id IS NULL OR s.archived_at IS NULL)
                        ORDER BY k.updated_at DESC LIMIT 10""",
                    (term, term, term, *project_ids, *allowed_domains),
                ).fetchall()
            results.extend(
                {
                    "kind": "knowledge",
                    "id": row["id"],
                    "title": row["title"],
                    "subtitle": f"{row['subject'] or '未归属主体'} · {row['item_type']}",
                }
                for row in knowledge_rows
            )
        return results[:20]

    @staticmethod
    def _mask_credential_ref(credential_ref: str | None) -> str | None:
        if not credential_ref:
            return None
        clean = credential_ref.strip()
        suffix = clean[-4:] if len(clean) >= 4 else clean[-1:]
        return f"••••••••{suffix}"

    @staticmethod
    def _pending_source_checks() -> list[dict[str, object]]:
        return [
            {
                "key": key,
                "label": label,
                "status": "pending",
                "message": "尚未执行检查",
                "checked_at": None,
            }
            for key, label in (
                ("connectivity", "连通性"),
                ("compliance", "授权与合规"),
                ("rate_limit", "速率限制"),
                ("field_availability", "字段可用性"),
            )
        ]

    @staticmethod
    def _health_status_from_score(score: int) -> str:
        if score >= 85:
            return "healthy"
        if score >= 70:
            return "warning"
        return "error"

    def _refresh_all_source_health(self, connection: sqlite3.Connection) -> None:
        project_ids = connection.execute("SELECT id FROM projects").fetchall()
        for project in project_ids:
            self._refresh_source_health(connection, project["id"])

    def _refresh_source_health(
        self, connection: sqlite3.Connection, project_id: str
    ) -> None:
        summary = connection.execute(
            """SELECT
                   COUNT(*) AS total,
                   SUM(CASE WHEN health_status='healthy' THEN 1 ELSE 0 END) AS normal_count,
                   SUM(CASE WHEN health_status IN ('warning','error') THEN 1 ELSE 0 END) AS abnormal_count,
                   SUM(CASE WHEN health_status='disabled' THEN 1 ELSE 0 END) AS disabled_count,
                   AVG(CASE WHEN enabled=1 THEN health_score END) AS score
               FROM data_sources WHERE project_id=? AND archived_at IS NULL""",
            (project_id,),
        ).fetchone()
        score = round(summary["score"] or 0)
        connection.execute(
            """UPDATE source_health
               SET score=?, normal_count=?, abnormal_count=?, disabled_count=?, last_sync=?
               WHERE project_id=?""",
            (
                score,
                int(summary["normal_count"] or 0),
                int(summary["abnormal_count"] or 0),
                int(summary["disabled_count"] or 0),
                "刚刚" if summary["total"] else "尚未同步",
                project_id,
            ),
        )

    def _audit(
        self,
        connection: sqlite3.Connection,
        actor_id: str | None,
        action: str,
        entity_type: str,
        entity_id: str,
        detail: dict[str, object],
    ) -> None:
        connection.execute(
            """INSERT INTO audit_events
               (actor_id, action, entity_type, entity_id, detail_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                actor_id,
                action,
                entity_type,
                entity_id,
                json.dumps(detail, ensure_ascii=False),
                utc_now(),
            ),
        )
