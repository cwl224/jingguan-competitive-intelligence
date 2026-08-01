from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from uuid import uuid4

from .database import Database
from .rag import RAGEngine, RetrievalHit, tokenize, utc_now
from .schemas import (
    AnalysisAgentStep,
    AnalysisFinding,
    BusinessRecommendation,
    ComparisonCell,
    CompetitiveAnalysisOverview,
    CompetitiveAnalysisRequest,
    CompetitiveAnalysisResult,
    CompetitiveAnalysisRunSummary,
    CompetitorSWOT,
    RAGCitation,
    RAGFilters,
    SWOTEntry,
)


DIMENSIONS: dict[str, dict[str, object]] = {
    "capability": {
        "label": "产品能力",
        "query": "产品能力 功能 连接器 工具调用 浏览器操作",
        "categories": {"product_capability", "feature_add", "product"},
        "keywords": {"功能", "能力", "连接器", "工具调用", "浏览器", "产品"},
    },
    "pricing": {
        "label": "套餐定价",
        "query": "套餐 定价 价格 调价",
        "categories": {"pricing"},
        "keywords": {"定价", "价格", "套餐", "调价"},
    },
    "governance": {
        "label": "企业治理",
        "query": "企业治理 权限 审计 数据驻留 管理员 合规",
        "categories": {"data_residency", "governance", "compliance", "strategy"},
        "keywords": {"治理", "权限", "审计", "数据驻留", "管理员", "合规"},
    },
    "release": {
        "label": "发布节奏",
        "query": "发布 上线 新增 版本 更新",
        "categories": {"release", "feature_add"},
        "keywords": {"发布", "上线", "新增", "版本", "更新"},
    },
    "market": {
        "label": "市场与生态",
        "query": "市场 地区 渠道 生态 合作 进入 退出",
        "categories": {"market", "expansion", "partnership", "channel", "ecosystem"},
        "keywords": {"市场", "地区", "渠道", "生态", "合作", "进入", "退出"},
    },
    "reputation": {
        "label": "口碑信号",
        "query": "用户反馈 口碑 舆情 评价",
        "categories": {"reputation", "sentiment", "user_feedback"},
        "keywords": {"反馈", "口碑", "舆情", "评价"},
    },
}


