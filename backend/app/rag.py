from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
import re
import unicodedata
from uuid import uuid4

from .database import Database
from .schemas import RAGCitation, RAGFilters, RAGQueryRequest, RAGResponse


TERM_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "治理": ("权限", "审计", "数据驻留", "管理员控制", "合规"),
    "价格": ("定价", "套餐", "调价"),
    "定价": ("价格", "套餐", "调价"),
    "能力": ("功能", "产品能力", "连接器", "工具调用"),
    "发布": ("上线", "新增", "版本", "更新"),
    "市场": ("地区", "进入", "退出", "渠道", "合作"),
    "风险": ("冲突", "待复核", "来源风险", "失效"),
    "agent": ("智能体", "工具调用", "自主执行"),
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


def tokenize(value: str) -> list[str]:
    normalized = _normalize(value)
    terms: list[str] = []
    terms.extend(re.findall(r"[a-z0-9][a-z0-9._+-]{1,}", normalized))
    for chunk in re.findall(r"[\u3400-\u9fff]+", normalized):
        if len(chunk) <= 8:
            terms.append(chunk)
        if len(chunk) == 1:
            terms.append(chunk)
        else:
            terms.extend(chunk[index : index + 2] for index in range(len(chunk) - 1))
    return list(dict.fromkeys(term for term in terms if term.strip()))


def expand_query(value: str) -> list[str]:
    normalized = _normalize(value)
    terms = tokenize(value)
    for trigger, additions in TERM_EXPANSIONS.items():
        if trigger in normalized:
            for addition in additions:
                terms.extend(tokenize(addition))
    return list(dict.fromkeys(terms))[:48]


@dataclass(slots=True)
class RetrievalHit:
    item: dict[str, object]
    score: float
    relevance: float = 0


