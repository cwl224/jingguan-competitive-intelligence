from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

from .database import Database, utc_now
from .schemas import (
    DailyBrief,
    CollectionDocumentDetail,
    CollectionDocumentListResponse,
    CollectionDocumentListSummary,
    CollectionDocumentSummary,
    Evidence,
    Headline,
    InsightDetail,
    InsightSummary,
    KnowledgeCollectionSummary,
    KnowledgeDocumentTrace,
    KnowledgeEvidenceTrace,
    KnowledgeItemDetail,
    KnowledgeItemSummary,
    KnowledgeOverview,
    KnowledgeOverviewSummary,
    KnowledgeRevision,
    KnowledgeSourceTrace,
    KnowledgeStorageSummary,
    Metric,
    OrchestrationDashboard,
    OrchestrationSchedule,
    OrchestrationSummary,
    ProjectSummary,
    ReportSummary,
    ReviewItem,
    ReviewQueue,
    SourceHealth,
    SourceHealthMetrics,
    SourceListResponse,
    SourceListSummary,
    SourceRecord,
    SourceRunListResponse,
    SourceRunListSummary,
    SourceRunSummary,
    TrendSeries,
    UserSummary,
    WorkbenchResponse,
    WorkflowNodeDefinition,
    WorkflowStep,
)