class CompetitiveAnalysisAgent:
    def __init__(self, database: Database, rag: RAGEngine):
        self.database = database
        self.rag = rag

    @staticmethod
    def _start_date(range_key: str) -> str | None:
        days = {"7d": 7, "30d": 30, "90d": 90}.get(range_key)
        if not days:
            return None
        return (datetime.now(UTC) - timedelta(days=days)).date().isoformat()

    @staticmethod
    def _matches_dimension(hit: RetrievalHit, dimension: str) -> bool:
        definition = DIMENSIONS[dimension]
        item = hit.item
        if str(item.get("category") or "") in definition["categories"]:
            return True
        searchable = " ".join(
            str(item.get(field) or "")
            for field in ("title", "summary", "content", "tags_json", "evidence_excerpt")
        )
        terms = set(tokenize(searchable))
        for keyword in definition["keywords"]:
            if set(tokenize(str(keyword))).intersection(terms):
                return True
        return False

    def overview(self, project_id: str) -> CompetitiveAnalysisOverview:
        rows = self.database.list_competitive_analyses(project_id)
        runs = []
        for row in rows:
            result = json.loads(row["result_json"])
            runs.append(
                CompetitiveAnalysisRunSummary(
                    id=row["id"],
                    title=row["title"],
                    status=row["status"],
                    competitors=json.loads(row["competitors_json"]),
                    dimensions=json.loads(row["dimensions_json"]),
                    range_key=row["range_key"],
                    coverage_rate=int(row["coverage_rate"]),
                    sample_size=int(row["sample_size"]),
                    created_at=result["created_at"],
                )
            )
        return CompetitiveAnalysisOverview(
            project_id=project_id,
            suggested_competitors=self.database.list_competitor_subjects(project_id),
            dimensions={key: str(value["label"]) for key, value in DIMENSIONS.items()},
            runs=runs,
        )

    def get(self, run_id: str) -> CompetitiveAnalysisResult | None:
        row = self.database.get_competitive_analysis(run_id)
        if row is None:
            return None
        return CompetitiveAnalysisResult.model_validate_json(row["result_json"])

    def run(
        self, payload: CompetitiveAnalysisRequest, actor_id: str
    ) -> CompetitiveAnalysisResult:
        run_id = f"car_{uuid4().hex[:16]}"
        created_at = utc_now()
        start_date = self._start_date(payload.range_key)
        citation_by_item: dict[str, int] = {}
        citations: list[RAGCitation] = []
        hits_by_cell: dict[tuple[str, str], list[RetrievalHit]] = {}
        access = self.database.get_user_access(actor_id)
        allowed_domains = list(access["data_domains"]) if access is not None else []

        def register(hit: RetrievalHit) -> int:
            item_id = str(hit.item["id"])
            if item_id in citation_by_item:
                return citation_by_item[item_id]
            citation_id = len(citations) + 1
            citation_by_item[item_id] = citation_id
            citations.append(self.rag.citation_from_hit(hit, citation_id))
            return citation_id

        matrix: list[ComparisonCell] = []
        for competitor in payload.competitors:
            for dimension in payload.dimensions:
                definition = DIMENSIONS[dimension]
                hits, _, _ = self.rag.retrieve(
                    payload.project_id,
                    f"{competitor} {definition['query']}",
                    RAGFilters(
                        competitors=[competitor],
                        start_date=start_date,
                        include_at_risk=True,
                        top_k=12,
                    ),
                    allowed_domains,
                )
                hits = [hit for hit in hits if self._matches_dimension(hit, dimension)][:4]
                hits_by_cell[(competitor, dimension)] = hits
                if not hits:
                    matrix.append(
                        ComparisonCell(
                            competitor=competitor,
                            dimension=dimension,
                            dimension_label=str(definition["label"]),
                            status="missing",
                            summary="暂无可信数据；不据此推断竞争劣势。",
                            confidence=0,
                            evidence_count=0,
                            citation_ids=[],
                        )
                    )
                    continue
                citation_ids = [register(hit) for hit in hits]
                confidence = round(
                    sum(int(hit.item.get("confidence") or 0) * hit.relevance for hit in hits)
                    / max(0.001, sum(hit.relevance for hit in hits))
                )
                if any(hit.item.get("review_status") == "conflict" for hit in hits):
                    status = "conflict"
                elif (
                    len(hits) == 1
                    or confidence < 82
                    or any(
                        hit.item.get("review_status") == "review_required"
                        or hit.item.get("validity_status") == "at_risk"
                        for hit in hits
                    )
                ):
                    status = "limited"
                else:
                    status = "evidence"
                summary = str(hits[0].item["summary"])
                if status == "conflict":
                    summary = f"存在来源冲突：{summary}"
                elif status == "limited":
                    summary = f"证据有限：{summary}"
                matrix.append(
                    ComparisonCell(
                        competitor=competitor,
                        dimension=dimension,
                        dimension_label=str(definition["label"]),
                        status=status,
                        summary=summary,
                        confidence=confidence,
                        evidence_count=len(hits),
                        citation_ids=citation_ids,
                    )
                )

        evidence_cells = [cell for cell in matrix if cell.status != "missing"]
        coverage_rate = round(100 * len(evidence_cells) / max(1, len(matrix)))
        source_names = {citation.source_name for citation in citations}
        findings: list[AnalysisFinding] = []
        seen_items: set[str] = set()
        for cell in sorted(evidence_cells, key=lambda item: item.confidence, reverse=True):
            for hit in hits_by_cell[(cell.competitor, cell.dimension)]:
                item_id = str(hit.item["id"])
                if item_id in seen_items:
                    continue
                seen_items.add(item_id)
                item_type = str(hit.item["item_type"])
                finding_type = "inference" if item_type == "insight" else "fact"
                findings.append(
                    AnalysisFinding(
                        type=finding_type,
                        title=str(hit.item["title"]),
                        detail=str(hit.item["summary"]),
                        impact_level=(
                            "high"
                            if int(hit.item.get("confidence") or 0) >= 92
                            and int(hit.item.get("source_count") or 0) >= 4
                            else "medium"
                            if int(hit.item.get("confidence") or 0) >= 80
                            else "low"
                        ),
                        competitors=[cell.competitor],
                        citation_ids=[register(hit)],
                    )
                )
                if len(findings) >= 7:
                    break
            if len(findings) >= 7:
                break

        swot: list[CompetitorSWOT] = []
        for competitor in payload.competitors:
            cells = [cell for cell in matrix if cell.competitor == competitor]
            supported = [cell for cell in cells if cell.status == "evidence"]
            risks = [cell for cell in cells if cell.status in {"limited", "conflict"}]
            missing = [cell for cell in cells if cell.status == "missing"]
            other_events = [
                finding
                for finding in findings
                if competitor not in finding.competitors and finding.type == "fact"
            ]
            strengths = [
                SWOTEntry(
                    text=f"{cell.dimension_label}已形成多条一致证据：{cell.summary}",
                    citation_ids=cell.citation_ids,
                )
                for cell in supported[:2]
            ]
            if not strengths:
                strengths = [SWOTEntry(text="当前证据不足，不推断相对优势。", citation_ids=[])]
            weaknesses = [
                SWOTEntry(
                    text=f"{cell.dimension_label}存在证据风险，需先复核再判断：{cell.summary}",
                    citation_ids=cell.citation_ids,
                )
                for cell in risks[:2]
            ]
            if not weaknesses:
                weaknesses = [SWOTEntry(text="暂无可被证据支持的明确弱势。", citation_ids=[])]
            opportunities = [
                SWOTEntry(
                    text=f"补齐{cell.dimension_label}的一手来源，可提高后续对比与预警可信度。",
                    citation_ids=[],
                )
                for cell in missing[:2]
            ]
            if not opportunities and supported:
                opportunities = [
                    SWOTEntry(
                        text=f"围绕{supported[0].dimension_label}建立连续时间序列，验证变化是否持续。",
                        citation_ids=supported[0].citation_ids,
                    )
                ]
            threats = [
                SWOTEntry(
                    text=f"其他竞品的高可信变化可能改变对比基线：{finding.detail}",
                    citation_ids=finding.citation_ids,
                )
                for finding in other_events[:1]
            ]
            if not threats:
                threats = [SWOTEntry(text="暂无足够的跨竞品威胁证据。", citation_ids=[])]
            swot.append(
                CompetitorSWOT(
                    competitor=competitor,
                    strengths=strengths,
                    weaknesses=weaknesses,
                    opportunities=opportunities,
                    threats=threats,
                )
            )

        recommendations: list[BusinessRecommendation] = []
        missing_cells = [cell for cell in matrix if cell.status == "missing"]
        conflict_cells = [cell for cell in matrix if cell.status == "conflict"]
        if missing_cells:
            missing_labels = sorted({cell.dimension_label for cell in missing_cells})
            recommendations.append(
                BusinessRecommendation(
                    applicable_to="数据运营与分析团队",
                    action=f"优先补采 {', '.join(missing_labels[:3])} 的一手来源，并登记授权与更新频率。",
                    basis=f"当前矩阵覆盖率为 {coverage_rate}%，有 {len(missing_cells)} 个单元格暂无可信数据。",
                    expected_impact="减少因样本缺失导致的误判，并提高后续报告引用完整度。",
                    risk="补采周期内仍不能把缺失项解释为竞品弱势。",
                    validation="补采后重跑分析，目标是每个核心单元格至少绑定 2 个有效来源。",
                    citation_ids=[],
                )
            )
        if conflict_cells:
            citation_ids = list(
                dict.fromkeys(item for cell in conflict_cells for item in cell.citation_ids)
            )
            recommendations.append(
                BusinessRecommendation(
                    applicable_to="负责定价与市场研究的分析师",
                    action="对冲突事实执行人工复核，按发布时间并列保留不同值。",
                    basis=f"本次分析发现 {len(conflict_cells)} 个冲突单元格。",
                    expected_impact="避免旧值或单一来源静默覆盖，降低错误归因风险。",
                    risk="在冲突解决前，相关结论只能以风险提示形式进入报告。",
                    validation="取得官方公告或第二个独立可信来源后，由分析师确认状态。",
                    citation_ids=citation_ids,
                )
            )
        if evidence_cells:
            leading = max(evidence_cells, key=lambda cell: cell.confidence)
            recommendations.append(
                BusinessRecommendation(
                    applicable_to="产品策略与竞争情报团队",
                    action=f"将{leading.dimension_label}加入固定周度跟踪维度，并设置变化事件预警。",
                    basis=leading.summary,
                    expected_impact="更早识别可验证的竞争动作，并沉淀连续对比基线。",
                    risk="单次变化不等于长期趋势，需持续观察样本量与时间范围。",
                    validation="连续四周跟踪变化频率、来源数及业务团队采纳情况。",
                    citation_ids=leading.citation_ids,
                )
            )

        missing_count = len(matrix) - len(evidence_cells)
        status = "completed" if missing_count == 0 and coverage_rate >= 80 else "partial"
        executive_summary = (
            f"本次对 {len(payload.competitors)} 家竞品、{len(payload.dimensions)} 个维度完成证据化对比，"
            f"引用 {len(citations)} 条知识、{len(source_names)} 个来源，矩阵覆盖率 {coverage_rate}%。"
        )
        if missing_count:
            executive_summary += (
                f"仍有 {missing_count} 个维度暂无可信数据，结果已标为空缺，未据此推断相对优劣。"
            )
        notices = [
            "事实、推断和建议已分层展示；所有事实型发现均绑定引用。",
            "SWOT 中的“优势”仅表示当前存在一致证据，不代表统计意义上的市场领先。",
        ]
        if any(cell.status == "conflict" for cell in matrix):
            notices.append("分析包含冲突证据，相关结论在人工复核前不得自动通过质量门禁。")
        completed_at = utc_now()
        result = CompetitiveAnalysisResult(
            id=run_id,
            project_id=payload.project_id,
            title=f"{' × '.join(payload.competitors[:3])}{' 等' if len(payload.competitors) > 3 else ''}竞品对比",
            status=status,
            competitors=payload.competitors,
            dimensions=payload.dimensions,
            range_key=payload.range_key,
            data_cutoff=max(
                (citation.published_at or completed_at for citation in citations),
                default="暂无可信数据",
            ),
            sample_size=len(citations),
            source_count=len(source_names),
            coverage_rate=coverage_rate,
            executive_summary=executive_summary,
            matrix=matrix,
            findings=findings,
            swot=swot,
            recommendations=recommendations,
            citations=citations,
            agent_steps=[
                AnalysisAgentStep(
                    key="scope",
                    label="任务拆解",
                    agent="分析规划 Agent",
                    status="completed",
                    detail=f"确认 {len(payload.competitors)} 家竞品、{len(payload.dimensions)} 个维度与 {payload.range_key} 时间窗。",
                    evidence_count=0,
                ),
                AnalysisAgentStep(
                    key="retrieve",
                    label="知识检索",
                    agent="检索 Agent",
                    status="completed" if citations else "warning",
                    detail=f"完成权限过滤、词项扩展和相关性排序，召回 {len(citations)} 条唯一知识。",
                    evidence_count=len(citations),
                ),
                AnalysisAgentStep(
                    key="verify",
                    label="证据门禁",
                    agent="证据校验 Agent",
                    status="warning" if conflict_cells or missing_cells else "completed",
                    detail=f"识别 {len(conflict_cells)} 个冲突单元格与 {len(missing_cells)} 个证据空缺。",
                    evidence_count=len(citations),
                ),
                AnalysisAgentStep(
                    key="compare",
                    label="矩阵与 SWOT",
                    agent="竞品分析 Agent",
                    status="completed" if evidence_cells else "warning",
                    detail=f"形成 {len(matrix)} 个矩阵单元格和 {len(swot)} 组 SWOT，覆盖率 {coverage_rate}%。",
                    evidence_count=len(citations),
                ),
                AnalysisAgentStep(
                    key="recommend",
                    label="商业建议",
                    agent="策略 Agent",
                    status="completed" if recommendations else "warning",
                    detail=f"生成 {len(recommendations)} 条含对象、依据、影响、风险与验证方式的建议。",
                    evidence_count=sum(bool(item.citation_ids) for item in recommendations),
                ),
            ],
            notices=notices,
            created_at=created_at,
            completed_at=completed_at,
        )
        self.database.save_competitive_analysis(result.model_dump(), actor_id)
        return result