class RAGEngine:
    """Authorization-filtered lexical RAG with extractive, citation-only generation."""

    def __init__(self, database: Database):
        self.database = database

    def retrieve(
        self,
        project_id: str,
        question: str,
        filters: RAGFilters,
        allowed_domains: list[str] | None = None,
    ) -> tuple[list[RetrievalHit], int, list[str]]:
        rows = self.database.list_rag_candidates(
            project_id,
            competitors=filters.competitors,
            item_types=filters.item_types,
            categories=filters.categories,
            review_statuses=filters.review_statuses,
            collection_id=filters.collection_id,
            start_date=filters.start_date,
            end_date=filters.end_date,
            include_at_risk=filters.include_at_risk,
            allowed_domains=allowed_domains,
        )
        items = [dict(row) for row in rows]
        query_terms = expand_query(question)
        if not items or not query_terms:
            return [], len(items), query_terms

        document_terms: list[set[str]] = []
        for item in items:
            combined = " ".join(
                str(item.get(field) or "")
                for field in (
                    "title",
                    "subject",
                    "category",
                    "tags_json",
                    "summary",
                    "content",
                    "evidence_excerpt",
                )
            )
            document_terms.append(set(tokenize(combined)))
        frequencies = Counter(
            term for terms in document_terms for term in set(query_terms).intersection(terms)
        )
        total_documents = len(items)
        field_weights = {
            "title": 4.4,
            "subject": 3.8,
            "category": 2.5,
            "tags_json": 2.4,
            "evidence_excerpt": 2.2,
            "summary": 1.9,
            "content": 1.2,
        }
        normalized_question = _normalize(question)
        hits: list[RetrievalHit] = []
        for item, all_terms in zip(items, document_terms, strict=True):
            field_term_sets = {
                field: set(tokenize(str(item.get(field) or "")))
                for field in field_weights
            }
            score = 0.0
            matched: set[str] = set()
            for term in query_terms:
                best_weight = max(
                    (weight for field, weight in field_weights.items() if term in field_term_sets[field]),
                    default=0.0,
                )
                if not best_weight:
                    continue
                matched.add(term)
                inverse_frequency = math.log(
                    1 + (total_documents + 1) / (frequencies.get(term, 0) + 1)
                )
                score += best_weight * inverse_frequency
            searchable = _normalize(
                " ".join(str(item.get(field) or "") for field in field_weights)
            )
            if normalized_question and normalized_question in searchable:
                score += 8.0
            if not matched or score <= 0:
                continue
            coverage = len(matched) / max(1, len(set(query_terms)))
            score *= 0.72 + min(0.28, coverage)
            score *= 0.72 + (int(item.get("confidence") or 0) / 100) * 0.28
            if item.get("review_status") == "verified":
                score *= 1.08
            elif item.get("review_status") == "conflict":
                score *= 0.94
            if item.get("validity_status") == "at_risk":
                score *= 0.82
            hits.append(RetrievalHit(item=item, score=score))

        hits.sort(
            key=lambda hit: (
                hit.score,
                int(hit.item.get("confidence") or 0),
                str(hit.item.get("published_at") or hit.item.get("updated_at") or ""),
            ),
            reverse=True,
        )
        hits = hits[: filters.top_k]
        if hits:
            maximum = hits[0].score
            for hit in hits:
                hit.relevance = round(min(1.0, 0.2 + 0.8 * hit.score / maximum), 4)
        return hits, len(items), query_terms

    @staticmethod
    def citation_from_hit(hit: RetrievalHit, citation_id: int) -> RAGCitation:
        item = hit.item
        return RAGCitation(
            id=citation_id,
            item_id=str(item["id"]),
            title=str(item["title"]),
            subject=str(item.get("subject") or "未归属主体"),
            item_type=str(item["item_type"]),
            category=str(item["category"]),
            summary=str(item["summary"]),
            evidence_excerpt=str(item["evidence_excerpt"]),
            source_name=str(item.get("source_name") or "内部知识库"),
            source_url=str(item.get("source_url") or ""),
            published_at=(str(item["published_at"]) if item.get("published_at") else None),
            confidence=int(item.get("confidence") or 0),
            relevance=hit.relevance,
            review_status=str(item["review_status"]),
            validity_status=str(item["validity_status"]),
        )

    def answer(self, payload: RAGQueryRequest, actor_id: str) -> RAGResponse:
        created_at = utc_now()
        query_id = f"rag_{uuid4().hex[:16]}"
        access = self.database.get_user_access(actor_id)
        allowed_domains = list(access["data_domains"]) if access is not None else []
        hits, candidate_count, query_terms = self.retrieve(
            payload.project_id,
            payload.question.strip(),
            payload.filters,
            allowed_domains,
        )
        citations = [
            self.citation_from_hit(hit, index)
            for index, hit in enumerate(hits, start=1)
        ]
        notices = ["回答仅使用当前项目内已授权且未过期的证据，不补写检索范围外的事实。"]
        if not citations:
            answer_type = "insufficient"
            confidence = 0
            answer = (
                "当前权限与筛选范围内没有检索到足以回答该问题的可信证据。"
                "请扩大时间范围、减少筛选条件或先补充数据源；系统不会用空值推断竞品优劣。"
            )
            notices.append("未命中证据，已触发拒答。")
            data_cutoff = "暂无可信数据"
        else:
            answer_type = "grounded"
            conflict_count = sum(item.review_status == "conflict" for item in citations)
            risk_count = sum(item.validity_status == "at_risk" for item in citations)
            confidence = round(
                sum(item.confidence * item.relevance for item in citations)
                / max(0.001, sum(item.relevance for item in citations))
            )
            if conflict_count:
                confidence = max(0, confidence - min(12, conflict_count * 6))
                notices.append(f"{conflict_count} 条证据存在来源冲突，答案中保留冲突状态。")
            if risk_count:
                confidence = max(0, confidence - min(10, risk_count * 5))
                notices.append(f"{risk_count} 条证据存在新鲜度或来源风险，建议复核后再决策。")
            lines = [
                f"在当前项目的授权证据范围内，共检索到 {len(citations)} 条高相关材料："
            ]
            labels = {"fact": "事实", "event": "事实", "entity": "事实", "insight": "推断"}
            for citation in citations[:5]:
                lines.append(
                    f"- [{labels[citation.item_type]}] {citation.subject}：{citation.summary} [{citation.id}]"
                )
            if all(item.item_type == "insight" for item in citations):
                lines.append("当前结果均为推断性知识，缺少直接事实材料，建议补充一手来源后再形成结论。")
            answer = "\n".join(lines)
            data_cutoff = max(
                (item.published_at or created_at for item in citations),
                default=created_at,
            )

        trace = {
            "query_terms": query_terms,
            "candidate_count": candidate_count,
            "retrieved_count": len(citations),
            "generation_mode": "extractive_grounded",
            "stages": [
                {
                    "key": "scope",
                    "label": "权限与范围过滤",
                    "status": "completed",
                    "detail": f"限定项目、授权状态、有效期及 {len(payload.filters.competitors) or '全部'} 个竞品范围。",
                },
                {
                    "key": "retrieve",
                    "label": "混合词项检索",
                    "status": "completed" if citations else "warning",
                    "detail": f"从 {candidate_count} 条候选知识中召回 {len(citations)} 条，并按字段权重、置信度和复核状态排序。",
                },
                {
                    "key": "ground",
                    "label": "证据约束生成",
                    "status": "completed" if citations else "warning",
                    "detail": "仅抽取候选知识中的原有表述，事实、推断和风险状态分别标注。",
                },
            ],
        }
        response = RAGResponse(
            id=query_id,
            project_id=payload.project_id,
            question=payload.question.strip(),
            answer=answer,
            answer_type=answer_type,
            confidence=confidence,
            data_cutoff=data_cutoff,
            citations=citations,
            trace=trace,
            notices=notices,
            created_at=created_at,
        )
        self.database.log_rag_query(
            query_id,
            payload.project_id,
            payload.question.strip(),
            payload.filters.model_dump(),
            [item.item_id for item in citations],
            answer_type,
            confidence,
            json.loads(response.trace.model_dump_json()),
            actor_id,
            created_at,
        )
        return response
