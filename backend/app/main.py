from contextlib import asynccontextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .auth import AuthenticationError, verify_access_token
from .config import Settings, load_settings
from .collector import CollectionEngine, CollectionScheduler
from .database import Database
from .processing import (
    DocumentProcessor,
    processing_detail_from_row,
    processing_summary_from_row,
)
from .competitive_agent import CompetitiveAnalysisAgent
from .rag import RAGEngine
from .schemas import (
    CompetitiveAnalysisOverview,
    CompetitiveAnalysisRequest,
    CompetitiveAnalysisResult,
    AdminDashboard,
    AdminUserAccessUpdate,
    AdminUserRecord,
    AlertAction,
    AlertRecord,
    AlertRuleCreate,
    AlertRuleRecord,
    AlertRuleUpdate,
    BackupActionResponse,
    HealthResponse,
    CollectionDocumentDetail,
    CollectionDocumentListResponse,
    FileUploadResponse,
    InsightDetail,
    KnowledgeCollectionCreate,
    KnowledgeCollectionSummary,
    KnowledgeItemDetail,
    KnowledgeOverview,
    KnowledgeReviewUpdate,
    IncidentAction,
    IncidentRecord,
    ModelConfigRecord,
    ModelConfigUpdate,
    OrchestrationActionResult,
    OrchestrationBulkRetry,
    OrchestrationDashboard,
    OrchestrationRecover,
    OrchestrationTrigger,
    ProcessingBatchRequest,
    ProcessingBatchResponse,
    ProcessingDocumentDetail,
    ProcessingDocumentSummary,
    ProcessingOptions,
    ProcessingOverview,
    ProcessingOverviewSummary,
    ProjectCreate,
    ProjectSummary,
    RAGQueryRequest,
    RAGResponse,
    ReportGenerate,
    ReportApproval,
    ReportRecord,
    ReportingDashboard,
    ReportSubscriptionRecord,
    ReportSubscriptionUpdate,
    ReportSummary,
    ReviewClaimResponse,
    SearchResponse,
    SearchResult,
    SourceActionResponse,
    SourceCreate,
    SourceCredentialRotate,
    SourceArchiveResponse,
    SourceListResponse,
    SourcePurgeRequest,
    SourcePurgeResponse,
    SourceRecord,
    SourceRunSummary,
    SourceRunListResponse,
    SourceScheduleUpdate,
    SourceStatusUpdate,
    SourceUpdate,
    SecurityPolicyRecord,
    SecurityPolicyUpdate,
    WorkbenchResponse,
)
from .report_exports import build_docx, build_pdf
from .services import (
    collection_document_detail_from_row,
    get_insight_detail,
    get_knowledge_item_detail,
    get_knowledge_overview,
    get_collection_documents,
    get_orchestration_dashboard,
    get_source_runs,
    get_sources,
    get_workbench,
    project_from_row,
    knowledge_collection_from_row,
    report_from_row,
    review_from_row,
    source_from_row,
    source_run_from_row,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or load_settings()
    if app_settings.environment == "production" and (
        app_settings.auth_secret == "development-only-change-me"
        or len(app_settings.auth_secret) < 32
    ):
        raise RuntimeError("生产环境必须配置至少 32 个字符的 AUTH_SECRET")
    database = Database(app_settings.database_path)
    collector = CollectionEngine(database, app_settings)
    processor = collector.processor
    rag_engine = RAGEngine(database)
    competitive_agent = CompetitiveAnalysisAgent(database, rag_engine)
    scheduler = CollectionScheduler(
        database,
        collector,
        app_settings.scheduler_poll_seconds,
        app_settings.scheduler_dispatch_batch,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.initialize()
        database.recover_interrupted_runs()
        if app_settings.scheduler_enabled:
            scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()

    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        debug=app_settings.debug,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.settings = app_settings
    app.state.database = database
    app.state.collector = collector
    app.state.processor = processor
    app.state.rag_engine = rag_engine
    app.state.competitive_agent = competitive_agent
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-User-Id"],
    )

    def get_database(request: Request) -> Database:
        return request.app.state.database

    def get_user_id(
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    ) -> str:
        authenticated_user = getattr(request.state, "user_id", None)
        if authenticated_user:
            return str(authenticated_user)
        current_settings: Settings = request.app.state.settings
        user_id: str | None = None
        if authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() != "bearer" or not token.strip():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authorization 必须使用 Bearer 访问令牌",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            try:
                payload = verify_access_token(token.strip(), current_settings.auth_secret)
            except AuthenticationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=str(exc),
                    headers={"WWW-Authenticate": "Bearer"},
                ) from exc
            user_id = str(payload["sub"])
        elif (
            current_settings.environment in {"development", "test"}
            and current_settings.allow_legacy_user_header
        ):
            user_id = x_user_id or current_settings.default_user_id
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少访问令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if request.app.state.database.get_user_access(user_id) is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在、已停用或未加入组织",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_id

    @app.middleware("http")
    async def require_api_authentication(request: Request, call_next):
        if (
            request.url.path.startswith(app_settings.api_prefix)
            and request.method != "OPTIONS"
        ):
            try:
                request.state.user_id = get_user_id(
                    request,
                    request.headers.get("Authorization"),
                    request.headers.get("X-User-Id"),
                )
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=exc.headers,
                )
        return await call_next(request)

    def get_collector(request: Request) -> CollectionEngine:
        return request.app.state.collector

    def get_processor(request: Request) -> DocumentProcessor:
        return request.app.state.processor

    def get_rag_engine(request: Request) -> RAGEngine:
        return request.app.state.rag_engine

    def get_competitive_agent(request: Request) -> CompetitiveAnalysisAgent:
        return request.app.state.competitive_agent

    DatabaseDependency = Annotated[Database, Depends(get_database)]
    UserDependency = Annotated[str, Depends(get_user_id)]
    CollectorDependency = Annotated[CollectionEngine, Depends(get_collector)]
    ProcessorDependency = Annotated[DocumentProcessor, Depends(get_processor)]
    RAGDependency = Annotated[RAGEngine, Depends(get_rag_engine)]
    CompetitiveAgentDependency = Annotated[
        CompetitiveAnalysisAgent, Depends(get_competitive_agent)
    ]

    def ensure_permission(db: Database, user_id: str, permission: str) -> None:
        if not db.user_has_permission(user_id, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前账号没有执行该操作的权限。",
            )

    def ensure_project_access(
        db: Database,
        user_id: str,
        project_id: str,
        permission: str | None = "reports.view",
        data_classification: str | None = None,
    ) -> None:
        if not db.user_can_access_project(
            user_id,
            project_id,
            permission=permission,
            data_classification=data_classification,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前账号无权访问该项目或数据域",
            )

    def ensure_source_access(
        db: Database,
        user_id: str,
        source_id: str,
        permission: str | None = "reports.view",
        *,
        include_archived: bool = False,
    ) -> sqlite3.Row:
        row = db.get_source(source_id, include_archived=include_archived)
        if row is None:
            raise HTTPException(status_code=404, detail="数据源不存在")
        ensure_project_access(
            db,
            user_id,
            row["project_id"],
            permission,
            row["data_classification"],
        )
        return row

    def allowed_domains(db: Database, user_id: str) -> list[str]:
        access = db.get_user_access(user_id)
        assert access is not None
        return list(access["data_domains"])

    def ensure_run_access(
        db: Database,
        user_id: str,
        run_id: str,
        permission: str | None = "reports.view",
    ) -> sqlite3.Row:
        row = db.get_source_run(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="采集任务不存在")
        ensure_project_access(
            db,
            user_id,
            row["project_id"],
            permission,
            row["source_data_classification"],
        )
        return row

    def ensure_document_access(
        db: Database,
        user_id: str,
        document_id: str,
        permission: str | None = "reports.view",
    ) -> sqlite3.Row:
        row = db.get_collection_document(document_id)
        if row is None:
            raise HTTPException(status_code=404, detail="采集材料不存在")
        ensure_project_access(
            db,
            user_id,
            row["project_id"],
            permission,
            row["source_data_classification"],
        )
        return row

    def ensure_knowledge_access(
        db: Database,
        user_id: str,
        item_id: str,
        permission: str | None = "reports.view",
    ) -> sqlite3.Row:
        row = db.get_knowledge_item(item_id)
        if row is None:
            raise HTTPException(status_code=404, detail="知识条目不存在")
        ensure_project_access(
            db,
            user_id,
            row["project_id"],
            permission,
            row["source_data_classification"],
        )
        return row

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health(db: DatabaseDependency) -> HealthResponse:
        db.ping()
        return HealthResponse(
            status="ok",
            service=app_settings.app_name,
            environment=app_settings.environment,
            database="ok",
        )

    @app.get(
        f"{app_settings.api_prefix}/projects",
        response_model=list[ProjectSummary],
        tags=["projects"],
    )
    def list_projects(
        db: DatabaseDependency, user_id: UserDependency
    ) -> list[ProjectSummary]:
        project_ids = db.accessible_project_ids(user_id)
        return [project_from_row(row) for row in db.list_projects(project_ids)]

    @app.post(
        f"{app_settings.api_prefix}/projects",
        response_model=ProjectSummary,
        status_code=status.HTTP_201_CREATED,
        tags=["projects"],
    )
    def create_project(
        payload: ProjectCreate, db: DatabaseDependency, user_id: UserDependency
    ) -> ProjectSummary:
        ensure_permission(db, user_id, "*")
        return project_from_row(db.create_project(payload, user_id))

    @app.get(
        f"{app_settings.api_prefix}/workbench",
        response_model=WorkbenchResponse,
        tags=["workbench"],
    )
    def workbench(
        db: DatabaseDependency,
        user_id: UserDependency,
        project_id: str | None = Query(default=None),
        range_key: Literal["24h", "7d", "30d"] = Query(
            default="7d", alias="range"
        ),
    ) -> WorkbenchResponse:
        project_ids = db.accessible_project_ids(user_id)
        selected_project_id = project_id or (project_ids[0] if project_ids else None)
        if selected_project_id is None:
            raise HTTPException(status_code=403, detail="当前账号没有可访问的项目")
        ensure_project_access(db, user_id, selected_project_id)
        result = get_workbench(
            db, selected_project_id, range_key, user_id, project_ids
        )
        if result is None:
            raise HTTPException(status_code=404, detail="项目或用户不存在")
        return result

    @app.get(
        f"{app_settings.api_prefix}/sources",
        response_model=SourceListResponse,
        tags=["sources"],
    )
    def list_sources(
        db: DatabaseDependency,
        user_id: UserDependency,
        project_id: str = Query(min_length=1),
        status_filter: Literal["healthy", "warning", "error", "disabled"] | None = Query(
            default=None, alias="status"
        ),
        source_type: Literal[
            "webpage",
            "dynamic_webpage",
            "sitemap",
            "rss",
            "public_api",
            "social_api",
            "public_database",
            "file_upload",
        ]
        | None = Query(default=None),
        q: str | None = Query(default=None, max_length=100),
    ) -> SourceListResponse:
        ensure_project_access(db, user_id, project_id)
        access = db.get_user_access(user_id)
        assert access is not None
        result = get_sources(
            db,
            project_id,
            status_filter,
            source_type,
            q,
            list(access["data_domains"]),
        )
        if result is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return result

    @app.post(
        f"{app_settings.api_prefix}/sources",
        response_model=SourceRecord,
        status_code=status.HTTP_201_CREATED,
        tags=["sources"],
    )
    def create_source(
        payload: SourceCreate, db: DatabaseDependency, user_id: UserDependency
    ) -> SourceRecord:
        ensure_project_access(
            db,
            user_id,
            payload.project_id,
            "sources.manage",
            payload.data_classification,
        )
        try:
            row = db.create_source(payload, user_id)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="同一项目中已存在相同入口的数据源",
            ) from exc
        if row is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return source_from_row(row)

    @app.get(
        f"{app_settings.api_prefix}/sources/{{source_id}}",
        response_model=SourceRecord,
        tags=["sources"],
    )
    def source_detail(
        source_id: str, db: DatabaseDependency, user_id: UserDependency
    ) -> SourceRecord:
        row = ensure_source_access(db, user_id, source_id)
        if row is None:
            raise HTTPException(status_code=404, detail="数据源不存在")
        return source_from_row(row)

    @app.patch(
        f"{app_settings.api_prefix}/sources/{{source_id}}",
        response_model=SourceRecord,
        tags=["sources"],
    )
    def update_source(
        source_id: str,
        payload: SourceUpdate,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> SourceRecord:
        current = ensure_source_access(db, user_id, source_id, "sources.manage")
        if payload.data_classification is not None:
            ensure_project_access(
                db,
                user_id,
                current["project_id"],
                "sources.manage",
                payload.data_classification,
            )
        if current is None:
            raise HTTPException(status_code=404, detail="数据源不存在")
        merged = {
            "project_id": current["project_id"],
            "name": current["name"],
            "source_type": current["source_type"],
            "endpoint": current["endpoint"],
            "subject": current["subject"],
            "access_method": current["access_method"],
            "crawl_strategy": current["crawl_strategy"],
            "regions": json.loads(current["regions_json"]),
            "authorization_basis": current["authorization_basis"],
            "authorization_status": current["authorization_status"],
            "data_classification": current["data_classification"],
            "retention_days": current["retention_days"],
            "schedule_frequency": current["schedule_frequency"],
            "rate_limit_per_minute": current["rate_limit_per_minute"],
            "concurrency_limit": current["concurrency_limit"],
            "task_timeout_seconds": current["task_timeout_seconds"],
            "max_attempts": current["max_attempts"],
            "retry_backoff_seconds": current["retry_backoff_seconds"],
            "priority": current["priority"],
            "credential_ref": current["credential_ref"],
            "credential_expires_at": current["credential_expires_at"],
            "fields_available": json.loads(current["fields_json"]),
            "collection_config": json.loads(current["collection_config_json"] or "{}"),
            "robots_acknowledged": bool(current["robots_acknowledged"]),
            "terms_acknowledged": bool(current["terms_acknowledged"]),
        }
        merged.update(payload.model_dump(exclude_unset=True))
        try:
            SourceCreate.model_validate(merged)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"更新后的数据源配置无效：{exc.errors()[0]['msg']}",
            ) from exc
        try:
            row = db.update_source(source_id, payload, user_id)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="同一项目中已存在相同入口的数据源",
            ) from exc
        assert row is not None
        return source_from_row(row)

    @app.post(
        f"{app_settings.api_prefix}/sources/{{source_id}}/checks",
        response_model=SourceActionResponse,
        tags=["sources"],
    )
    def check_source(
        source_id: str, db: DatabaseDependency, user_id: UserDependency
    ) -> SourceActionResponse:
        ensure_source_access(db, user_id, source_id, "sources.manage")
        row = db.run_source_checks(source_id, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="数据源不存在")
        item = source_from_row(row)
        return SourceActionResponse(
            item=item,
            message="启用前检查已通过" if item.activation_ready else "检查完成，请修正未通过项",
        )

    @app.patch(
        f"{app_settings.api_prefix}/sources/{{source_id}}/status",
        response_model=SourceActionResponse,
        tags=["sources"],
    )
    def update_source_status(
        source_id: str,
        payload: SourceStatusUpdate,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> SourceActionResponse:
        ensure_source_access(db, user_id, source_id, "sources.manage")
        try:
            row = db.set_source_enabled(source_id, payload.enabled, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if row is None:
            raise HTTPException(status_code=404, detail="数据源不存在")
        return SourceActionResponse(
            item=source_from_row(row),
            message="数据源已启用" if payload.enabled else "数据源已停用，不会再发起新采集",
        )

    @app.patch(
        f"{app_settings.api_prefix}/sources/{{source_id}}/schedule",
        response_model=SourceRecord,
        tags=["orchestration"],
    )
    def update_source_schedule(
        source_id: str,
        payload: SourceScheduleUpdate,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> SourceRecord:
        ensure_source_access(db, user_id, source_id, "tasks.manage")
        row = db.update_source_schedule(source_id, payload, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="数据源不存在")
        return source_from_row(row)

    @app.post(
        f"{app_settings.api_prefix}/sources/{{source_id}}/credentials/rotate",
        response_model=SourceActionResponse,
        tags=["sources"],
    )
    def rotate_source_credential(
        source_id: str,
        payload: SourceCredentialRotate,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> SourceActionResponse:
        ensure_source_access(db, user_id, source_id, "sources.manage")
        row = db.rotate_source_credential(
            source_id,
            payload.credential_ref,
            payload.credential_expires_at,
            user_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="数据源不存在")
        return SourceActionResponse(item=source_from_row(row), message="凭据引用已轮换")

    @app.post(
        f"{app_settings.api_prefix}/sources/{{source_id}}/runs",
        response_model=SourceRunSummary,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["sources"],
    )
    def run_source(
        source_id: str,
        background_tasks: BackgroundTasks,
        db: DatabaseDependency,
        user_id: UserDependency,
        collection_engine: CollectorDependency,
    ) -> SourceRunSummary:
        ensure_source_access(db, user_id, source_id, "tasks.manage")
        try:
            row = db.queue_source_run(source_id, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if row is None:
            raise HTTPException(status_code=404, detail="数据源不存在")
        background_tasks.add_task(collection_engine.execute_run, row["id"])
        return source_run_from_row(row, db)

    @app.get(
        f"{app_settings.api_prefix}/orchestration",
        response_model=OrchestrationDashboard,
        tags=["orchestration"],
    )
    def orchestration_dashboard(
        db: DatabaseDependency,
        user_id: UserDependency,
        project_id: str = Query(min_length=1),
    ) -> OrchestrationDashboard:
        ensure_project_access(db, user_id, project_id)
        result = get_orchestration_dashboard(db, project_id)
        if result is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return result

    @app.post(
        f"{app_settings.api_prefix}/orchestration/triggers",
        response_model=SourceRunSummary,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["orchestration"],
    )
    def trigger_orchestration_run(
        payload: OrchestrationTrigger,
        background_tasks: BackgroundTasks,
        db: DatabaseDependency,
        user_id: UserDependency,
        collection_engine: CollectorDependency,
    ) -> SourceRunSummary:
        ensure_source_access(db, user_id, payload.source_id, "tasks.manage")
        try:
            row = db.queue_source_run(
                payload.source_id, user_id, trigger_type=payload.trigger_type
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if row is None:
            raise HTTPException(status_code=404, detail="数据源不存在")
        background_tasks.add_task(collection_engine.execute_run, row["id"])
        return source_run_from_row(row, db)

    @app.post(
        f"{app_settings.api_prefix}/orchestration/runs/retry",
        response_model=OrchestrationActionResult,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["orchestration"],
    )
    def bulk_retry_orchestration_runs(
        payload: OrchestrationBulkRetry,
        background_tasks: BackgroundTasks,
        db: DatabaseDependency,
        user_id: UserDependency,
        collection_engine: CollectorDependency,
    ) -> OrchestrationActionResult:
        for run_id in payload.run_ids:
            ensure_run_access(db, user_id, run_id, "tasks.manage")
        queued = []
        skipped: dict[str, str] = {}
        for run_id in payload.run_ids:
            try:
                row = db.retry_source_run(run_id, user_id)
            except ValueError as exc:
                skipped[run_id] = str(exc)
                continue
            if row is None:
                skipped[run_id] = "采集任务不存在"
                continue
            queued.append(source_run_from_row(row, db))
            background_tasks.add_task(collection_engine.execute_run, row["id"])
        return OrchestrationActionResult(queued=queued, skipped=skipped)

    @app.post(
        f"{app_settings.api_prefix}/orchestration/recover",
        response_model=OrchestrationActionResult,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["orchestration"],
    )
    def recover_orchestration_runs(
        payload: OrchestrationRecover,
        background_tasks: BackgroundTasks,
        db: DatabaseDependency,
        user_id: UserDependency,
        collection_engine: CollectorDependency,
    ) -> OrchestrationActionResult:
        ensure_project_access(db, user_id, payload.project_id, "tasks.manage")
        if db.get_project(payload.project_id) is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        run_ids = payload.run_ids or db.latest_recoverable_run_ids(payload.project_id)
        queued = []
        skipped: dict[str, str] = {}
        for run_id in run_ids:
            try:
                row = db.recover_source_run(run_id, user_id)
            except ValueError as exc:
                skipped[run_id] = str(exc)
                continue
            if row is None:
                skipped[run_id] = "采集任务不存在"
                continue
            queued.append(source_run_from_row(row, db))
            background_tasks.add_task(collection_engine.execute_run, row["id"])
        return OrchestrationActionResult(queued=queued, skipped=skipped)

    @app.get(
        f"{app_settings.api_prefix}/collection/runs",
        response_model=SourceRunListResponse,
        tags=["collection"],
    )
    def list_collection_runs(
        db: DatabaseDependency,
        user_id: UserDependency,
        project_id: str = Query(min_length=1),
        source_id: str | None = Query(default=None),
        status_filter: Literal[
            "queued",
            "running",
            "succeeded",
            "partial",
            "failed",
            "cancelled",
            "manual_review",
        ]
        | None = Query(default=None, alias="status"),
    ) -> SourceRunListResponse:
        ensure_project_access(db, user_id, project_id)
        if source_id is not None:
            ensure_source_access(db, user_id, source_id)
        result = get_source_runs(
            db, project_id, source_id, status_filter, allowed_domains(db, user_id)
        )
        if result is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return result

    @app.get(
        f"{app_settings.api_prefix}/collection/runs/{{run_id}}",
        response_model=SourceRunSummary,
        tags=["collection"],
    )
    def collection_run_detail(
        run_id: str, db: DatabaseDependency, user_id: UserDependency
    ) -> SourceRunSummary:
        row = ensure_run_access(db, user_id, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="采集任务不存在")
        return source_run_from_row(row, db)

    @app.post(
        f"{app_settings.api_prefix}/collection/runs/{{run_id}}/retry",
        response_model=SourceRunSummary,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["collection"],
    )
    def retry_collection_run(
        run_id: str,
        background_tasks: BackgroundTasks,
        db: DatabaseDependency,
        user_id: UserDependency,
        collection_engine: CollectorDependency,
    ) -> SourceRunSummary:
        ensure_run_access(db, user_id, run_id, "tasks.manage")
        try:
            row = db.retry_source_run(run_id, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if row is None:
            raise HTTPException(status_code=404, detail="采集任务不存在")
        background_tasks.add_task(collection_engine.execute_run, row["id"])
        return source_run_from_row(row, db)

    @app.post(
        f"{app_settings.api_prefix}/collection/runs/{{run_id}}/cancel",
        response_model=SourceRunSummary,
        tags=["collection"],
    )
    def cancel_collection_run(
        run_id: str, db: DatabaseDependency, user_id: UserDependency
    ) -> SourceRunSummary:
        ensure_run_access(db, user_id, run_id, "tasks.manage")
        try:
            row = db.cancel_source_run(run_id, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if row is None:
            raise HTTPException(status_code=404, detail="采集任务不存在")
        return source_run_from_row(row, db)

    @app.get(
        f"{app_settings.api_prefix}/collection/documents",
        response_model=CollectionDocumentListResponse,
        tags=["collection"],
    )
    def list_collection_documents(
        db: DatabaseDependency,
        user_id: UserDependency,
        project_id: str = Query(min_length=1),
        source_id: str | None = Query(default=None),
        latest_only: bool = Query(default=True),
        q: str | None = Query(default=None, max_length=100),
    ) -> CollectionDocumentListResponse:
        ensure_project_access(db, user_id, project_id)
        if source_id is not None:
            ensure_source_access(db, user_id, source_id)
        result = get_collection_documents(
            db,
            project_id,
            source_id=source_id,
            latest_only=latest_only,
            query=q,
            allowed_domains=allowed_domains(db, user_id),
        )
        if result is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return result

    @app.get(
        f"{app_settings.api_prefix}/collection/documents/{{document_id}}",
        response_model=CollectionDocumentDetail,
        tags=["collection"],
    )
    def collection_document_detail(
        document_id: str, db: DatabaseDependency, user_id: UserDependency
    ) -> CollectionDocumentDetail:
        row = ensure_document_access(db, user_id, document_id)
        if row is None:
            raise HTTPException(status_code=404, detail="采集材料不存在")
        return collection_document_detail_from_row(row)

    @app.get(
        f"{app_settings.api_prefix}/collection/documents/{{document_id}}/raw",
        response_class=Response,
        tags=["collection"],
    )
    def collection_document_raw(
        document_id: str, db: DatabaseDependency, user_id: UserDependency
    ) -> Response:
        row = ensure_document_access(db, user_id, document_id)
        if row is None:
            raise HTTPException(status_code=404, detail="采集材料不存在")
        return Response(
            content=bytes(row["raw_content"]),
            media_type=row["content_type"].split(";", 1)[0],
            headers={
                "Content-Disposition": f'attachment; filename="{document_id}.raw"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get(
        f"{app_settings.api_prefix}/processing",
        response_model=ProcessingOverview,
        tags=["processing"],
    )
    def processing_overview(
        db: DatabaseDependency,
        user_id: UserDependency,
        project_id: str = Query(min_length=1),
        status_filter: Literal[
            "pending", "processing", "completed", "review_required", "failed"
        ]
        | None = Query(default=None, alias="status"),
        q: str | None = Query(default=None, max_length=100),
    ) -> ProcessingOverview:
        if db.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        ensure_project_access(db, user_id, project_id)
        domains = allowed_domains(db, user_id)
        all_rows = db.list_processing_documents(
            project_id, limit=1000, allowed_domains=domains
        )
        rows = db.list_processing_documents(
            project_id, status_filter, q, allowed_domains=domains
        )
        all_items = [processing_summary_from_row(row) for row in all_rows]
        items = [ProcessingDocumentSummary.model_validate(processing_summary_from_row(row)) for row in rows]
        return ProcessingOverview(
            project_id=project_id,
            generated_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            summary=ProcessingOverviewSummary(
                total=len(all_items),
                processed=sum(item["status"] in {"completed", "review_required"} for item in all_items),
                pending=sum(item["status"] == "pending" for item in all_items),
                review_required=sum(item["status"] == "review_required" for item in all_items),
                failed=sum(item["status"] == "failed" for item in all_items),
                duplicates=sum(item["duplicate"]["type"] != "none" for item in all_items),
                entities=sum(int(item["entity_count"]) for item in all_items),
                events=sum(int(item["event_count"]) for item in all_items),
                ocr_completed=sum(item["ocr_status"] == "completed" for item in all_items),
            ),
            items=items,
        )

    @app.get(
        f"{app_settings.api_prefix}/processing/documents/{{document_id}}",
        response_model=ProcessingDocumentDetail,
        tags=["processing"],
    )
    def processing_document_detail(
        document_id: str, db: DatabaseDependency, user_id: UserDependency
    ) -> ProcessingDocumentDetail:
        ensure_document_access(db, user_id, document_id)
        row = db.get_processing_document(document_id)
        if row is None:
            raise HTTPException(status_code=404, detail="采集材料不存在")
        return ProcessingDocumentDetail.model_validate(processing_detail_from_row(row))

    @app.post(
        f"{app_settings.api_prefix}/processing/jobs",
        response_model=ProcessingBatchResponse,
        tags=["processing"],
    )
    def run_processing_batch(
        payload: ProcessingBatchRequest,
        db: DatabaseDependency,
        user_id: UserDependency,
        document_processor: ProcessorDependency,
    ) -> ProcessingBatchResponse:
        ensure_project_access(db, user_id, payload.project_id, "tasks.manage")
        if db.get_project(payload.project_id) is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        rows = document_processor.process_project(
            payload.project_id,
            payload.document_ids,
            payload.options.model_dump(),
        )
        items = [
            ProcessingDocumentSummary.model_validate(processing_summary_from_row(row))
            for row in rows
        ]
        return ProcessingBatchResponse(
            requested=len(payload.document_ids) if payload.document_ids else len(items),
            completed=sum(item.status == "completed" for item in items),
            review_required=sum(item.status == "review_required" for item in items),
            failed=sum(item.status == "failed" for item in items),
            items=items,
        )

    @app.post(
        f"{app_settings.api_prefix}/processing/documents/{{document_id}}/run",
        response_model=ProcessingDocumentDetail,
        tags=["processing"],
    )
    def run_processing_document(
        document_id: str,
        payload: ProcessingOptions,
        db: DatabaseDependency,
        user_id: UserDependency,
        document_processor: ProcessorDependency,
    ) -> ProcessingDocumentDetail:
        row = ensure_document_access(db, user_id, document_id, "tasks.manage")
        if row is None:
            raise HTTPException(status_code=404, detail="采集材料不存在")
        processed = document_processor.process_document(document_id, payload.model_dump())
        assert processed is not None
        return ProcessingDocumentDetail.model_validate(
            processing_detail_from_row(processed)
        )

    @app.get(
        f"{app_settings.api_prefix}/knowledge",
        response_model=KnowledgeOverview,
        tags=["knowledge"],
    )
    def knowledge_overview(
        db: DatabaseDependency,
        user_id: UserDependency,
        project_id: str = Query(min_length=1),
        q: str | None = Query(default=None, max_length=100),
        item_type: Literal["fact", "entity", "event", "insight"]
        | None = Query(default=None),
        review_status: Literal["verified", "review_required", "conflict"]
        | None = Query(default=None),
        source_id: str | None = Query(default=None),
        collection_id: str | None = Query(default=None),
    ) -> KnowledgeOverview:
        ensure_project_access(db, user_id, project_id)
        if source_id is not None:
            ensure_source_access(db, user_id, source_id)
        result = get_knowledge_overview(
            db,
            project_id,
            query=q,
            item_type=item_type,
            review_status=review_status,
            source_id=source_id,
            collection_id=collection_id,
            allowed_domains=allowed_domains(db, user_id),
        )
        if result is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return result

    @app.get(
        f"{app_settings.api_prefix}/knowledge/items/{{item_id}}",
        response_model=KnowledgeItemDetail,
        tags=["knowledge"],
    )
    def knowledge_item_detail(
        item_id: str, db: DatabaseDependency, user_id: UserDependency
    ) -> KnowledgeItemDetail:
        ensure_knowledge_access(db, user_id, item_id)
        result = get_knowledge_item_detail(db, item_id)
        if result is None:
            raise HTTPException(status_code=404, detail="知识条目不存在")
        return result

    @app.patch(
        f"{app_settings.api_prefix}/knowledge/items/{{item_id}}/review",
        response_model=KnowledgeItemDetail,
        tags=["knowledge"],
    )
    def review_knowledge_item(
        item_id: str,
        payload: KnowledgeReviewUpdate,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> KnowledgeItemDetail:
        ensure_knowledge_access(db, user_id, item_id, "insights.review")
        row = db.update_knowledge_review(
            item_id, payload.review_status, payload.note, user_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="知识条目不存在")
        result = get_knowledge_item_detail(db, item_id)
        assert result is not None
        return result

    @app.post(
        f"{app_settings.api_prefix}/knowledge/collections",
        response_model=KnowledgeCollectionSummary,
        status_code=status.HTTP_201_CREATED,
        tags=["knowledge"],
    )
    def create_knowledge_collection(
        payload: KnowledgeCollectionCreate,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> KnowledgeCollectionSummary:
        ensure_project_access(
            db, user_id, payload.project_id, "insights.review"
        )
        try:
            row = db.create_knowledge_collection(
                payload.project_id,
                payload.name,
                payload.description,
                payload.color,
                user_id,
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="同名专题集合已存在") from exc
        if row is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return knowledge_collection_from_row(row)

    @app.post(
        f"{app_settings.api_prefix}/knowledge/collections/{{collection_id}}/items/{{item_id}}",
        response_model=KnowledgeCollectionSummary,
        tags=["knowledge"],
    )
    def add_knowledge_collection_item(
        collection_id: str,
        item_id: str,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> KnowledgeCollectionSummary:
        item = ensure_knowledge_access(db, user_id, item_id, "insights.review")
        collection = db.get_knowledge_collection(collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="专题集合不存在")
        ensure_project_access(
            db, user_id, collection["project_id"], "insights.review"
        )
        if collection["project_id"] != item["project_id"]:
            raise HTTPException(status_code=409, detail="专题集合与知识条目不属于同一项目")
        try:
            row = db.add_knowledge_collection_item(collection_id, item_id, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if row is None:
            raise HTTPException(status_code=404, detail="专题集合或知识条目不存在")
        return knowledge_collection_from_row(row)

    @app.delete(
        f"{app_settings.api_prefix}/knowledge/collections/{{collection_id}}/items/{{item_id}}",
        response_model=KnowledgeCollectionSummary,
        tags=["knowledge"],
    )
    def remove_knowledge_collection_item(
        collection_id: str,
        item_id: str,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> KnowledgeCollectionSummary:
        ensure_knowledge_access(db, user_id, item_id, "insights.review")
        collection = db.get_knowledge_collection(collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="专题集合不存在")
        ensure_project_access(
            db, user_id, collection["project_id"], "insights.review"
        )
        row = db.remove_knowledge_collection_item(collection_id, item_id, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="专题集合不存在")
        return knowledge_collection_from_row(row)

    @app.post(
        f"{app_settings.api_prefix}/collection/files",
        response_model=FileUploadResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["collection"],
    )
    async def upload_collection_file(
        background_tasks: BackgroundTasks,
        db: DatabaseDependency,
        user_id: UserDependency,
        collection_engine: CollectorDependency,
        file: UploadFile = File(...),
        project_id: str = Form(...),
        name: str = Form(...),
        subject: str = Form(...),
        authorization_basis: str = Form(...),
        retention_days: int = Form(default=365),
    ) -> FileUploadResponse:
        ensure_project_access(
            db, user_id, project_id, "sources.manage", "internal"
        )
        if db.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        filename = Path(file.filename or "upload.bin").name
        safe_filename = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]", "_", filename)[:160]
        content = await file.read(app_settings.collector_max_response_bytes + 1)
        if len(content) > app_settings.collector_max_response_bytes:
            raise HTTPException(status_code=413, detail="文件超过允许的最大体积")
        upload_token = uuid4().hex
        payload = SourceCreate(
            project_id=project_id,
            name=name.strip(),
            source_type="file_upload",
            endpoint=f"upload://{upload_token}/{safe_filename}",
            subject=subject.strip(),
            access_method="upload",
            crawl_strategy="文件解析与内容指纹",
            regions=["global"],
            authorization_basis=authorization_basis.strip(),
            authorization_status="approved",
            data_classification="internal",
            retention_days=retention_days,
            schedule_frequency="manual",
            rate_limit_per_minute=1,
            fields_available=["title", "body", "metadata"],
            collection_config={"max_items": 1, "timeout_seconds": 20},
            robots_acknowledged=True,
            terms_acknowledged=True,
        )
        source = db.create_source(payload, user_id)
        assert source is not None
        upload_dir = db.path.parent / "uploads" / source["id"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        storage_path = upload_dir / safe_filename
        storage_path.write_bytes(content)
        db.attach_source_file(
            source["id"],
            storage_path,
            file.content_type or "application/octet-stream",
            len(content),
            user_id,
        )
        db.run_source_checks(source["id"], user_id)
        enabled_source = db.set_source_enabled(source["id"], True, user_id)
        run = db.queue_source_run(source["id"], user_id, trigger_type="upload")
        assert enabled_source is not None and run is not None
        background_tasks.add_task(collection_engine.execute_run, run["id"])
        return FileUploadResponse(
            source=source_from_row(enabled_source), run=source_run_from_row(run, db)
        )

    @app.delete(
        f"{app_settings.api_prefix}/sources/{{source_id}}",
        response_model=SourceArchiveResponse,
        tags=["sources"],
    )
    def archive_source(
        source_id: str, db: DatabaseDependency, user_id: UserDependency
    ) -> SourceArchiveResponse:
        ensure_source_access(db, user_id, source_id, "sources.manage")
        try:
            archived = db.archive_source(source_id, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if archived is None:
            raise HTTPException(status_code=404, detail="数据源不存在")
        row = db.get_source(source_id, include_archived=True)
        assert row is not None and row["archived_at"]
        return SourceArchiveResponse(
            id=source_id, archived=True, archived_at=row["archived_at"]
        )

    @app.delete(
        f"{app_settings.api_prefix}/sources/{{source_id}}/purge",
        response_model=SourcePurgeResponse,
        tags=["sources"],
    )
    def purge_source(
        source_id: str,
        payload: SourcePurgeRequest,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> SourcePurgeResponse:
        ensure_permission(db, user_id, "*")
        ensure_source_access(db, user_id, source_id, "*", include_archived=True)
        expected_confirmation = f"PURGE:{source_id}"
        if payload.confirmation != expected_confirmation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"永久清除需要精确确认值：{expected_confirmation}",
            )

        upload_root = (db.path.parent / "uploads").resolve()
        source_dir = (upload_root / source_id).resolve()
        if source_dir.parent != upload_root:
            raise HTTPException(status_code=400, detail="无效的数据源存储路径")
        quarantine_root = (db.path.parent / ".purge-quarantine").resolve()
        quarantined: Path | None = None
        if source_dir.exists():
            quarantine_root.mkdir(parents=True, exist_ok=True)
            quarantined = quarantine_root / f"{source_id}-{uuid4().hex}"
            source_dir.replace(quarantined)
        try:
            counts = db.purge_source(source_id, user_id)
        except Exception:
            if quarantined is not None and quarantined.exists():
                quarantined.replace(source_dir)
            raise
        if counts is None:
            if quarantined is not None and quarantined.exists():
                quarantined.replace(source_dir)
            raise HTTPException(status_code=404, detail="数据源不存在")
        if quarantined is not None and quarantined.exists():
            shutil.rmtree(quarantined)
        return SourcePurgeResponse(
            id=source_id,
            purged=True,
            removed_runs=counts["runs"],
            removed_documents=counts["documents"],
            detached_knowledge_items=counts["knowledge_items"],
        )

    @app.get(
        f"{app_settings.api_prefix}/insights/{{insight_id}}",
        response_model=InsightDetail,
        tags=["insights"],
    )
    def insight_detail(
        insight_id: int, db: DatabaseDependency, user_id: UserDependency
    ) -> InsightDetail:
        insight = db.get_insight(insight_id)
        if insight is None:
            raise HTTPException(status_code=404, detail="洞察不存在")
        ensure_project_access(db, user_id, insight["project_id"])
        result = get_insight_detail(db, insight_id)
        if result is None:
            raise HTTPException(status_code=404, detail="洞察不存在")
        return result

    @app.post(
        f"{app_settings.api_prefix}/reviews/{{review_id}}/claim",
        response_model=ReviewClaimResponse,
        tags=["reviews"],
    )
    def claim_review(
        review_id: int, db: DatabaseDependency, user_id: UserDependency
    ) -> ReviewClaimResponse:
        review = db.get_review(review_id)
        if review is None:
            raise HTTPException(status_code=404, detail="复核项不存在")
        ensure_project_access(
            db, user_id, review["project_id"], "insights.review"
        )
        row = db.claim_review(review_id, user_id)
        if row is None:
            raise HTTPException(status_code=409, detail="复核项不存在或已被领取")
        return ReviewClaimResponse(
            item=review_from_row(row),
            pending_count=db.pending_review_count(row["project_id"]),
        )

    @app.get(
        f"{app_settings.api_prefix}/reports",
        response_model=ReportingDashboard,
        tags=["reports"],
    )
    def reporting_dashboard(
        project_id: str,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> ReportingDashboard:
        ensure_project_access(db, user_id, project_id, "reports.view")
        result = db.get_reporting_dashboard(project_id)
        if result is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return ReportingDashboard.model_validate(result)

    @app.get(
        f"{app_settings.api_prefix}/reports/{{report_id}}",
        response_model=ReportRecord,
        tags=["reports"],
    )
    def report_detail(
        report_id: str,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> ReportRecord:
        ensure_permission(db, user_id, "reports.view")
        result = db.get_report_record(report_id)
        if result is None:
            raise HTTPException(status_code=404, detail="报告不存在")
        ensure_project_access(
            db, user_id, str(result["project_id"]), "reports.view"
        )
        return ReportRecord.model_validate(result)

    @app.post(
        f"{app_settings.api_prefix}/reports/generate",
        response_model=ReportSummary,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["reports"],
    )
    def generate_report(
        payload: ReportGenerate,
        background_tasks: BackgroundTasks,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> ReportSummary:
        ensure_project_access(db, user_id, payload.project_id, "reports.manage")
        row = db.generate_report(
            payload.project_id,
            payload.template,
            user_id,
            payload.model_dump(),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        background_tasks.add_task(db.complete_report, row["id"])
        return report_from_row(row)

    @app.post(
        f"{app_settings.api_prefix}/reports/{{report_id}}/approval",
        response_model=ReportRecord,
        tags=["reports"],
    )
    def approve_report(
        report_id: str,
        payload: ReportApproval,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> ReportRecord:
        ensure_permission(db, user_id, "reports.manage")
        current = db.get_report_record(report_id)
        if current is None:
            raise HTTPException(status_code=404, detail="报告不存在")
        ensure_project_access(
            db, user_id, str(current["project_id"]), "reports.manage"
        )
        result = db.approve_report(report_id, payload.decision, payload.note, user_id)
        if result is None:
            raise HTTPException(status_code=404, detail="报告不存在")
        return ReportRecord.model_validate(result)

    @app.get(
        f"{app_settings.api_prefix}/reports/{{report_id}}/export",
        tags=["reports"],
    )
    def export_report(
        report_id: str,
        db: DatabaseDependency,
        user_id: UserDependency,
        format: Literal["docx", "pdf"] = Query("pdf"),
    ) -> Response:
        ensure_permission(db, user_id, "reports.export")
        result = db.get_report_record(report_id)
        if result is None:
            raise HTTPException(status_code=404, detail="报告不存在")
        ensure_project_access(
            db, user_id, str(result["project_id"]), "reports.export"
        )
        body = build_docx(result) if format == "docx" else build_pdf(result)
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if format == "docx"
            else "application/pdf"
        )
        return Response(
            content=body,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{report_id}.{format}"'},
        )

    @app.patch(
        f"{app_settings.api_prefix}/report-subscriptions/{{subscription_id}}",
        response_model=ReportSubscriptionRecord,
        tags=["reports"],
    )
    def update_report_subscription(
        subscription_id: str,
        payload: ReportSubscriptionUpdate,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> ReportSubscriptionRecord:
        ensure_permission(db, user_id, "reports.manage")
        subscription_project_id = db.get_resource_project_id(
            "report_subscription", subscription_id
        )
        if subscription_project_id is None:
            raise HTTPException(status_code=404, detail="订阅不存在")
        ensure_project_access(
            db, user_id, subscription_project_id, "reports.manage"
        )
        result = db.set_subscription_enabled(subscription_id, payload.enabled, user_id)
        if result is None:
            raise HTTPException(status_code=404, detail="订阅不存在")
        return ReportSubscriptionRecord.model_validate(result)

    @app.post(
        f"{app_settings.api_prefix}/alert-rules",
        response_model=AlertRuleRecord,
        status_code=status.HTTP_201_CREATED,
        tags=["alerts"],
    )
    def create_alert_rule(
        payload: AlertRuleCreate,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> AlertRuleRecord:
        ensure_project_access(
            db, user_id, payload.project_id, "reports.manage"
        )
        result = db.create_alert_rule(payload.model_dump(), user_id)
        if result is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return AlertRuleRecord.model_validate(result)

    @app.patch(
        f"{app_settings.api_prefix}/alert-rules/{{rule_id}}",
        response_model=AlertRuleRecord,
        tags=["alerts"],
    )
    def update_alert_rule(
        rule_id: str,
        payload: AlertRuleUpdate,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> AlertRuleRecord:
        ensure_permission(db, user_id, "reports.manage")
        rule_project_id = db.get_resource_project_id("alert_rule", rule_id)
        if rule_project_id is None:
            raise HTTPException(status_code=404, detail="预警规则不存在")
        ensure_project_access(db, user_id, rule_project_id, "reports.manage")
        result = db.update_alert_rule(
            rule_id, payload.model_dump(exclude_unset=True), user_id
        )
        if result is None:
            raise HTTPException(status_code=404, detail="预警规则不存在")
        return AlertRuleRecord.model_validate(result)

    @app.post(
        f"{app_settings.api_prefix}/alerts/{{alert_id}}/actions",
        response_model=AlertRecord,
        tags=["alerts"],
    )
    def act_on_alert(
        alert_id: str,
        payload: AlertAction,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> AlertRecord:
        ensure_permission(db, user_id, "reports.manage")
        alert_project_id = db.get_resource_project_id("alert", alert_id)
        if alert_project_id is None:
            raise HTTPException(status_code=404, detail="预警不存在")
        ensure_project_access(db, user_id, alert_project_id, "reports.manage")
        result = db.act_on_alert(alert_id, payload.action, payload.note, user_id)
        if result is None:
            raise HTTPException(status_code=404, detail="预警不存在")
        return AlertRecord.model_validate(result)

    @app.get(
        f"{app_settings.api_prefix}/admin",
        response_model=AdminDashboard,
        tags=["admin"],
    )
    def admin_dashboard(
        db: DatabaseDependency, user_id: UserDependency
    ) -> AdminDashboard:
        ensure_permission(db, user_id, "admin.view")
        result = db.get_admin_dashboard()
        if result is None:
            raise HTTPException(status_code=404, detail="组织配置不存在")
        return AdminDashboard.model_validate(result)

    @app.patch(
        f"{app_settings.api_prefix}/admin/users/{{target_user_id}}/access",
        response_model=AdminUserRecord,
        tags=["admin"],
    )
    def update_admin_user_access(
        target_user_id: str,
        payload: AdminUserAccessUpdate,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> AdminUserRecord:
        ensure_permission(db, user_id, "*")
        try:
            result = db.update_user_access(
                target_user_id, payload.model_dump(exclude_unset=True), user_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="成员不存在")
        return AdminUserRecord.model_validate(result)

    @app.patch(
        f"{app_settings.api_prefix}/admin/models/{{model_id}}",
        response_model=ModelConfigRecord,
        tags=["admin"],
    )
    def update_admin_model(
        model_id: str,
        payload: ModelConfigUpdate,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> ModelConfigRecord:
        ensure_permission(db, user_id, "*")
        result = db.update_model_config(
            model_id, payload.model_dump(exclude_unset=True), user_id
        )
        if result is None:
            raise HTTPException(status_code=404, detail="模型配置不存在")
        return ModelConfigRecord.model_validate(result)

    @app.patch(
        f"{app_settings.api_prefix}/admin/policies/{{policy_id}}",
        response_model=SecurityPolicyRecord,
        tags=["admin"],
    )
    def update_admin_policy(
        policy_id: str,
        payload: SecurityPolicyUpdate,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> SecurityPolicyRecord:
        ensure_permission(db, user_id, "*")
        result = db.update_security_policy(
            policy_id, payload.model_dump(exclude_unset=True), user_id
        )
        if result is None:
            raise HTTPException(status_code=404, detail="安全策略不存在")
        return SecurityPolicyRecord.model_validate(result)

    @app.post(
        f"{app_settings.api_prefix}/admin/incidents/{{incident_id}}/actions",
        response_model=IncidentRecord,
        tags=["operations"],
    )
    def act_on_incident(
        incident_id: str,
        payload: IncidentAction,
        db: DatabaseDependency,
        user_id: UserDependency,
    ) -> IncidentRecord:
        ensure_permission(db, user_id, "*")
        result = db.act_on_incident(incident_id, payload.action, payload.note, user_id)
        if result is None:
            raise HTTPException(status_code=404, detail="事故不存在")
        return IncidentRecord.model_validate(result)

    @app.post(
        f"{app_settings.api_prefix}/admin/backups",
        response_model=BackupActionResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["operations"],
    )
    def run_backup(
        db: DatabaseDependency, user_id: UserDependency
    ) -> BackupActionResponse:
        ensure_permission(db, user_id, "*")
        backup = db.run_backup(user_id)
        return BackupActionResponse(
            backup=backup,
            message=(
                "全量备份与完整性校验已完成。"
                if backup["status"] == "succeeded"
                else "备份失败，请查看审计记录。"
            ),
        )

    @app.get(
        f"{app_settings.api_prefix}/search",
        response_model=SearchResponse,
        tags=["search"],
    )
    def search(
        db: DatabaseDependency,
        user_id: UserDependency,
        q: str = Query(min_length=1, max_length=100),
        project_id: str | None = Query(default=None),
    ) -> SearchResponse:
        project_ids = db.accessible_project_ids(user_id)
        if project_id is not None:
            ensure_project_access(db, user_id, project_id)
            project_ids = [project_id]
        access = db.get_user_access(user_id)
        assert access is not None
        items = [
            SearchResult(**item)
            for item in db.search(
                q.strip(), project_ids, list(access["data_domains"])
            )
        ]
        return SearchResponse(query=q, total=len(items), items=items)

    @app.post(
        f"{app_settings.api_prefix}/rag/query",
        response_model=RAGResponse,
        tags=["rag"],
    )
    def rag_query(
        payload: RAGQueryRequest,
        db: DatabaseDependency,
        user_id: UserDependency,
        engine: RAGDependency,
    ) -> RAGResponse:
        ensure_project_access(db, user_id, payload.project_id, "reports.view")
        if db.get_project(payload.project_id) is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return engine.answer(payload, user_id)

    @app.get(
        f"{app_settings.api_prefix}/competitive-analysis",
        response_model=CompetitiveAnalysisOverview,
        tags=["competitive-analysis"],
    )
    def competitive_analysis_overview(
        db: DatabaseDependency,
        user_id: UserDependency,
        agent: CompetitiveAgentDependency,
        project_id: str = Query(min_length=1),
    ) -> CompetitiveAnalysisOverview:
        ensure_project_access(db, user_id, project_id, "reports.view")
        if db.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return agent.overview(project_id)

    @app.post(
        f"{app_settings.api_prefix}/competitive-analysis/runs",
        response_model=CompetitiveAnalysisResult,
        status_code=status.HTTP_201_CREATED,
        tags=["competitive-analysis"],
    )
    def run_competitive_analysis(
        payload: CompetitiveAnalysisRequest,
        db: DatabaseDependency,
        user_id: UserDependency,
        agent: CompetitiveAgentDependency,
    ) -> CompetitiveAnalysisResult:
        ensure_project_access(
            db, user_id, payload.project_id, "reports.manage"
        )
        if db.get_project(payload.project_id) is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        known_competitors = set(db.list_competitor_subjects(payload.project_id))
        unknown = [item for item in payload.competitors if item not in known_competitors]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"以下竞品尚无可用知识：{', '.join(unknown)}",
            )
        return agent.run(payload, user_id)

    @app.get(
        f"{app_settings.api_prefix}/competitive-analysis/runs/{{run_id}}",
        response_model=CompetitiveAnalysisResult,
        tags=["competitive-analysis"],
    )
    def competitive_analysis_detail(
        run_id: str,
        db: DatabaseDependency,
        user_id: UserDependency,
        agent: CompetitiveAgentDependency,
    ) -> CompetitiveAnalysisResult:
        project_id = db.get_resource_project_id("competitive_analysis", run_id)
        if project_id is None:
            raise HTTPException(status_code=404, detail="竞品分析任务不存在")
        ensure_project_access(db, user_id, project_id, "reports.view")
        result = agent.get(run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="竞品分析任务不存在")
        return result

    return app


app = create_app()
