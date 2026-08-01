from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from textwrap import wrap
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


def report_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        report["title"],
        f"版本 V{report['version']} | 数据截止 {report.get('data_cutoff') or '生成中'}",
        (
            f"证据 {report['evidence_count']} 条 | 来源 {report['source_count']} 个 | "
            f"置信度 {report['confidence']}%"
        ),
        "",
    ]
    for heading, value in report.get("sections", {}).items():
        lines.append(str(heading))
        _append_value(lines, value)
        lines.append("")
    if not report.get("sections"):
        lines.append("报告仍在生成，暂无可导出的正文。")
    lines.extend(
        [
            "来源说明",
            "本文件由镜观竞品分析系统生成。事实型结论应结合在线证据链核验；推断与建议不构成专业意见。",
        ]
    )
    return lines


def _append_value(lines: list[str], value: Any, depth: int = 0) -> None:
    prefix = "  " * depth
    if isinstance(value, str):
        lines.append(f"{prefix}{value}")
    elif isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(nested, (dict, list)):
                lines.append(f"{prefix}{key}：")
                _append_value(lines, nested, depth + 1)
            else:
                lines.append(f"{prefix}{key}：{nested}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                label = item.get("title") or item.get("action") or item.get("label") or "记录"
                lines.append(f"{prefix}• {label}")
                for key, nested in item.items():
                    if key in {"title", "action", "label"}:
                        continue
                    lines.append(f"{prefix}  {key}：{nested}")
            else:
                lines.append(f"{prefix}• {item}")
    else:
        lines.append(f"{prefix}{value}")


def build_docx(report: dict[str, Any]) -> bytes:
    lines = report_lines(report)
    paragraphs: list[str] = []
    section_names = set(report.get("sections", {}).keys()) | {"来源说明"}
    for index, line in enumerate(lines):
        style = "Title" if index == 0 else "Heading1" if line in section_names else "Normal"
        if not line:
            paragraphs.append("<w:p/>")
            continue
        paragraphs.append(
            f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
            f'<w:r><w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>'
        )
    document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{''.join(paragraphs)}
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>
  </w:body>
</w:document>'''
    styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Microsoft YaHei"/><w:sz w:val="21"/></w:rPr><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:color w:val="263028"/><w:sz w:val="36"/></w:rPr><w:pPr><w:spacing w:after="240"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:outlineLvl w:val="0"/><w:rPr><w:b/><w:color w:val="687C67"/><w:sz w:val="26"/></w:rPr><w:pPr><w:keepNext/><w:spacing w:before="260" w:after="120"/></w:pPr></w:style>
</w:styles>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
    document_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", styles_xml)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
    return output.getvalue()


def build_pdf(report: dict[str, Any]) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            KeepTogether,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        return _build_pdf_fallback(report)

    font_name = "JinguanCJK"
    bold_name = "JinguanCJK-Bold"
    regular_candidates = (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    )
    bold_candidates = (
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    )
    try:
        regular_path = next(path for path in regular_candidates if path.exists())
        bold_path = next((path for path in bold_candidates if path.exists()), regular_path)
        pdfmetrics.registerFont(TTFont(font_name, str(regular_path), subfontIndex=0))
        pdfmetrics.registerFont(TTFont(bold_name, str(bold_path), subfontIndex=0))
    except (StopIteration, ValueError, OSError):
        font_name = "STSong-Light"
        bold_name = font_name
        if font_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(font_name))

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=22 * mm,
        bottomMargin=19 * mm,
        title=str(report["title"]),
        author="镜观竞品分析系统",
        subject="证据化竞品分析报告",
        pageCompression=1,
    )
    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "JinguanTitle",
        parent=base_styles["Title"],
        fontName=bold_name,
        fontSize=20,
        leading=28,
        textColor=colors.HexColor("#263028"),
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    meta_style = ParagraphStyle(
        "JinguanMeta",
        parent=base_styles["Normal"],
        fontName=font_name,
        fontSize=8.5,
        leading=13,
        textColor=colors.HexColor("#7F857D"),
        alignment=TA_CENTER,
    )
    heading_style = ParagraphStyle(
        "JinguanHeading",
        parent=base_styles["Heading1"],
        fontName=bold_name,
        fontSize=13,
        leading=19,
        textColor=colors.HexColor("#526650"),
        spaceBefore=12,
        spaceAfter=7,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "JinguanBody",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=9.5,
        leading=16,
        textColor=colors.HexColor("#555E55"),
        spaceAfter=6,
        wordWrap="CJK",
    )
    detail_style = ParagraphStyle(
        "JinguanDetail",
        parent=body_style,
        fontSize=8.5,
        leading=14,
        leftIndent=7 * mm,
        textColor=colors.HexColor("#727970"),
    )
    story: list[Any] = [
        Paragraph(escape(str(report["title"])), title_style),
        Paragraph(
            escape(
                f"版本 V{report['version']}  ·  数据截止 {report.get('data_cutoff') or '生成中'}  ·  "
                f"读者 {report.get('audience', 'analyst')}"
            ),
            meta_style,
        ),
        Spacer(1, 5 * mm),
    ]
    proof = Table(
        [
            [f"{report['evidence_count']}\n证据", f"{report['source_count']}\n来源", f"{report['confidence']}%\n置信度"],
        ],
        colWidths=[52 * mm, 52 * mm, 52 * mm],
        rowHeights=[17 * mm],
    )
    proof.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), bold_name),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("LEADING", (0, 0), (-1, -1), 15),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#5D715B")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F6F1")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D6DED2")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DDE4D9")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.extend([proof, Spacer(1, 4 * mm)])
    for heading, value in report.get("sections", {}).items():
        story.append(Paragraph(escape(str(heading)), heading_style))
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    item_lines: list[str] = []
                    _append_value(item_lines, [item])
                    item_block = [
                        Paragraph(
                            escape(line).replace("  ", "&nbsp;&nbsp;"),
                            detail_style if index else body_style,
                        )
                        for index, line in enumerate(item_lines)
                    ]
                    story.append(KeepTogether(item_block))
                else:
                    story.append(Paragraph(escape(f"• {item}"), body_style))
        elif isinstance(value, dict):
            for key, nested in value.items():
                story.append(
                    Paragraph(
                        escape(f"{key}：{nested}"),
                        body_style,
                    )
                )
        else:
            story.append(Paragraph(escape(str(value)), body_style))
    story.extend(
        [
            Paragraph("来源说明", heading_style),
            Paragraph(
                "本文件由镜观竞品分析系统生成。事实型结论应结合在线证据链核验；推断与建议不构成专业意见。",
                body_style,
            ),
        ]
    )

    def decorate_page(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(colors.HexColor("#D9DED5"))
        canvas.setLineWidth(0.5)
        canvas.line(20 * mm, height - 14 * mm, width - 20 * mm, height - 14 * mm)
        canvas.setFont(font_name, 7.5)
        canvas.setFillColor(colors.HexColor("#8D928B"))
        canvas.drawString(20 * mm, height - 11 * mm, "镜观 · 竞品情报报告")
        canvas.drawRightString(width - 20 * mm, 11 * mm, f"第 {doc.page} 页 · 内部资料")
        canvas.restoreState()

    document.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    return output.getvalue()


def _build_pdf_fallback(report: dict[str, Any]) -> bytes:
    logical_lines: list[str] = []
    for line in report_lines(report):
        if not line:
            logical_lines.append("")
            continue
        logical_lines.extend(wrap(line, width=42, break_long_words=True, break_on_hyphens=False) or [""])
    pages = [logical_lines[index : index + 42] for index in range(0, len(logical_lines), 42)] or [[report["title"]]]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H /DescendantFonts [4 0 R] >>",
        4: b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light /CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> >>",
    }
    page_ids: list[int] = []
    for page_index, lines in enumerate(pages):
        page_id = 5 + page_index * 2
        content_id = page_id + 1
        page_ids.append(page_id)
        commands: list[str] = []
        for line_index, line in enumerate(lines):
            font_size = 16 if page_index == 0 and line_index == 0 else 10
            y = 790 - line_index * 17
            encoded = ("\ufeff" + line).encode("utf-16-be").hex().upper()
            commands.append(f"BT /F1 {font_size} Tf 48 {y} Td <{encoded}> Tj ET")
        stream = "\n".join(commands).encode("ascii")
        objects[content_id] = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    max_id = max(objects)
    output = BytesIO()
    output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (max_id + 1)
    for object_id in range(1, max_id + 1):
        offsets[object_id] = output.tell()
        output.write(f"{object_id} 0 obj\n".encode("ascii"))
        output.write(objects[object_id])
        output.write(b"\nendobj\n")
    xref = output.tell()
    output.write(f"xref\n0 {max_id + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for object_id in range(1, max_id + 1):
        output.write(f"{offsets[object_id]:010d} 00000 n \n".encode("ascii"))
    output.write(
        f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode("ascii")
    )
    return output.getvalue()


def debug_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)