def source_from_row(row: sqlite3.Row) -> SourceRecord:
    checks = json.loads(row["check_results_json"])
    activation_ready = bool(checks) and all(
        item["status"] in {"passed", "not_applicable"} for item in checks
    )
    collection_config = {
        key: value
        for key, value in json.loads(row["collection_config_json"] or "{}").items()
        if not key.startswith("_")
    }
    return SourceRecord(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        source_type=row["source_type"],
        endpoint=row["endpoint"],
        subject=row["subject"],
        access_method=row["access_method"],
        crawl_strategy=row["crawl_strategy"],
        regions=json.loads(row["regions_json"]),
        authorization_basis=row["authorization_basis"],
        authorization_status=row["authorization_status"],
        data_classification=row["data_classification"],
        retention_days=row["retention_days"],
        schedule_frequency=row["schedule_frequency"],
        rate_limit_per_minute=row["rate_limit_per_minute"],
        concurrency_limit=row["concurrency_limit"],
        task_timeout_seconds=row["task_timeout_seconds"],
        max_attempts=row["max_attempts"],
        retry_backoff_seconds=row["retry_backoff_seconds"],
        priority=row["priority"],
        circuit_state=row["circuit_state"],
        circuit_open_until=row["circuit_open_until"],
        credential_masked=row["credential_masked"],
        credential_expires_at=row["credential_expires_at"],
        fields_available=json.loads(row["fields_json"]),
        collection_config=collection_config,
        robots_acknowledged=bool(row["robots_acknowledged"]),
        terms_acknowledged=bool(row["terms_acknowledged"]),
        enabled=bool(row["enabled"]),
        status=row["health_status"],
        health_score=row["health_score"],
        health=SourceHealthMetrics(
            success_rate=row["success_rate"],
            consecutive_failures=row["consecutive_failures"],
            average_latency_ms=row["average_latency_ms"],
            freshness_minutes=row["freshness_minutes"],
            content_change_rate=row["content_change_rate"],
            parser_completeness=row["parser_completeness"],
        ),
        checks=checks,
        activation_ready=activation_ready,
        last_checked_at=row["last_checked_at"],
        last_collected_at=row["last_collected_at"],
        last_success_at=row["last_success_at"],
        next_run_at=row["next_run_at"],
        archived_at=row["archived_at"],
        archived_by=row["archived_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def workflow_step_from_row(row: sqlite3.Row) -> WorkflowStep:
    return WorkflowStep(
        key=row["step_key"],
        name=row["step_name"],
        agent=row["agent_name"],
        order=row["step_order"],
        status=row["status"],
        attempt=row["attempt"],
        max_attempts=row["max_attempts"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        duration_ms=row["duration_ms"],
        error_type=row["error_type"],
        error_message=row["error_message"],
        output_summary=row["output_summary"],
    )


def source_run_from_row(row: sqlite3.Row, database: Database) -> SourceRunSummary:
    return SourceRunSummary(
        id=row["id"],
        source_id=row["source_id"],
        project_id=row["project_id"],
        source_name=row["source_name"],
        source_type=row["source_type"],
        trigger_type=row["trigger_type"],
        status=row["status"],
        priority=row["priority"],
        attempt=row["attempt"],
        max_attempts=row["max_attempts"],
        timeout_seconds=row["timeout_seconds"],
        backoff_seconds=row["backoff_seconds"],
        scheduled_for=row["scheduled_for"],
        available_at=row["available_at"],
        next_retry_at=row["next_retry_at"],
        retry_delays=json.loads(row["retry_delays_json"] or "[]"),
        retry_of=row["retry_of"],
        recovery_of=row["recovery_of"],
        recovered_from_restart=bool(row["recovered_from_restart"]),
        workflow_version=row["workflow_version"],
        workflow_steps=[
            workflow_step_from_row(step)
            for step in database.list_workflow_steps(row["id"])
        ],
        items_discovered=row["items_discovered"],
        documents_created=row["documents_created"],
        documents_updated=row["documents_updated"],
        duplicates_skipped=row["duplicates_skipped"],
        error_type=row["error_type"],
        error_message=row["error_message"],
        request_summary=row["request_summary"],
        parser_steps=json.loads(row["parser_steps_json"] or "[]"),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        created_at=row["created_at"],
    )


def get_source_runs(
    database: Database,
    project_id: str,
    source_id: str | None = None,
    status_filter: str | None = None,
    allowed_domains: list[str] | None = None,
) -> SourceRunListResponse | None:
    if database.get_project(project_id) is None:
        return None
    all_rows = database.list_source_runs(
        project_id, source_id=source_id, allowed_domains=allowed_domains
    )
    rows = (
        database.list_source_runs(
            project_id,
            source_id=source_id,
            status_filter=status_filter,
            allowed_domains=allowed_domains,
        )
        if status_filter
        else all_rows
    )
    return SourceRunListResponse(
        project_id=project_id,
        summary=SourceRunListSummary(
            total=len(all_rows),
            running=sum(row["status"] in {"queued", "running"} for row in all_rows),
            succeeded=sum(row["status"] in {"succeeded", "partial"} for row in all_rows),
            failed=sum(
                row["status"] in {"failed", "manual_review"} for row in all_rows
            ),
        ),
        items=[source_run_from_row(row, database) for row in rows],
    )


def get_orchestration_dashboard(
    database: Database, project_id: str
) -> OrchestrationDashboard | None:
    if database.get_project(project_id) is None:
        return None
    metric_row = database.orchestration_metrics(project_id)
    run_rows = database.list_source_runs(project_id, limit=200)
    runs = [source_run_from_row(row, database) for row in run_rows]
    recoverable_ids = set(database.latest_recoverable_run_ids(project_id))
    exceptions = [run for run in runs if run.id in recoverable_ids]
    finished_24h = int(metric_row["finished_24h"] or 0)
    success_rate = (
        round(int(metric_row["ok_24h"] or 0) / finished_24h * 100, 1)
        if finished_24h
        else 100.0
    )
    schedules = [
        OrchestrationSchedule(
            source=source_from_row(row),
            active_runs=int(row["active_runs"] or 0),
            last_run_status=row["last_run_status"],
        )
        for row in database.list_orchestration_schedules(project_id)
    ]
    return OrchestrationDashboard(
        project_id=project_id,
        generated_at=utc_now(),
        summary=OrchestrationSummary(
            scheduled_sources=int(metric_row["scheduled_sources"] or 0),
            queued=int(metric_row["queued"] or 0),
            running=int(metric_row["running"] or 0),
            exceptions=len(exceptions),
            success_rate_24h=success_rate,
            recovered_24h=int(metric_row["recovered_24h"] or 0),
        ),
        workflow_nodes=[
            WorkflowNodeDefinition(
                key="collect",
                name="获取内容",
                agent="采集 Agent",
                description="连接来源并受超时、限流与合规策略约束",
            ),
            WorkflowNodeDefinition(
                key="normalize",
                name="解析与标准化",
                agent="内容理解 Agent",
                description="提取正文、元数据并统一结构",
            ),
            WorkflowNodeDefinition(
                key="deduplicate",
                name="指纹与版本判断",
                agent="去重 Agent",
                description="内容指纹去重并维护版本链",
            ),
            WorkflowNodeDefinition(
                key="quality_gate",
                name="质量门禁",
                agent="质量 Agent",
                description="校验完整度并决定成功、部分成功或异常恢复",
            ),
        ],
        schedules=schedules,
        runs=runs,
        exceptions=exceptions,
    )


def collection_document_summary_from_row(
    row: sqlite3.Row,
) -> CollectionDocumentSummary:
    readable_text = row["readable_text"] or ""
    excerpt = " ".join(readable_text.split())[:220]
    return CollectionDocumentSummary(
        id=row["id"],
        project_id=row["project_id"],
        source_id=row["source_id"],
        source_name=row["source_name"],
        source_type=row["source_type"],
        run_id=row["run_id"],
        canonical_url=row["canonical_url"],
        title=row["title"],
        published_at=row["published_at"],
        collected_at=row["collected_at"],
        language=row["language"],
        content_type=row["content_type"],
        content_hash=row["content_hash"],
        readable_excerpt=excerpt,
        word_count=len(readable_text.split()),
        version=row["version_no"],
        is_latest=bool(row["is_latest"]),
    )


def collection_document_detail_from_row(
    row: sqlite3.Row,
) -> CollectionDocumentDetail:
    summary = collection_document_summary_from_row(row)
    return CollectionDocumentDetail(
        **summary.model_dump(),
        readable_text=row["readable_text"],
        metadata=json.loads(row["metadata_json"] or "{}"),
        structured_fields=json.loads(row["structured_fields_json"] or "{}"),
        parser_version=row["parser_version"],
        previous_document_id=row["previous_document_id"],
    )


def get_collection_documents(
    database: Database,
    project_id: str,
    source_id: str | None = None,
    latest_only: bool = True,
    query: str | None = None,
    allowed_domains: list[str] | None = None,
) -> CollectionDocumentListResponse | None:
    if database.get_project(project_id) is None:
        return None
    rows = database.list_collection_documents(
        project_id,
        source_id=source_id,
        latest_only=latest_only,
        query=query,
        allowed_domains=allowed_domains,
    )
    return CollectionDocumentListResponse(
        project_id=project_id,
        summary=CollectionDocumentListSummary(
            total=len(rows),
            latest=sum(bool(row["is_latest"]) for row in rows),
            sources=len({row["source_id"] for row in rows}),
        ),
        items=[collection_document_summary_from_row(row) for row in rows],
    )


def knowledge_collection_from_row(row: sqlite3.Row) -> KnowledgeCollectionSummary:
    return KnowledgeCollectionSummary(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        description=row["description"],
        color=row["color"],
        item_count=int(row["item_count"] or 0),
        updated_at=row["updated_at"],
    )


def knowledge_item_from_row(row: sqlite3.Row) -> KnowledgeItemSummary:
    return KnowledgeItemSummary(
        id=row["id"],
        project_id=row["project_id"],
        document_id=row["document_id"],
        source_id=row["source_id"],
        item_type=row["item_type"],
        title=row["title"],
        summary=row["summary"],
        subject=row["subject"],
        category=row["category"],
        language=row["language"],
        tags=json.loads(row["tags_json"] or "[]"),
        confidence=int(row["confidence"] or 0),
        quality_score=int(row["quality_score"] or 0),
        review_status=row["review_status"],
        validity_status=row["validity_status"],
        source_count=int(row["source_count"] or 0),
        source_name=row["source_name"] or "来源已移除",
        source_url=row["source_url"] or "",
        evidence_excerpt=row["evidence_excerpt"],
        extraction_method=row["extraction_method"],
        published_at=row["published_at"],
        updated_at=row["updated_at"],
        collection_count=int(row["collection_count"] or 0),
    )


def get_knowledge_overview(
    database: Database,
    project_id: str,
    *,
    query: str | None = None,
    item_type: str | None = None,
    review_status: str | None = None,
    source_id: str | None = None,
    collection_id: str | None = None,
    allowed_domains: list[str] | None = None,
) -> KnowledgeOverview | None:
    if database.get_project(project_id) is None:
        return None
    all_rows = database.list_knowledge_items(
        project_id, limit=1000, allowed_domains=allowed_domains
    )
    rows = database.list_knowledge_items(
        project_id,
        query=query,
        item_type=item_type,
        review_status=review_status,
        source_id=source_id,
        collection_id=collection_id,
        allowed_domains=allowed_domains,
    )
    collections = [
        knowledge_collection_from_row(row)
        for row in database.list_knowledge_collections(project_id)
    ]
    metrics = database.knowledge_storage_metrics(project_id, allowed_domains)
    type_counts = {
        kind: sum(row["item_type"] == kind for row in all_rows)
        for kind in ("fact", "entity", "event", "insight")
    }
    evidence_count = sum(
        bool(row["evidence_excerpt"] and row["source_id"]) for row in all_rows
    )
    return KnowledgeOverview(
        project_id=project_id,
        generated_at=utc_now(),
        summary=KnowledgeOverviewSummary(
            knowledge_items=len(all_rows),
            verified=sum(row["review_status"] == "verified" for row in all_rows),
            review_required=sum(
                row["review_status"] == "review_required" for row in all_rows
            ),
            conflicts=sum(row["review_status"] == "conflict" for row in all_rows),
            collections=len(collections),
            sources=int(metrics["sources"] or 0),
            evidence_coverage=(
                round(evidence_count / len(all_rows) * 100) if all_rows else 0
            ),
            latest_update=max((row["updated_at"] for row in all_rows), default=None),
        ),
        storage=KnowledgeStorageSummary(
            raw_documents=int(metrics["raw_documents"] or 0),
            document_versions=int(metrics["document_versions"] or 0),
            processed_documents=int(metrics["processed_documents"] or 0),
            storage_bytes=int(metrics["storage_bytes"] or 0),
        ),
        type_counts=type_counts,
        items=[knowledge_item_from_row(row) for row in rows],
        collections=collections,
    )


def get_knowledge_item_detail(
    database: Database, item_id: str
) -> KnowledgeItemDetail | None:
    row = database.get_knowledge_item(item_id)
    if row is None:
        return None
    summary = knowledge_item_from_row(row)
    document = None
    if row["document_id"]:
        document = KnowledgeDocumentTrace(
            id=row["document_id"],
            title=row["document_title"] or row["title"],
            version=int(row["document_version"] or 1),
            content_hash=row["document_content_hash"] or "",
            parser_version=row["document_parser_version"] or "",
            collected_at=row["document_collected_at"] or row["created_at"],
            published_at=row["document_published_at"],
            raw_available=bool(row["raw_available"]),
        )
    revisions = [
        KnowledgeRevision(
            version=int(item["version_no"]),
            action=item["action"],
            snapshot=json.loads(item["snapshot_json"] or "{}"),
            note=item["note"],
            changed_by=item["changed_by_name"],
            created_at=item["created_at"],
        )
        for item in database.list_knowledge_revisions(item_id)
    ]
    collections = [
        knowledge_collection_from_row(item)
        for item in database.list_knowledge_item_collections(item_id)
    ]
    return KnowledgeItemDetail(
        **summary.model_dump(),
        content=row["content"],
        source=KnowledgeSourceTrace(
            id=row["source_id"],
            name=row["source_name"] or "来源已移除",
            url=row["source_url"] or "",
            authorization_status=row["source_authorization_status"],
            retention_days=row["source_retention_days"],
        ),
        document=document,
        evidence=KnowledgeEvidenceTrace(
            excerpt=row["evidence_excerpt"],
            start=row["evidence_start"],
            end=row["evidence_end"],
            extraction_method=row["extraction_method"],
        ),
        collections=collections,
        revisions=revisions,
    )


def get_sources(
    database: Database,
    project_id: str,
    status_filter: str | None = None,
    source_type: str | None = None,
    query: str | None = None,
    allowed_domains: list[str] | None = None,
) -> SourceListResponse | None:
    if database.get_project(project_id) is None:
        return None
    all_rows = database.list_sources(project_id, allowed_domains=allowed_domains)
    filtered_rows = database.list_sources(
        project_id, status_filter, source_type, query, allowed_domains
    )
    items = [source_from_row(row) for row in filtered_rows]
    enabled_rows = [row for row in all_rows if row["enabled"]]
    now = datetime.now(UTC)
    expiry_threshold = now + timedelta(days=30)
    expiring_credentials = 0
    for row in all_rows:
        expires_at = row["credential_expires_at"]
        if not expires_at:
            continue
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if expiry <= expiry_threshold:
            expiring_credentials += 1
    average_health = (
        round(sum(row["health_score"] for row in enabled_rows) / len(enabled_rows))
        if enabled_rows
        else 0
    )
    return SourceListResponse(
        project_id=project_id,
        summary=SourceListSummary(
            total=len(all_rows),
            enabled=len(enabled_rows),
            needs_attention=sum(
                row["health_status"] in {"warning", "error"} for row in all_rows
            ),
            disabled=sum(row["health_status"] == "disabled" for row in all_rows),
            expiring_credentials=expiring_credentials,
            average_health=average_health,
        ),
        items=items,
    )


def project_from_row(row: sqlite3.Row) -> ProjectSummary:
    return ProjectSummary(
        id=row["id"],
        name=row["name"],
        avatar=row["avatar"],
        template=row["template"],
        regions=json.loads(row["regions_json"]),
        status=row["status"],
    )


def insight_from_row(row: sqlite3.Row) -> InsightSummary:
    return InsightSummary(
        id=row["id"],
        time=row["time_label"],
        type=row["kind"],
        level=row["impact_level"],
        company=row["company"],
        title=row["title"],
        summary=row["summary"],
        sources=row["source_count"],
        confidence=row["confidence"],
    )


def review_from_row(row: sqlite3.Row) -> ReviewItem:
    return ReviewItem(
        id=row["id"],
        company=row["company"],
        field=row["field_name"],
        reason=row["reason"],
        time=row["time_label"],
        tone=row["tone"],
        status=row["status"],
        claimed_by=row["claimed_by"],
    )


def report_from_row(row: sqlite3.Row) -> ReportSummary:
    return ReportSummary(
        id=row["id"],
        title=row["title"],
        meta=row["schedule_label"],
        state=row["status"],
        progress=row["progress"],
    )


def get_workbench(
    database: Database,
    project_id: str | None,
    range_key: str,
    user_id: str,
    accessible_project_ids: list[str] | None = None,
) -> WorkbenchResponse | None:
    project_row = database.get_project(project_id)
    user_row = database.get_user(user_id)
    if project_row is None or user_row is None:
        return None

    project = project_from_row(project_row)
    projects = [
        project_from_row(row)
        for row in database.list_projects(accessible_project_ids)
    ]
    metrics_row = database.get_metrics(project.id)
    brief_row = database.get_daily_brief(project.id)
    trend_rows = database.get_trend(project.id, range_key)
    health_row = database.get_source_health(project.id)
    insights = [insight_from_row(row) for row in database.list_insights(project.id)]
    reviews = [review_from_row(row) for row in database.list_reviews(project.id)]
    reports = [report_from_row(row) for row in database.list_reports(project.id)]

    metrics = [
        Metric(
            key="coverage",
            label="竞品覆盖率",
            value=f"{metrics_row['coverage_rate']:.1f}",
            unit="%",
            delta=f"{abs(metrics_row['coverage_delta']):g}%",
            trend="up" if metrics_row["coverage_delta"] >= 0 else "down",
            note="较上周",
        ),
        Metric(
            key="changes",
            label="新增变化",
            value=str(metrics_row["new_changes"]),
            unit="条",
            delta=f"{abs(metrics_row['new_changes_delta'])} 条",
            trend="up" if metrics_row["new_changes_delta"] >= 0 else "down",
            note="过去 24 小时",
        ),
        Metric(
            key="alerts",
            label="重大预警",
            value=str(metrics_row["major_alerts"]),
            unit="条",
            delta=f"{abs(metrics_row['major_alerts_delta'])} 条",
            trend="down",
            note="需优先查看",
            accent=True,
        ),
        Metric(
            key="reviews",
            label="待人工复核",
            value=str(metrics_row["pending_reviews"]),
            unit="项",
            delta=f"{abs(metrics_row['pending_reviews_delta'])} 项",
            trend="down",
            note="队列正在收敛",
        ),
    ]

    return WorkbenchResponse(
        project=project,
        projects=projects,
        user=UserSummary(
            id=user_row["id"], name=user_row["name"], initial=user_row["initial"]
        ),
        data_cutoff=metrics_row["data_cutoff"],
        headline=Headline(
            greeting=f"早上好，{user_row['name']}",
            new_changes=metrics_row["new_changes"],
            priority_changes=metrics_row["major_alerts"],
        ),
        daily_brief=DailyBrief(
            title=brief_row["title"],
            summary=brief_row["summary"],
            evidence_count=brief_row["evidence_count"],
            confidence=brief_row["confidence"],
            impact_level=brief_row["impact_level"],
            insight_id=brief_row["insight_id"],
        ),
        metrics=metrics,
        trend=TrendSeries(
            range=range_key,
            labels=[row["label"] for row in trend_rows],
            events=[row["event_count"] for row in trend_rows],
            high_impact=[row["high_impact_count"] for row in trend_rows],
        ),
        source_health=SourceHealth(
            score=health_row["score"],
            total=health_row["normal_count"]
            + health_row["abnormal_count"]
            + health_row["disabled_count"],
            normal=health_row["normal_count"],
            abnormal=health_row["abnormal_count"],
            disabled=health_row["disabled_count"],
            last_sync=health_row["last_sync"],
        ),
        insights=insights,
        review_queue=ReviewQueue(total=metrics_row["pending_reviews"], items=reviews),
        reports=reports,
    )


def get_insight_detail(database: Database, insight_id: int) -> InsightDetail | None:
    row = database.get_insight(insight_id)
    if row is None:
        return None
    evidence = [
        Evidence(
            id=item["id"],
            title=item["title"],
            source_name=item["source_name"],
            source_url=item["source_url"],
            excerpt=item["excerpt"],
            source_type=item["source_type"],
            published_at=item["published_at"],
        )
        for item in database.list_evidence(insight_id)
    ]
    summary = insight_from_row(row)
    return InsightDetail(
        **summary.model_dump(), recommendation=row["recommendation"], evidence=evidence
    )
