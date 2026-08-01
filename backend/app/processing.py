from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from bs4 import BeautifulSoup

from .config import Settings
from .database import Database


PROCESSOR_VERSION = "processing-1.0.0"
IMAGE_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/tiff": ".tiff",
    "image/bmp": ".bmp",
}
DEFAULT_OPTIONS = {
    "extract_body": True,
    "denoise": True,
    "deduplicate": True,
    "detect_language": True,
    "ocr": True,
    "extract_entities": True,
    "extract_events": True,
}

BOILERPLATE_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"^(首页|关于我们|联系我们|返回顶部|网站地图|隐私政策|使用条款)$",
        r"^(home|about us|contact us|back to top|privacy policy|terms of use)$",
        r"^(登录|注册|订阅|分享|打印|收藏|下载客户端)(\s*[|·/]\s*.*)?$",
        r"^(sign in|sign up|subscribe|share|print|download)(\s*[|·/]\s*.*)?$",
        r"^(cookie|cookies).{0,80}(同意|接受|accept|agree)",
        r"^(版权所有|copyright\s*©?|©)\s*\d{0,4}",
        r"^(上一篇|下一篇|相关阅读|相关推荐|热门文章)[:：]?.*$",
    )
)

ENTITY_LABELS = {
    "company": "企业",
    "brand": "品牌",
    "product": "产品",
    "person": "人物",
    "version": "版本",
    "price": "价格",
    "location": "地点",
    "date": "日期",
    "feature": "功能",
}

EVENT_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("price_increase", "价格上调", "high", r"涨价|价格上调|提价|上调.{0,8}价格|price increase|raise[sd]? prices?"),
    ("price_decrease", "价格下调", "medium", r"降价|价格下调|下调.{0,8}价格|优惠|折扣|price cut|lower(?:ed)? prices?"),
    ("acquisition", "收购并购", "high", r"收购|并购|被.{0,6}收购|acquir(?:e|ed|es|ing)|merger"),
    ("funding", "融资动态", "high", r"融资|募资|投资.{0,8}(轮|亿美元|万元)|funding|raised? .{0,20}(million|billion)"),
    ("partnership", "合作签约", "medium", r"合作|签署.{0,8}协议|战略伙伴|达成.{0,8}伙伴|partnership|partnered|collaboration"),
    ("market_exit", "市场退出", "high", r"退出.{0,8}市场|停止运营|停服|关闭.{0,8}业务|exit(?:ed|s)? the market|shut down"),
    ("market_entry", "市场进入", "medium", r"进入.{0,8}市场|进军|拓展至|正式登陆|enter(?:ed|s)? the market|expand(?:ed|s)? into"),
    ("feature_remove", "功能移除", "medium", r"移除.{0,12}功能|取消.{0,12}功能|下线|停止支持|remove(?:d|s)?|deprecated?"),
    ("feature_add", "功能新增", "medium", r"新增|新功能|支持.{0,12}(功能|模式|语言)|集成|feature update|adds? support"),
    ("hiring", "招聘扩张", "low", r"招聘|扩招|新增.{0,6}岗位|hiring|recruit(?:ing|ment)"),
    ("release", "产品发布", "medium", r"发布|推出|上线|更新至|正式开放|launch(?:ed|es)?|release(?:d|s)?|unveil(?:ed|s)?"),
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _decode_bytes(content: bytes, content_type: str = "") -> str:
    charset = re.search(r"charset=([\w.-]+)", content_type, re.I)
    candidates = [charset.group(1)] if charset else []
    candidates.extend(["utf-8-sig", "utf-8", "gb18030"])
    for encoding in candidates:
        try:
            return content.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")


def _clean_line(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]", "", value)
    return re.sub(r"[ \t\f\v]+", " ", value).strip()


def _json_list(value: Any) -> list[Any]:
    if not value:
        return []
    try:
        result = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return result if isinstance(result, list) else []


