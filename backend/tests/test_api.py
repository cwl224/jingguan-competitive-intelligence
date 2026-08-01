from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sqlite3
import threading

from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.config import Settings
from app.database import Database, SCHEMA
from app.main import create_app


def make_client(tmp_path: Path, *, allow_private_networks: bool = False) -> TestClient:
    settings = Settings(
        environment="test",
        debug=True,
        database_path=tmp_path / "test.db",
        cors_origins=("http://localhost:3000",),
        collector_allow_private_networks=allow_private_networks,
        scheduler_enabled=False,
    )
    return TestClient(create_app(settings))


@contextmanager
def fixture_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            payloads = {
                "/robots.txt": ("text/plain", b"User-agent: *\nAllow: /\n"),
                "/page": (
                    "text/html; charset=utf-8",
                    """<html lang="zh-CN"><head><title>静态标题</title></head>
                    <body><nav>导航</nav><main><h1>产品更新</h1><p>新增企业审计功能。</p></main></body></html>""".encode(),
                ),
                "/feed": (
                    "application/rss+xml",
                    b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Updates</title>
                    <item><title>RSS update</title><link>https://example.com/rss-item</link>
                    <description>New RSS capability</description><pubDate>Fri, 31 Jul 2026 10:00:00 GMT</pubDate></item>
                    </channel></rss>""",
                ),
                "/api": (
                    "application/json",
                    b'{"data":{"items":[{"name":"API update","description":"New API capability","url":"https://example.com/api-item","published_at":"2026-07-31T10:00:00Z"}]}}',
                ),
            }
            if self.path not in payloads:
                self.send_response(404)
                self.end_headers()
                return
            content_type, body = payloads[self.path]
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_health_and_workbench_contract(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["database"] == "ok"

        response = client.get("/api/v1/workbench", params={"range": "7d"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["project"]["id"] == "prj_ai_agent"
        assert payload["metrics"][0]["key"] == "coverage"
        assert len(payload["trend"]["labels"]) == len(payload["trend"]["events"])
        assert payload["review_queue"]["total"] == 7


def test_insight_detail_has_traceable_evidence(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        dashboard = client.get("/api/v1/workbench").json()
        insight_id = dashboard["insights"][0]["id"]
        response = client.get(f"/api/v1/insights/{insight_id}")
        assert response.status_code == 200
        detail = response.json()
        assert detail["evidence"]
        assert detail["evidence"][0]["source_url"].startswith("https://")
        assert detail["recommendation"]


def test_knowledge_library_preserves_traceability_review_and_collections(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        response = client.get(
            "/api/v1/knowledge", params={"project_id": "prj_ai_agent"}
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["summary"]["knowledge_items"] == 7
        assert payload["summary"]["evidence_coverage"] == 100
        assert payload["summary"]["conflicts"] == 1
        assert payload["storage"]["raw_documents"] == 0
        assert payload["type_counts"]["fact"] >= 3
        assert len(payload["collections"]) == 3

        item = payload["items"][0]
        detail = client.get(f"/api/v1/knowledge/items/{item['id']}")
        assert detail.status_code == 200, detail.text
        detail_payload = detail.json()
        assert detail_payload["source"]["authorization_status"] == "approved"
        assert detail_payload["evidence"]["excerpt"]
        assert detail_payload["revisions"][0]["version"] == 1

        reviewed = client.patch(
            f"/api/v1/knowledge/items/{item['id']}/review",
            json={"review_status": "verified", "note": "已核对来源与时间"},
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["review_status"] == "verified"
        assert reviewed.json()["revisions"][0]["version"] == 2

        created = client.post(
            "/api/v1/knowledge/collections",
            json={
                "project_id": "prj_ai_agent",
                "name": "本周高影响变化",
                "description": "用于周报选材",
                "color": "#4F6B5A",
            },
        )
        assert created.status_code == 201, created.text
        collection_id = created.json()["id"]

        added = client.post(
            f"/api/v1/knowledge/collections/{collection_id}/items/{item['id']}"
        )
        assert added.status_code == 200, added.text
        assert added.json()["item_count"] == 1

        filtered = client.get(
            "/api/v1/knowledge",
            params={
                "project_id": "prj_ai_agent",
                "collection_id": collection_id,
            },
        )
        assert [entry["id"] for entry in filtered.json()["items"]] == [item["id"]]

        removed = client.delete(
            f"/api/v1/knowledge/collections/{collection_id}/items/{item['id']}"
        )
        assert removed.status_code == 200, removed.text
        assert removed.json()["item_count"] == 0


def test_create_project_persists_and_has_empty_dashboard(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/projects",
            json={"name": "智能办公软件追踪", "template": "daily", "regions": ["cn"]},
        )
        assert response.status_code == 201
        project = response.json()

        dashboard = client.get(
            "/api/v1/workbench", params={"project_id": project["id"]}
        )
        assert dashboard.status_code == 200
        payload = dashboard.json()
        assert payload["project"]["name"] == "智能办公软件追踪"
        assert payload["metrics"][1]["value"] == "0"
        assert payload["daily_brief"]["insight_id"] is None


def test_claim_review_updates_queue(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        dashboard = client.get("/api/v1/workbench").json()
        item_id = dashboard["review_queue"]["items"][0]["id"]
        response = client.post(
            f"/api/v1/reviews/{item_id}/claim",
            headers={"X-User-Id": "user_lin_che"},
        )
        assert response.status_code == 200
        assert response.json()["item"]["status"] == "claimed"
        assert response.json()["pending_count"] == 6

        refreshed = client.get("/api/v1/workbench").json()
        assert refreshed["review_queue"]["total"] == 6
        assert len(refreshed["review_queue"]["items"]) == 3


def test_generate_report_and_search(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        report = client.post(
            "/api/v1/reports/generate",
            json={"project_id": "prj_ai_agent", "template": "daily"},
        )
        assert report.status_code == 202
        assert report.json()["state"] == "生成中"

        search = client.get(
            "/api/v1/search", params={"q": "Agent", "project_id": "prj_ai_agent"}
        )
        assert search.status_code == 200
        assert search.json()["total"] >= 1


def test_reporting_alerts_approval_and_real_exports(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        dashboard = client.get(
            "/api/v1/reports", params={"project_id": "prj_ai_agent"}
        )
        assert dashboard.status_code == 200, dashboard.text
        payload = dashboard.json()
        assert len(payload["templates"]) == 6
        assert payload["summary"]["evidence_coverage"] == 100
        assert payload["alerts"][0]["source_count"] >= 1

        created = client.post(
            "/api/v1/reports/generate",
            json={
                "project_id": "prj_ai_agent",
                "template": "weekly",
                "template_id": "tpl_weekly",
                "time_window": "7d",
                "audience": "product",
                "language": "zh-CN",
                "length": "standard",
            },
        )
        assert created.status_code == 202, created.text
        report_id = created.json()["id"]
        detail = client.get(f"/api/v1/reports/{report_id}")
        assert detail.status_code == 200
        assert detail.json()["state"] == "待审批"
        assert detail.json()["evidence_count"] > 0
        assert "执行摘要" in detail.json()["sections"]

        approved = client.post(
            f"/api/v1/reports/{report_id}/approval",
            json={"decision": "approve", "note": "证据完整"},
        )
        assert approved.status_code == 200
        assert approved.json()["state"] == "已交付"
        assert approved.json()["approval_status"] == "approved"

        word = client.get(
            f"/api/v1/reports/{report_id}/export", params={"format": "docx"}
        )
        assert word.status_code == 200
        assert word.content.startswith(b"PK")
        assert "wordprocessingml" in word.headers["content-type"]
        pdf = client.get(
            f"/api/v1/reports/{report_id}/export", params={"format": "pdf"}
        )
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF-1.4")

        alert = payload["alerts"][0]
        acknowledged = client.post(
            f"/api/v1/alerts/{alert['id']}/actions",
            json={"action": "acknowledge", "note": "已指派分析师"},
        )
        assert acknowledged.status_code == 200
        assert acknowledged.json()["status"] == "acknowledged"

        rule = client.post(
            "/api/v1/alert-rules",
            json={
                "project_id": "prj_ai_agent",
                "name": "高置信定价变化",
                "keywords": ["定价"],
                "event_types": ["price_increase", "price_decrease"],
                "min_impact": "medium",
                "min_confidence": 88,
                "quiet_minutes": 180,
                "escalation_minutes": 60,
                "channels": ["in_app", "email"],
            },
        )
        assert rule.status_code == 201, rule.text
        assert rule.json()["enabled"] is True


def test_admin_rbac_security_model_incident_and_backup(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        denied = client.get(
            "/api/v1/admin", headers={"X-User-Id": "user_zhou_qi"}
        )
        assert denied.status_code == 403

        dashboard = client.get("/api/v1/admin")
        assert dashboard.status_code == 200, dashboard.text
        payload = dashboard.json()
        assert payload["organization"]["sso_enforced"] is True
        assert len(payload["roles"]) == 5
        assert payload["summary"]["availability"] >= 99

        updated_user = client.patch(
            "/api/v1/admin/users/user_zhou_qi/access",
            json={
                "role_id": "role_viewer",
                "mfa_enabled": True,
                "export_permission": "standard",
            },
        )
        assert updated_user.status_code == 200, updated_user.text
        assert updated_user.json()["role_name"] == "业务查看者"
        assert updated_user.json()["mfa_enabled"] is True

        updated_model = client.patch(
            "/api/v1/admin/models/mdl_primary",
            json={"monthly_budget": 24000, "fallback_model": "mdl_private"},
        )
        assert updated_model.status_code == 200
        assert updated_model.json()["monthly_budget"] == 24000

        incident = next(
            item for item in payload["incidents"] if item["status"] != "resolved"
        )
        resolved = client.post(
            f"/api/v1/admin/incidents/{incident['id']}/actions",
            json={"action": "resolve", "note": "延迟已恢复"},
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "resolved"

        backup = client.post("/api/v1/admin/backups")
        assert backup.status_code == 202
        backup_record = backup.json()["backup"]
        assert backup_record["backup_type"] == "full"
        assert backup_record["status"] == "succeeded"
        assert backup_record["restore_verified"] is True
        backup_path = tmp_path / "backups" / f"{backup_record['id']}.db"
        assert backup_path.is_file()
        assert backup_path.stat().st_size == backup_record["size_bytes"]
        with sqlite3.connect(backup_path) as verification:
            assert verification.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_rag_query_is_grounded_traceable_and_refuses_missing_evidence(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/rag/query",
            json={
                "project_id": "prj_ai_agent",
                "question": "哪些竞品正在强化企业治理能力？",
                "filters": {"top_k": 6},
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["answer_type"] == "grounded"
        assert payload["citations"]
        assert all(item["evidence_excerpt"] for item in payload["citations"])
        assert all(item["source_url"].startswith("https://") for item in payload["citations"])
        assert "[1]" in payload["answer"]
        assert payload["trace"]["candidate_count"] >= payload["trace"]["retrieved_count"]
        assert [stage["key"] for stage in payload["trace"]["stages"]] == [
            "scope",
            "retrieve",
            "ground",
        ]

        insufficient = client.post(
            "/api/v1/rag/query",
            json={
                "project_id": "prj_ai_agent",
                "question": "Microsoft 的公开套餐价格是多少？",
                "filters": {
                    "competitors": ["Microsoft"],
                    "categories": ["pricing"],
                    "review_statuses": ["verified"],
                },
            },
        )
        assert insufficient.status_code == 200, insufficient.text
        assert insufficient.json()["answer_type"] == "insufficient"
        assert insufficient.json()["citations"] == []
        assert "不" in insufficient.json()["answer"]


def test_competitive_analysis_agent_persists_matrix_swot_and_citations(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        overview = client.get(
            "/api/v1/competitive-analysis", params={"project_id": "prj_ai_agent"}
        )
        assert overview.status_code == 200, overview.text
        assert set(overview.json()["suggested_competitors"]) >= {
            "OpenAI",
            "Google",
            "Anthropic",
        }

        response = client.post(
            "/api/v1/competitive-analysis/runs",
            json={
                "project_id": "prj_ai_agent",
                "competitors": ["OpenAI", "Google", "Anthropic"],
                "dimensions": ["capability", "pricing", "governance", "release"],
                "range_key": "30d",
            },
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert len(payload["matrix"]) == 12
        assert len(payload["swot"]) == 3
        assert payload["citations"]
        assert payload["source_count"] >= 1
        assert payload["agent_steps"][0]["agent"] == "分析规划 Agent"
        assert payload["agent_steps"][-1]["agent"] == "策略 Agent"
        assert all(
            finding["citation_ids"]
            for finding in payload["findings"]
            if finding["type"] == "fact"
        )
        missing_cells = [
            cell for cell in payload["matrix"] if cell["status"] == "missing"
        ]
        assert missing_cells
        assert all("不据此推断竞争劣势" in cell["summary"] for cell in missing_cells)

        detail = client.get(
            f"/api/v1/competitive-analysis/runs/{payload['id']}"
        )
        assert detail.status_code == 200, detail.text
        assert detail.json() == payload
        refreshed = client.get(
            "/api/v1/competitive-analysis", params={"project_id": "prj_ai_agent"}
        ).json()
        assert refreshed["runs"][0]["id"] == payload["id"]

        unknown = client.post(
            "/api/v1/competitive-analysis/runs",
            json={
                "project_id": "prj_ai_agent",
                "competitors": ["OpenAI", "Unknown Co"],
                "dimensions": ["capability"],
                "range_key": "all",
            },
        )
        assert unknown.status_code == 422


def test_source_list_masks_credentials_and_supports_filters(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get(
            "/api/v1/sources", params={"project_id": "prj_ai_agent"}
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["total"] == 8
        assert payload["summary"]["enabled"] == 7
        assert payload["summary"]["needs_attention"] == 2
        assert all("credential_ref" not in item for item in payload["items"])
        credential_source = next(
            item for item in payload["items"] if item["credential_masked"]
        )
        assert credential_source["credential_masked"].startswith("••••")

        filtered = client.get(
            "/api/v1/sources",
            params={
                "project_id": "prj_ai_agent",
                "status": "healthy",
                "source_type": "rss",
                "q": "Anthropic",
            },
        )
        assert filtered.status_code == 200
        assert [item["id"] for item in filtered.json()["items"]] == [
            "src_anthropic_rss"
        ]


def test_source_enablement_checks_and_disabled_run_gate(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        created = client.post(
            "/api/v1/sources",
            json={
                "project_id": "prj_ai_agent",
                "name": "示例官网新闻",
                "source_type": "webpage",
                "endpoint": "https://example.test/news",
                "subject": "示例竞品",
                "access_method": "public",
                "crawl_strategy": "正文差异",
                "regions": ["cn"],
                "authorization_basis": "待完成公开条款确认",
                "authorization_status": "pending",
                "data_classification": "public",
                "retention_days": 180,
                "schedule_frequency": "daily",
                "rate_limit_per_minute": 10,
                "fields_available": [],
                "robots_acknowledged": False,
                "terms_acknowledged": False,
            },
        )
        assert created.status_code == 201
        source_id = created.json()["id"]
        assert created.json()["enabled"] is False
        assert created.json()["activation_ready"] is False

        blocked_enable = client.patch(
            f"/api/v1/sources/{source_id}/status", json={"enabled": True}
        )
        assert blocked_enable.status_code == 409

        failed_check = client.post(f"/api/v1/sources/{source_id}/checks")
        assert failed_check.status_code == 200
        assert failed_check.json()["item"]["activation_ready"] is False

        updated = client.patch(
            f"/api/v1/sources/{source_id}",
            json={
                "authorization_basis": "公开官网合理访问，经合规确认",
                "authorization_status": "approved",
                "fields_available": ["title", "published_at", "body"],
                "robots_acknowledged": True,
                "terms_acknowledged": True,
            },
        )
        assert updated.status_code == 200
        assert all(
            item["status"] == "pending" for item in updated.json()["checks"]
        )

        passed_check = client.post(f"/api/v1/sources/{source_id}/checks")
        assert passed_check.status_code == 200
        assert passed_check.json()["item"]["activation_ready"] is True

        enabled = client.patch(
            f"/api/v1/sources/{source_id}/status", json={"enabled": True}
        )
        assert enabled.status_code == 200
        assert enabled.json()["item"]["enabled"] is True

        run = client.post(f"/api/v1/sources/{source_id}/runs")
        assert run.status_code == 202
        assert run.json()["status"] == "queued"

        disabled = client.patch(
            f"/api/v1/sources/{source_id}/status", json={"enabled": False}
        )
        assert disabled.status_code == 200
        blocked_run = client.post(f"/api/v1/sources/{source_id}/runs")
        assert blocked_run.status_code == 409
        assert "停用" in blocked_run.json()["detail"]

        deleted = client.delete(f"/api/v1/sources/{source_id}")
        assert deleted.status_code == 200
        assert deleted.json()["id"] == source_id
        assert deleted.json()["archived"] is True
        assert deleted.json()["archived_at"]

        assert client.get(
            "/api/v1/sources", params={"project_id": "prj_ai_agent"}
        ).json()["summary"]["total"] == 8
        assert client.get(f"/api/v1/sources/{source_id}").status_code == 404
        archived = client.app.state.database.get_source(
            source_id, include_archived=True
        )
        assert archived is not None
        with client.app.state.database.session() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM source_runs WHERE source_id=?", (source_id,)
            ).fetchone()[0] == 1

        wrong_confirmation = client.request(
            "DELETE",
            f"/api/v1/sources/{source_id}/purge",
            json={"confirmation": source_id},
        )
        assert wrong_confirmation.status_code == 409
        purged = client.request(
            "DELETE",
            f"/api/v1/sources/{source_id}/purge",
            json={"confirmation": f"PURGE:{source_id}"},
        )
        assert purged.status_code == 200, purged.text
        assert purged.json()["purged"] is True
        assert purged.json()["removed_runs"] == 1
        assert client.app.state.database.get_source(
            source_id, include_archived=True
        ) is None


def test_production_requires_signed_bearer_token(tmp_path: Path) -> None:
    secret = "production-test-secret-with-at-least-32-characters"
    settings = Settings(
        environment="production",
        debug=False,
        database_path=tmp_path / "production.db",
        cors_origins=("https://app.example.test",),
        auth_secret=secret,
        allow_legacy_user_header=True,
        scheduler_enabled=False,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/projects").status_code == 401
        assert client.get(
            "/api/v1/projects", headers={"X-User-Id": "user_lin_che"}
        ).status_code == 401

        token = create_access_token("user_lin_che", secret)
        response = client.get(
            "/api/v1/projects", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, response.text
        assert {item["id"] for item in response.json()} == {
            "prj_ai_agent",
            "prj_collaboration",
        }

        forged = create_access_token("user_lin_che", "different-secret")
        assert client.get(
            "/api/v1/projects", headers={"Authorization": f"Bearer {forged}"}
        ).status_code == 401


def test_existing_database_adds_source_archive_columns(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    legacy_schema = SCHEMA.replace(
        "    archived_at TEXT,\n    archived_by TEXT REFERENCES users(id),\n", ""
    )
    with sqlite3.connect(database_path) as connection:
        connection.executescript(legacy_schema)

    database = Database(database_path)
    database.initialize()
    with database.session() as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(data_sources)").fetchall()
        }
        assert {"archived_at", "archived_by"}.issubset(columns)
        assert connection.execute(
            "SELECT COUNT(*) FROM data_sources WHERE archived_at IS NULL"
        ).fetchone()[0] == 8


def test_project_scope_permissions_and_data_domains_are_enforced(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        analyst = {"X-User-Id": "user_zhou_qi"}
        projects = client.get("/api/v1/projects", headers=analyst)
        assert projects.status_code == 200
        assert [item["id"] for item in projects.json()] == ["prj_ai_agent"]

        assert client.get(
            "/api/v1/workbench",
            params={"project_id": "prj_collaboration"},
            headers=analyst,
        ).status_code == 403
        assert client.get(
            "/api/v1/sources",
            params={"project_id": "prj_ai_agent"},
            headers=analyst,
        ).status_code == 200
        assert client.post(
            "/api/v1/sources",
            headers=analyst,
            json={
                "project_id": "prj_ai_agent",
                "name": "analyst-write-attempt",
                "source_type": "rss",
                "endpoint": "https://example.test/analyst.xml",
                "subject": "scope-test",
                "authorization_basis": "public feed",
                "authorization_status": "approved",
                "data_classification": "public",
                "robots_acknowledged": True,
                "terms_acknowledged": True,
            },
        ).status_code == 403
        assert client.get("/api/v1/admin", headers=analyst).status_code == 403

        search = client.get(
            "/api/v1/search", params={"q": "企业协作"}, headers=analyst
        )
        assert search.status_code == 200
        assert all(
            item["id"] != "prj_collaboration" for item in search.json()["items"]
        )

        with client.app.state.database.session() as connection:
            connection.execute(
                "UPDATE user_memberships SET data_domains_json='[\"public\"]' "
                "WHERE user_id='user_zhou_qi'"
            )
        restricted = client.get(
            "/api/v1/sources/src_ms_graph", headers=analyst
        )
        assert restricted.status_code == 403
        filtered = client.get(
            "/api/v1/sources",
            params={"project_id": "prj_ai_agent"},
            headers=analyst,
        )
        assert filtered.status_code == 200
        assert all(
            item["data_classification"] == "public"
            for item in filtered.json()["items"]
        )

        public_candidates = client.app.state.database.list_rag_candidates(
            "prj_ai_agent", allowed_domains=["public"]
        )
        assert public_candidates
        assert all(
            row["source_data_classification"] == "public"
            for row in public_candidates
        )
        rag = client.post(
            "/api/v1/rag/query",
            headers=analyst,
            json={
                "project_id": "prj_ai_agent",
                "question": public_candidates[0]["title"],
                "filters": {"top_k": 10},
            },
        )
        assert rag.status_code == 200, rag.text
        for citation in rag.json()["citations"]:
            item = client.app.state.database.get_knowledge_item(citation["item_id"])
            assert item is not None
            assert item["source_data_classification"] == "public"


def test_source_credential_rotation_returns_mask_only(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/sources/src_ms_graph/credentials/rotate",
            json={
                "credential_ref": "vault://jinguan/microsoft-graph-v2",
                "credential_expires_at": "2027-07-31T00:00:00Z",
            },
        )
        assert response.status_code == 200
        item = response.json()["item"]
        assert item["credential_masked"].endswith("h-v2")
        assert "credential_ref" not in item


def test_archived_source_keeps_history_but_leaves_active_retrieval(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        database = client.app.state.database
        with database.session() as connection:
            source = connection.execute(
                """SELECT source_id, COUNT(*) AS item_count
                   FROM knowledge_items
                   WHERE source_id IS NOT NULL
                   GROUP BY source_id ORDER BY item_count DESC LIMIT 1"""
            ).fetchone()
            assert source is not None
            source_id = source["source_id"]
            before = {
                "knowledge": connection.execute(
                    "SELECT COUNT(*) FROM knowledge_items WHERE source_id=?",
                    (source_id,),
                ).fetchone()[0],
                "runs": connection.execute(
                    "SELECT COUNT(*) FROM source_runs WHERE source_id=?", (source_id,)
                ).fetchone()[0],
                "documents": connection.execute(
                    "SELECT COUNT(*) FROM collection_documents WHERE source_id=?",
                    (source_id,),
                ).fetchone()[0],
            }
        assert any(
            row["source_id"] == source_id
            for row in database.list_rag_candidates(
                "prj_ai_agent",
                allowed_domains=["public", "internal", "restricted"],
            )
        )

        disabled = client.patch(
            f"/api/v1/sources/{source_id}/status", json={"enabled": False}
        )
        assert disabled.status_code == 200, disabled.text
        archived = client.delete(f"/api/v1/sources/{source_id}")
        assert archived.status_code == 200, archived.text

        assert all(
            row["source_id"] != source_id
            for row in database.list_rag_candidates(
                "prj_ai_agent",
                allowed_domains=["public", "internal", "restricted"],
            )
        )
        with database.session() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM knowledge_items WHERE source_id=?", (source_id,)
            ).fetchone()[0] == before["knowledge"]
            assert connection.execute(
                "SELECT COUNT(*) FROM source_runs WHERE source_id=?", (source_id,)
            ).fetchone()[0] == before["runs"]
            assert connection.execute(
                "SELECT COUNT(*) FROM collection_documents WHERE source_id=?",
                (source_id,),
            ).fetchone()[0] == before["documents"]


def test_static_rss_and_api_collectors_persist_traceable_documents(tmp_path: Path) -> None:
    with fixture_server() as base_url, make_client(
        tmp_path, allow_private_networks=True
    ) as client:
        cases = [
            ("webpage", f"{base_url}/page", {}),
            ("rss", f"{base_url}/feed", {"max_items": 10}),
            (
                "public_api",
                f"{base_url}/api",
                {
                    "items_path": "data.items",
                    "title_path": "name",
                    "content_path": "description",
                    "url_path": "url",
                    "published_path": "published_at",
                    "max_items": 10,
                },
            ),
        ]
        for index, (source_type, endpoint, collection_config) in enumerate(cases):
            created = client.post(
                "/api/v1/sources",
                json={
                    "project_id": "prj_ai_agent",
                    "name": f"采集测试 {source_type}",
                    "source_type": source_type,
                    "endpoint": endpoint,
                    "subject": "测试主体",
                    "access_method": "public",
                    "crawl_strategy": "增量采集",
                    "regions": ["global"],
                    "authorization_basis": "本地测试服务",
                    "authorization_status": "approved",
                    "data_classification": "public",
                    "retention_days": 30,
                    "schedule_frequency": "manual",
                    "rate_limit_per_minute": 30,
                    "fields_available": ["title", "body", "published_at"],
                    "collection_config": {"timeout_seconds": 5, **collection_config},
                    "robots_acknowledged": True,
                    "terms_acknowledged": True,
                },
            )
            assert created.status_code == 201, created.text
            source_id = created.json()["id"]
            assert client.post(f"/api/v1/sources/{source_id}/checks").status_code == 200
            assert client.patch(
                f"/api/v1/sources/{source_id}/status", json={"enabled": True}
            ).status_code == 200

            queued = client.post(f"/api/v1/sources/{source_id}/runs")
            assert queued.status_code == 202, queued.text
            detail = client.get(
                f"/api/v1/collection/runs/{queued.json()['id']}"
            ).json()
            assert detail["status"] == "succeeded"
            assert detail["documents_created"] == 1
            assert detail["parser_steps"]
            assert [step["key"] for step in detail["workflow_steps"]] == [
                "collect",
                "normalize",
                "deduplicate",
                "quality_gate",
            ]
            assert all(
                step["status"] == "succeeded" for step in detail["workflow_steps"]
            )

            documents = client.get(
                "/api/v1/collection/documents",
                params={"project_id": "prj_ai_agent", "source_id": source_id},
            )
            assert documents.status_code == 200
            assert documents.json()["summary"]["total"] == 1
            assert documents.json()["items"][0]["content_hash"]
            assert documents.json()["items"][0]["readable_excerpt"]


def test_file_upload_collection_and_fingerprint_deduplication(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/collection/files",
            data={
                "project_id": "prj_ai_agent",
                "name": "产品价格 CSV",
                "subject": "示例竞品",
                "authorization_basis": "内部测试资料",
                "retention_days": "30",
            },
            files={"file": ("pricing.csv", b"plan,price\nPro,99\n", "text/csv")},
        )
        assert response.status_code == 202, response.text
        payload = response.json()
        source_id = payload["source"]["id"]
        run_id = payload["run"]["id"]

        run = client.get(f"/api/v1/collection/runs/{run_id}").json()
        assert run["status"] == "succeeded"
        assert run["documents_created"] == 1

        documents = client.get(
            "/api/v1/collection/documents",
            params={"project_id": "prj_ai_agent", "source_id": source_id},
        ).json()
        document_id = documents["items"][0]["id"]
        detail = client.get(f"/api/v1/collection/documents/{document_id}").json()
        assert detail["metadata"]["row_count"] == 1
        assert "Pro" in detail["readable_text"]
        raw = client.get(f"/api/v1/collection/documents/{document_id}/raw")
        assert raw.content == b"plan,price\nPro,99\n"
        assert raw.headers["x-content-type-options"] == "nosniff"

        repeated = client.post(f"/api/v1/sources/{source_id}/runs")
        assert repeated.status_code == 202
        repeated_run = client.get(
            f"/api/v1/collection/runs/{repeated.json()['id']}"
        ).json()
        assert repeated_run["status"] == "succeeded"
        assert repeated_run["duplicates_skipped"] == 1
        assert repeated_run["documents_created"] == 0


def test_processing_pipeline_extracts_traceable_entities_events_and_cross_source_duplicates(
    tmp_path: Path,
) -> None:
    article = """<!doctype html><html lang="zh-CN"><body>
    <nav>首页</nav><article><h1>星河科技有限公司发布 Nova Pro 2.1</h1>
    <p>2026年7月31日，星河科技有限公司在上海正式发布产品 Nova Pro 2.1，
    新增智能会议摘要功能，企业版价格为 ¥99/月。</p>
    <p>该版本面向中国团队开放，并将逐步进入东南亚市场。</p></article>
    <footer>版权所有 2026</footer></body></html>""".encode("utf-8")

    with make_client(tmp_path) as client:
        first = client.post(
            "/api/v1/collection/files",
            data={
                "project_id": "prj_ai_agent",
                "name": "星河发布稿",
                "subject": "星河科技",
                "authorization_basis": "企业公开发布稿",
            },
            files={"file": ("release.html", article, "text/html")},
        )
        assert first.status_code == 202, first.text

        overview = client.get(
            "/api/v1/processing", params={"project_id": "prj_ai_agent"}
        )
        assert overview.status_code == 200, overview.text
        payload = overview.json()
        assert payload["summary"]["processed"] == 1
        assert payload["summary"]["entities"] >= 4
        assert payload["summary"]["events"] >= 1
        document_id = payload["items"][0]["document_id"]

        detail = client.get(f"/api/v1/processing/documents/{document_id}")
        assert detail.status_code == 200, detail.text
        result = detail.json()
        assert result["language"] == "zh"
        assert "首页" not in result["clean_text"]
        assert any(item["type"] == "company" for item in result["entities"])
        assert any(item["type"] == "release" for item in result["events"])
        assert all(item["end"] > item["start"] for item in result["entities"])
        assert {step["key"] for step in result["steps"]} >= {
            "body",
            "denoise",
            "language",
            "deduplicate",
            "entities",
            "events",
            "quality",
        }

        knowledge = client.get(
            "/api/v1/knowledge",
            params={"project_id": "prj_ai_agent", "q": "Nova Pro"},
        )
        assert knowledge.status_code == 200, knowledge.text
        derived_items = knowledge.json()["items"]
        assert any(item["document_id"] == document_id for item in derived_items)
        assert any(item["item_type"] == "event" for item in derived_items)

        second = client.post(
            "/api/v1/collection/files",
            data={
                "project_id": "prj_ai_agent",
                "name": "合作媒体转载",
                "subject": "星河科技",
                "authorization_basis": "授权转载测试",
            },
            files={"file": ("mirror.html", article, "text/html")},
        )
        assert second.status_code == 202, second.text
        duplicates = client.get(
            "/api/v1/processing", params={"project_id": "prj_ai_agent"}
        ).json()
        assert duplicates["summary"]["duplicates"] == 1
        duplicate_item = next(
            item for item in duplicates["items"] if item["duplicate"]["type"] == "exact"
        )
        assert duplicate_item["duplicate"]["similarity"] == 1
        assert duplicate_item["duplicate"]["document_id"] == document_id

        rerun = client.post(
            f"/api/v1/processing/documents/{document_id}/run",
            json={
                "extract_body": True,
                "denoise": True,
                "deduplicate": True,
                "detect_language": True,
                "ocr": True,
                "extract_entities": True,
                "extract_events": True,
            },
        )
        assert rerun.status_code == 200, rerun.text
        assert rerun.json()["processor_version"] == "processing-1.0.0"


def test_processing_detects_english_company_and_product_entities(tmp_path: Path) -> None:
    article = (
        b"<html><body><article><h1>Google launches Workspace update</h1>"
        b"<p>Google released Google Workspace with a new meeting summary "
        b"feature on August 1, 2026.</p></article></body></html>"
    )

    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/collection/files",
            data={
                "project_id": "prj_ai_agent",
                "name": "Google Workspace release",
                "subject": "Google",
                "authorization_basis": "Public product announcement",
            },
            files={"file": ("workspace.html", article, "text/html")},
        )
        assert response.status_code == 202, response.text

        overview = client.get(
            "/api/v1/processing", params={"project_id": "prj_ai_agent"}
        ).json()
        detail = client.get(
            f"/api/v1/processing/documents/{overview['items'][0]['document_id']}"
        ).json()
        assert detail["language"] == "en"
        assert any(
            entity["type"] == "company" and entity["text"] == "Google"
            for entity in detail["entities"]
        )
        assert any(
            entity["type"] == "product" and entity["text"] == "Google Workspace"
            for entity in detail["entities"]
        )


def test_api_collector_rejects_state_changing_methods(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/sources",
            json={
                "project_id": "prj_ai_agent",
                "name": "不安全 API",
                "source_type": "public_api",
                "endpoint": "https://example.com/api",
                "subject": "示例主体",
                "access_method": "public",
                "crawl_strategy": "接口采集",
                "regions": ["global"],
                "authorization_basis": "公开接口",
                "authorization_status": "approved",
                "data_classification": "public",
                "retention_days": 30,
                "schedule_frequency": "manual",
                "rate_limit_per_minute": 30,
                "fields_available": ["title"],
                "collection_config": {"request_method": "POST"},
                "robots_acknowledged": True,
                "terms_acknowledged": True,
            },
        )
        assert response.status_code == 422
        assert "只读 GET" in response.text


def test_orchestration_dashboard_and_schedule_policy(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get(
            "/api/v1/orchestration", params={"project_id": "prj_ai_agent"}
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["scheduled_sources"] == 7
        assert [node["key"] for node in payload["workflow_nodes"]] == [
            "collect",
            "normalize",
            "deduplicate",
            "quality_gate",
        ]
        assert len(payload["schedules"]) == 8

        updated = client.patch(
            "/api/v1/sources/src_anthropic_rss/schedule",
            json={
                "schedule_frequency": "15m",
                "rate_limit_per_minute": 12,
                "concurrency_limit": 2,
                "task_timeout_seconds": 90,
                "max_attempts": 5,
                "retry_backoff_seconds": 3,
                "priority": 9,
            },
        )
        assert updated.status_code == 200, updated.text
        source = updated.json()
        assert source["enabled"] is True
        assert source["schedule_frequency"] == "15m"
        assert source["concurrency_limit"] == 2
        assert source["task_timeout_seconds"] == 90
        assert source["max_attempts"] == 5
        assert source["priority"] == 9
        assert source["next_run_at"]


def test_retry_backoff_and_restart_recovery_are_persisted(tmp_path: Path) -> None:
    with make_client(tmp_path, allow_private_networks=True) as client:
        created = client.post(
            "/api/v1/sources",
            json={
                "project_id": "prj_ai_agent",
                "name": "重试与恢复测试来源",
                "source_type": "webpage",
                "endpoint": "http://127.0.0.1:1/unavailable",
                "subject": "测试主体",
                "access_method": "public",
                "crawl_strategy": "增量采集",
                "regions": ["global"],
                "authorization_basis": "本地故障注入测试",
                "authorization_status": "approved",
                "data_classification": "public",
                "retention_days": 30,
                "schedule_frequency": "manual",
                "rate_limit_per_minute": 60,
                "concurrency_limit": 1,
                "task_timeout_seconds": 5,
                "max_attempts": 2,
                "retry_backoff_seconds": 1,
                "priority": 8,
                "fields_available": ["title", "body"],
                "collection_config": {"timeout_seconds": 2},
                "robots_acknowledged": True,
                "terms_acknowledged": True,
            },
        )
        assert created.status_code == 201, created.text
        source_id = created.json()["id"]
        assert client.post(f"/api/v1/sources/{source_id}/checks").status_code == 200
        assert client.patch(
            f"/api/v1/sources/{source_id}/status", json={"enabled": True}
        ).status_code == 200

        queued = client.post(
            "/api/v1/orchestration/triggers",
            json={"source_id": source_id, "trigger_type": "event", "event_name": "test"},
        )
        assert queued.status_code == 202, queued.text
        run_id = queued.json()["id"]
        detail = client.get(f"/api/v1/collection/runs/{run_id}").json()
        assert detail["status"] == "queued"
        assert detail["attempt"] == 1
        assert detail["next_retry_at"]
        assert detail["retry_delays"] == [1]
        assert detail["workflow_steps"][0]["status"] == "waiting_retry"

        database = client.app.state.database
        with database.session() as connection:
            connection.execute(
                "UPDATE source_runs SET status='running', available_at=NULL WHERE id=?",
                (run_id,),
            )
            connection.execute(
                "UPDATE workflow_steps SET status='running' WHERE run_id=? AND step_key='collect'",
                (run_id,),
            )
        assert database.recover_interrupted_runs() == [run_id]
        recovered = client.get(f"/api/v1/collection/runs/{run_id}").json()
        assert recovered["status"] == "queued"
        assert recovered["recovered_from_restart"] is True
        assert "服务重启" in recovered["parser_steps"][-1]