class DocumentProcessor:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings

    def process_document(
        self, document_id: str, options: dict[str, bool] | None = None
    ) -> Any:
        document = self.database.mark_document_processing(document_id)
        if document is None:
            return None
        selected = {**DEFAULT_OPTIONS, **(options or {})}
        try:
            result = self._process(document, selected)
            return self.database.save_document_processing(
                document_id, document["project_id"], result
            )
        except Exception as exc:  # Processing failures must remain visible and retryable.
            return self.database.fail_document_processing(
                document_id,
                document["project_id"],
                f"{type(exc).__name__}: {exc}",
            )

    def process_project(
        self,
        project_id: str,
        document_ids: list[str] | None = None,
        options: dict[str, bool] | None = None,
    ) -> list[Any]:
        if document_ids:
            rows = [self.database.get_collection_document(item) for item in document_ids]
            targets = [
                row
                for row in rows
                if row is not None and row["project_id"] == project_id
            ]
        else:
            targets = self.database.list_collection_documents(
                project_id, latest_only=True, limit=100
            )
        results = []
        for document in targets:
            result = self.process_document(document["id"], options)
            if result is not None:
                results.append(result)
        return results

    def _process(self, document: Any, options: dict[str, bool]) -> dict[str, object]:
        steps: list[dict[str, object]] = []
        raw = bytes(document["raw_content"] or b"")
        original = str(document["readable_text"] or "")

        body, extraction_method = self._timed_step(
            steps,
            "body",
            "正文提取",
            lambda: self._extract_body(document, raw)
            if options["extract_body"]
            else (original, "existing_readable_text"),
            lambda value: f"使用 {value[1]} 提取 {len(value[0])} 个字符",
            skipped=not options["extract_body"],
        )

        needs_ocr = self._needs_ocr(document["content_type"], body)
        ocr_status = "not_required"
        ocr_text = ""
        if needs_ocr and options["ocr"]:
            started = time.perf_counter()
            ocr_status, ocr_text, ocr_message = self._run_ocr(
                raw, document["content_type"]
            )
            steps.append(
                self._step(
                    "ocr",
                    "OCR 识别",
                    "completed" if ocr_status == "completed" else "warning",
                    started,
                    ocr_message,
                )
            )
            if ocr_text:
                body = ocr_text
                extraction_method = f"{extraction_method}+ocr"
        elif needs_ocr:
            ocr_status = "unavailable"
            steps.append(
                {
                    "key": "ocr",
                    "label": "OCR 识别",
                    "status": "skipped",
                    "duration_ms": 0,
                    "summary": "本次处理未启用 OCR",
                }
            )
        else:
            steps.append(
                {
                    "key": "ocr",
                    "label": "OCR 识别",
                    "status": "skipped",
                    "duration_ms": 0,
                    "summary": "当前材料包含可读文本，无需 OCR",
                }
            )

        clean_text, removed_lines = self._timed_step(
            steps,
            "denoise",
            "内容去噪",
            lambda: self._denoise(body) if options["denoise"] else (_clean_line(body), 0),
            lambda value: f"移除 {value[1]} 行导航、版权或重复噪声，保留 {len(value[0])} 个字符",
            skipped=not options["denoise"],
        )
        clean_hash = (
            hashlib.sha256(clean_text.casefold().encode("utf-8")).hexdigest()
            if clean_text
            else None
        )

        language, language_confidence = self._timed_step(
            steps,
            "language",
            "语言识别",
            lambda: self._detect_language(clean_text)
            if options["detect_language"]
            else (document["language"] or None, 0.5 if document["language"] else 0.0),
            lambda value: f"识别为 {value[0] or 'und'}，置信度 {value[1]:.0%}",
            skipped=not options["detect_language"],
        )

        duplicate = self._timed_step(
            steps,
            "deduplicate",
            "跨来源去重",
            lambda: self._find_duplicate(document, clean_text, clean_hash)
            if options["deduplicate"]
            else self._no_duplicate(document, clean_hash),
            lambda value: (
                f"命中{('精确' if value['type'] == 'exact' else '近似')}重复，"
                f"相似度 {value['similarity']:.0%}"
                if value["type"] != "none"
                else "未发现跨来源重复材料"
            ),
            skipped=not options["deduplicate"],
        )

        entities = self._timed_step(
            steps,
            "entities",
            "实体抽取",
            lambda: self._extract_entities(clean_text)
            if options["extract_entities"]
            else [],
            lambda value: f"抽取 {len(value)} 个带原文位置的实体",
            skipped=not options["extract_entities"],
        )
        events = self._timed_step(
            steps,
            "events",
            "事件抽取",
            lambda: self._extract_events(clean_text, entities)
            if options["extract_events"]
            else [],
            lambda value: f"识别 {len(value)} 个变化事件",
            skipped=not options["extract_events"],
        )

        quality_score, review_reasons = self._quality_gate(
            clean_text,
            language,
            language_confidence,
            needs_ocr,
            ocr_status,
            entities,
            events,
        )
        steps.append(
            {
                "key": "quality",
                "label": "质量门禁",
                "status": "warning" if review_reasons else "completed",
                "duration_ms": 0,
                "summary": (
                    f"质量分 {quality_score}，需人工复核：{'；'.join(review_reasons)}"
                    if review_reasons
                    else f"质量分 {quality_score}，自动通过"
                ),
            }
        )
        return {
            "status": "review_required" if review_reasons else "completed",
            "clean_text": clean_text,
            "clean_hash": clean_hash,
            "body_extraction_method": extraction_method,
            "noise_removed_lines": removed_lines,
            "language": language,
            "language_confidence": language_confidence,
            "ocr_status": ocr_status,
            "ocr_text": ocr_text,
            "duplicate_type": duplicate["type"],
            "duplicate_of": duplicate["document_id"],
            "duplicate_similarity": duplicate["similarity"],
            "duplicate_cluster_id": duplicate["cluster_id"],
            "entities": entities,
            "events": events,
            "steps": steps,
            "quality_score": quality_score,
            "needs_review": bool(review_reasons),
            "review_reasons": review_reasons,
            "processor_version": PROCESSOR_VERSION,
            "processed_at": _utc_now(),
            "error_message": None,
        }

    @staticmethod
    def _step(
        key: str, label: str, status: str, started: float, summary: str
    ) -> dict[str, object]:
        return {
            "key": key,
            "label": label,
            "status": status,
            "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
            "summary": summary,
        }

    def _timed_step(
        self,
        steps: list[dict[str, object]],
        key: str,
        label: str,
        operation: Callable[[], Any],
        summarize: Callable[[Any], str],
        *,
        skipped: bool = False,
    ) -> Any:
        started = time.perf_counter()
        value = operation()
        steps.append(
            self._step(
                key,
                label,
                "skipped" if skipped else "completed",
                started,
                summarize(value),
            )
        )
        return value

    @staticmethod
    def _extract_body(document: Any, raw: bytes) -> tuple[str, str]:
        content_type = str(document["content_type"] or "").lower()
        existing = str(document["readable_text"] or "")
        if "html" not in content_type:
            return existing, "collector_readable_text"
        soup = BeautifulSoup(_decode_bytes(raw, content_type), "html.parser")
        for node in soup.select(
            "script,style,noscript,template,svg,canvas,nav,header,footer,aside,form,"
            "[role=navigation],[role=banner],[role=contentinfo],"
            ".nav,.navbar,.menu,.footer,.header,.sidebar,.advertisement,.ads,.cookie"
        ):
            node.decompose()
        candidates = [
            soup.select_one("article"),
            soup.select_one("main"),
            soup.select_one("[role=main]"),
            soup.select_one(".article-content"),
            soup.select_one(".post-content"),
            soup.select_one(".entry-content"),
            soup.body,
        ]
        scored = [
            (len(node.get_text("\n", strip=True)), node)
            for node in candidates
            if node is not None
        ]
        target = max(scored, key=lambda item: item[0])[1] if scored else soup
        return target.get_text("\n", strip=True), "html_semantic_density"

    @staticmethod
    def _needs_ocr(content_type: str, body: str) -> bool:
        normalized = (content_type or "").split(";", 1)[0].lower()
        return normalized in IMAGE_CONTENT_TYPES or (
            normalized == "application/pdf" and len(body.strip()) < 40
        )

    def _run_ocr(self, raw: bytes, content_type: str) -> tuple[str, str, str]:
        if not self.settings.ocr_enabled:
            return "unavailable", "", "OCR 服务已由环境配置关闭"
        command = shutil.which(self.settings.ocr_command)
        if command is None and Path(self.settings.ocr_command).is_file():
            command = str(Path(self.settings.ocr_command).resolve())
        if command is None:
            return (
                "unavailable",
                "",
                "未检测到 Tesseract OCR 引擎，材料已进入人工复核",
            )
        normalized = (content_type or "").split(";", 1)[0].lower()
        with tempfile.TemporaryDirectory(prefix="jinguan-ocr-") as directory:
            temp_root = Path(directory)
            images: list[Path]
            if normalized == "application/pdf":
                converter = shutil.which("pdftoppm")
                if converter is None:
                    return (
                        "unavailable",
                        "",
                        "扫描 PDF 需要 pdftoppm 转图，当前环境未安装",
                    )
                pdf_path = temp_root / "input.pdf"
                pdf_path.write_bytes(raw)
                prefix = temp_root / "page"
                converted = subprocess.run(
                    [converter, "-png", "-r", "180", str(pdf_path), str(prefix)],
                    capture_output=True,
                    text=True,
                    timeout=self.settings.ocr_timeout_seconds,
                    check=False,
                )
                if converted.returncode != 0:
                    message = (converted.stderr or converted.stdout).strip()[:300]
                    return "failed", "", f"扫描 PDF 转图失败：{message or '未知错误'}"
                images = sorted(temp_root.glob("page-*.png"))[:20]
            else:
                suffix = IMAGE_CONTENT_TYPES.get(normalized, ".img")
                image_path = temp_root / f"input{suffix}"
                image_path.write_bytes(raw)
                images = [image_path]
            if not images:
                return "failed", "", "OCR 未生成可识别的页面图像"
            output: list[str] = []
            for image in images:
                completed = subprocess.run(
                    [
                        command,
                        str(image),
                        "stdout",
                        "-l",
                        self.settings.ocr_languages,
                        "--psm",
                        "6",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.settings.ocr_timeout_seconds,
                    check=False,
                )
                if completed.returncode != 0:
                    message = (completed.stderr or completed.stdout).strip()[:300]
                    return "failed", "", f"OCR 引擎执行失败：{message or '未知错误'}"
                if completed.stdout.strip():
                    output.append(completed.stdout.strip())
            text = "\n".join(output).strip()
            if not text:
                return "failed", "", "OCR 已运行，但未识别到文字"
            return "completed", text, f"OCR 完成，识别 {len(text)} 个字符"

    @staticmethod
    def _denoise(text: str) -> tuple[str, int]:
        kept: list[str] = []
        seen: set[str] = set()
        removed = 0
        for raw_line in text.splitlines() or [text]:
            line = _clean_line(raw_line)
            if not line:
                continue
            key = line.casefold()
            if key in seen or any(pattern.search(line) for pattern in BOILERPLATE_PATTERNS):
                removed += 1
                continue
            if len(line) <= 2 and not re.search(r"[。！？!?]", line):
                removed += 1
                continue
            seen.add(key)
            kept.append(line)
        return "\n".join(kept).strip(), removed

    @staticmethod
    def _detect_language(text: str) -> tuple[str | None, float]:
        sample = text[:10000]
        counts = {
            "zh": len(re.findall(r"[\u4e00-\u9fff]", sample)),
            "ja": len(re.findall(r"[\u3040-\u30ff]", sample)),
            "ko": len(re.findall(r"[\uac00-\ud7af]", sample)),
            "en": len(re.findall(r"[A-Za-z]", sample)),
        }
        significant = sum(counts.values())
        if significant < 4:
            return None, 0.0
        if counts["ja"]:
            counts["ja"] += counts["zh"]
        language, best = max(counts.items(), key=lambda item: item[1])
        confidence = min(0.99, max(0.5, best / max(1, significant)))
        return language, round(confidence, 3)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        normalized = text.casefold()
        tokens = set(re.findall(r"[a-z0-9]+(?:[.+_-][a-z0-9]+)*", normalized))
        for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
            tokens.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
        return tokens

    @classmethod
    def _similarity(cls, left: str, right: str) -> float:
        left_tokens = cls._tokens(left)
        right_tokens = cls._tokens(right)
        if not left_tokens or not right_tokens:
            return 0.0
        overlap = len(left_tokens & right_tokens)
        jaccard = overlap / len(left_tokens | right_tokens)
        containment = overlap / min(len(left_tokens), len(right_tokens))
        return round(jaccard * 0.65 + containment * 0.35, 4)

    @staticmethod
    def _no_duplicate(document: Any, clean_hash: str | None) -> dict[str, object]:
        return {
            "type": "none",
            "document_id": None,
            "similarity": 0.0,
            "cluster_id": f"cluster_{(clean_hash or document['id'])[:12]}",
        }

    def _find_duplicate(
        self, document: Any, clean_text: str, clean_hash: str | None
    ) -> dict[str, object]:
        fallback = self._no_duplicate(document, clean_hash)
        if not clean_text or not clean_hash:
            return fallback
        best: Any | None = None
        best_similarity = 0.0
        for candidate in self.database.list_processing_candidates(
            document["project_id"], document["id"]
        ):
            if candidate["clean_hash"] == clean_hash:
                best = candidate
                best_similarity = 1.0
                break
            similarity = self._similarity(clean_text, candidate["clean_text"])
            if similarity > best_similarity:
                best = candidate
                best_similarity = similarity
        if best is None or best_similarity < self.settings.near_duplicate_threshold:
            return fallback
        return {
            "type": "exact" if best_similarity == 1 else "near",
            "document_id": best["document_id"],
            "similarity": best_similarity,
            "cluster_id": best["duplicate_cluster_id"]
            or f"cluster_{(best['clean_hash'] or best['document_id'])[:12]}",
        }

    @staticmethod
    def _extract_entities(text: str) -> list[dict[str, object]]:
        entities: list[dict[str, object]] = []
        seen: set[tuple[str, int, int]] = set()

        def add(kind: str, value: str, start: int, end: int, confidence: float, method: str) -> None:
            value = value.strip(" \t\n，。；;、:：()（）[]【】\"'“”")
            if len(value) < 2 or (kind, start, end) in seen:
                return
            seen.add((kind, start, end))
            normalized = value.casefold()
            if kind == "price":
                normalized = re.sub(r"\s+", "", value).replace("￥", "¥")
            entities.append(
                {
                    "id": f"ent_{len(entities) + 1:04d}",
                    "type": kind,
                    "text": value,
                    "normalized": normalized,
                    "start": max(0, start),
                    "end": max(start, end),
                    "confidence": round(confidence, 2),
                    "method": method,
                }
            )

        patterns: tuple[tuple[str, str, float, int], ...] = (
            ("company", r"(?<![\u4e00-\u9fffA-Za-z0-9])([\u4e00-\u9fffA-Za-z0-9·]{2,24}(?:股份有限公司|有限责任公司|有限公司|集团|公司))", 0.9, 1),
            ("company", r"\b([A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,4}\s+(?:Inc\.?|Corp\.?|Corporation|Ltd\.?|LLC|Group))\b", 0.88, 1),
            ("person", r"([\u4e00-\u9fff]{2,4})(?=.{0,6}(?:创始人|联合创始人|首席执行官|CEO|总裁|董事长))", 0.82, 1),
            ("version", r"(?i)(?<![A-Za-z0-9])((?:v(?:ersion)?\s*)?\d+(?:\.\d+){1,3}(?:[-_][A-Za-z0-9.]+)?)", 0.94, 1),
            ("price", r"((?:US\$|HK\$|[$¥￥€£])\s?\d[\d,]*(?:\.\d+)?(?:\s*(?:元|美元|港元|欧元|/月|/年|per month|monthly|annually))?|\d[\d,]*(?:\.\d+)?\s*(?:元|美元|港元|欧元)(?:/月|/年)?)", 0.92, 1),
            ("date", r"((?:20\d{2})[年./-](?:0?[1-9]|1[0-2])[月./-](?:0?[1-9]|[12]\d|3[01])日?|(?:0?[1-9]|1[0-2])月(?:0?[1-9]|[12]\d|3[01])日|\b20\d{2}-\d{2}-\d{2}\b)", 0.9, 1),
            ("product", r"(?:产品|平台|应用|服务)[“\"]?([A-Za-z][A-Za-z0-9+._ -]{1,30})[”\"]?", 0.72, 1),
            ("feature", r"(?:新增|推出|上线|支持|集成)([\u4e00-\u9fffA-Za-z0-9+· _-]{2,24})(?=[，。；,;])", 0.72, 1),
        )
        for kind, pattern, confidence, group in patterns:
            for match in re.finditer(pattern, text):
                add(
                    kind,
                    match.group(group),
                    match.start(group),
                    match.end(group),
                    confidence,
                    "rule_regex_v1",
                )

        for location in (
            "中国", "美国", "日本", "欧洲", "英国", "德国", "法国", "新加坡",
            "东南亚", "香港", "北京", "上海", "深圳", "广州", "杭州", "硅谷",
        ):
            for match in re.finditer(re.escape(location), text):
                add("location", location, match.start(), match.end(), 0.86, "gazetteer_v1")

        company_names = (
            "OpenAI", "Google", "Microsoft", "Anthropic", "Meta", "Amazon",
            "Apple", "Salesforce", "Adobe", "Oracle", "Atlassian", "Zoom",
            "Notion", "Slack", "Perplexity",
        )
        product_names = (
            "ChatGPT", "Google Workspace", "Google Meet", "Google Drive",
            "Google Sheets", "Google Classroom", "Gemini", "Microsoft Copilot",
            "Microsoft Teams", "Claude", "Salesforce Einstein", "Adobe Firefly",
            "Amazon Bedrock", "AWS", "Azure", "Zoom", "Notion",
        )
        for company_name in company_names:
            for match in re.finditer(rf"(?i)(?<![A-Za-z0-9]){re.escape(company_name)}(?![A-Za-z0-9])", text):
                add(
                    "company",
                    match.group(0),
                    match.start(),
                    match.end(),
                    0.9,
                    "competitor_gazetteer_v1",
                )
        for product_name in product_names:
            for match in re.finditer(rf"(?i)(?<![A-Za-z0-9]){re.escape(product_name)}(?![A-Za-z0-9])", text):
                add(
                    "product",
                    match.group(0),
                    match.start(),
                    match.end(),
                    0.9,
                    "product_gazetteer_v1",
                )

        companies = [item for item in entities if item["type"] == "company"]
        for company in companies:
            brand = re.sub(
                r"(?:股份有限公司|有限责任公司|有限公司|集团|公司|Corporation|Corp\.?|Inc\.?|Ltd\.?|LLC|Group)$",
                "",
                str(company["text"]),
                flags=re.I,
            ).strip()
            if len(brand) >= 2 and brand != company["text"]:
                add(
                    "brand",
                    brand,
                    int(company["start"]),
                    int(company["start"]) + len(brand),
                    0.76,
                    "company_alias_v1",
                )
        entities.sort(key=lambda item: (int(item["start"]), int(item["end"]), str(item["type"])))
        for index, item in enumerate(entities, start=1):
            item["id"] = f"ent_{index:04d}"
        return entities[:300]

    @staticmethod
    def _extract_events(
        text: str, entities: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        sentence_start = 0
        for boundary in re.finditer(r"[^。！？!?\n]+[。！？!?]?", text):
            sentence = boundary.group(0).strip()
            if not sentence:
                continue
            sentence_start = boundary.start()
            for event_type, label, impact, pattern in EVENT_RULES:
                trigger = re.search(pattern, sentence, re.I)
                if trigger is None:
                    continue
                absolute_start = sentence_start + trigger.start()
                sentence_end = sentence_start + len(sentence)
                nearby = [
                    item
                    for item in entities
                    if int(item["start"]) < sentence_end
                    and int(item["end"]) > sentence_start
                ]
                subject_candidates = [
                    item
                    for item in nearby
                    if item["type"] in {"company", "brand", "product", "person"}
                    and int(item["start"]) <= absolute_start
                ]
                subject = (
                    str(max(subject_candidates, key=lambda item: int(item["start"]))["text"])
                    if subject_candidates
                    else None
                )
                object_candidates = [
                    item
                    for item in nearby
                    if item["type"] in {"product", "company", "brand", "feature", "price", "location"}
                    and int(item["start"]) > absolute_start
                ]
                event_object = (
                    str(min(object_candidates, key=lambda item: int(item["start"]))["text"])
                    if object_candidates
                    else None
                )
                dates = [item for item in nearby if item["type"] == "date"]
                occurred_at = str(dates[0]["normalized"]) if dates else None
                confidence = 0.68 + (0.1 if subject else 0) + (0.08 if event_object else 0) + (0.06 if occurred_at else 0)
                events.append(
                    {
                        "id": f"evt_{len(events) + 1:04d}",
                        "type": event_type,
                        "label": label,
                        "subject": subject,
                        "object": event_object,
                        "occurred_at": occurred_at,
                        "impact_level": impact,
                        "confidence": round(min(0.96, confidence), 2),
                        "evidence_text": sentence[:500],
                        "start": sentence_start,
                        "end": sentence_end,
                        "method": "trigger_rule_v1",
                    }
                )
                break
        return events[:100]

    @staticmethod
    def _quality_gate(
        clean_text: str,
        language: str | None,
        language_confidence: float,
        needs_ocr: bool,
        ocr_status: str,
        entities: list[dict[str, object]],
        events: list[dict[str, object]],
    ) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        if len(clean_text) >= 80:
            score += 30
        elif len(clean_text) >= 20:
            score += 20
        else:
            reasons.append("正文内容过短或未成功提取")
        if language and language_confidence >= 0.55:
            score += 15
        else:
            reasons.append("语言识别置信度不足")
        if not needs_ocr or ocr_status == "completed":
            score += 15
        else:
            reasons.append("OCR 未完成")
        score += 10  # 去重步骤可审计完成，不以是否重复惩罚材料质量。
        if entities:
            score += 15
        if events:
            score += 15
        elif len(clean_text) >= 120:
            score += 8
        low_confidence = [
            item
            for item in [*entities, *events]
            if float(item.get("confidence", 0)) < 0.6
        ]
        if low_confidence:
            reasons.append("存在低置信度抽取结果")
        score = min(100, score)
        if score < 65 and "质量分低于自动通过阈值" not in reasons:
            reasons.append("质量分低于自动通过阈值")
        return score, list(dict.fromkeys(reasons))


def processing_summary_from_row(row: Any) -> dict[str, object]:
    entities = _json_list(row["entities_json"])
    events = _json_list(row["events_json"])
    clean_hash = row["clean_hash"]
    cluster_id = row["duplicate_cluster_id"] or f"cluster_{(clean_hash or row['id'])[:12]}"
    return {
        "document_id": row["id"],
        "project_id": row["project_id"],
        "source_id": row["source_id"],
        "source_name": row["source_name"],
        "title": row["title"],
        "collected_at": row["collected_at"],
        "content_type": row["content_type"],
        "status": row["processing_status"] or "pending",
        "quality_score": int(row["quality_score"] or 0),
        "language": row["detected_language"] or row["language"],
        "language_confidence": float(row["language_confidence"] or 0),
        "ocr_status": row["ocr_status"] or "not_required",
        "duplicate": {
            "type": row["duplicate_type"] or "none",
            "document_id": row["duplicate_of"],
            "title": row["duplicate_title"],
            "source_name": row["duplicate_source_name"],
            "similarity": float(row["duplicate_similarity"] or 0),
            "cluster_id": cluster_id,
        },
        "entity_count": len(entities),
        "event_count": len(events),
        "noise_removed_lines": int(row["noise_removed_lines"] or 0),
        "needs_review": bool(row["needs_review"]),
        "review_reasons": _json_list(row["review_reasons_json"]),
        "processed_at": row["processed_at"],
    }


def processing_detail_from_row(row: Any) -> dict[str, object]:
    summary = processing_summary_from_row(row)
    summary.update(
        {
            "original_excerpt": str(row["readable_text"] or "")[:1000],
            "clean_text": row["clean_text"] or "",
            "body_extraction_method": row["body_extraction_method"] or "pending",
            "entities": _json_list(row["entities_json"]),
            "events": _json_list(row["events_json"]),
            "steps": _json_list(row["steps_json"]),
            "processor_version": row["processor_version"] or PROCESSOR_VERSION,
            "error_message": row["error_message"],
        }
    )
    return summary
