# 镜观 Agent 竞品分析系统

本仓库包含产品需求文档、已完成的前端和与之对接的 FastAPI 后端。模块二覆盖多类型数据采集，模块三覆盖任务调度与 Agent 编排，模块四覆盖数据清洗与信息抽取，模块五覆盖数据与知识存储，模块六覆盖检索与 RAG，模块七覆盖竞品分析 Agent。
<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776ab.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)
![React](https://img.shields.io/badge/React-19.2-61dafb.svg)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178c6.svg)
![Vinext](https://img.shields.io/badge/Vinext-0.0.50-646cff.svg)
![Ant Design](https://img.shields.io/badge/Ant%20Design-6.5-1677ff.svg)
![SQLite](https://img.shields.io/badge/SQLite-3-003b57.svg)
![Playwright](https://img.shields.io/badge/Playwright-1.50+-2eAD33.svg)

**基于 React + FastAPI + RAG + 多 Agent 的证据化竞品情报分析平台**

[项目简介](#项目简介) · [核心亮点](#核心亮点) · [技术架构](#技术架构) · [功能模块](#功能模块) · [快速启动](#快速启动) · [接口概览](#接口概览)

</div>

---

## 项目简介

镜观是一套面向产品、市场、战略和管理团队的 Agent 竞品分析系统。平台覆盖外部数据采集、任务调度、内容清洗、知识沉淀、证据检索、竞品分析、报告交付、预警处置和安全运维，形成从原始信息到商业洞察的完整闭环。

用户可以配置网页、RSS、公开 API、数据库和本地文件等数据源，通过调度与 Agent 工作流持续采集竞品信息；系统对材料执行正文提取、OCR、去重、实体识别和事件抽取，并将可信事实写入带来源、版本、原文位置和置信度的知识库。

分析阶段采用证据约束的 RAG 与多 Agent 流程，依次完成任务规划、知识检索、证据校验、对比分析和策略建议。证据不足时系统会明确拒绝补写，避免把推测包装成事实。

### 项目价值

- 完整情报闭环：采集、处理、存储、检索、分析、报告和预警统一管理。
- 证据可追溯：结论关联来源、材料版本、原文位置、抽取方式和置信度。
- 多 Agent 编排：将复杂竞品研究拆分为可观察、可恢复的分析步骤。
- 企业级治理：提供 RBAC、MFA、项目范围、数据域、审计和模型预算管理。
- 多格式交付：支持在线报告、审批流以及 Word/PDF 文件导出。
- 合规采集边界：默认阻止私网访问，不绕过登录、验证码、付费墙或 robots 限制。

### 界面预览

![镜观 Agent 竞品分析工作台](frontend/public/og.png)

---

## 核心亮点

### 业务能力

## 目录
- 多项目工作台展示情报数量、趋势、来源健康度、待复核任务和最新洞察。
- 支持静态网页、动态网页、RSS/Atom、只读 JSON API、公开数据库和文件上传。
- 支持立即、定时、事件和 API 触发，并提供重试、超时、限速、并发及熔断策略。
- 支持正文提取、噪声清理、语言识别、OCR、精确/近似去重、实体与事件抽取。
- 提供分层知识存储、统一检索、证据链下钻、人工复核和专题集合。
- 提供证据化 RAG 问答、竞品对比矩阵、SWOT、商业建议和历史分析版本。
- 提供日报、周报、产品对比、竞品快讯、专题研究和高管摘要模板。
- 提供报告订阅、信号合并、影响分级、静默期、升级时限和预警处置。

- `Agent竞品分析系统_产品需求文档_V1.0_最终版.docx`：产品需求依据
- `frontend/`：Vinext + React 工作台
- `backend/`：FastAPI + SQLite API 服务
### 技术能力

## 启动后端
- FastAPI + SQLite 提供真实 REST API、持久化和自动演示数据初始化。
- React + TypeScript + Ant Design 构建单页竞品情报工作台。
- Playwright 调用 Edge/Chromium 采集需要浏览器渲染的动态页面。
- SHA-256 内容指纹与 URL 版本链保留原始材料的完整历史。
- RAG 使用中英文词项扩展、字段权重、置信度和复核状态进行重排。
- Agent 分析结果区分事实与推断，记录引用覆盖率、样本量和执行轨迹。
- HMAC 签名 Bearer Token、角色权限、项目范围和数据域共同完成访问控制。
- 报告导出使用 python-docx 与 ReportLab 生成真实 Word/PDF 文件。

---

## 技术架构

### 后端技术栈

| 技术 | 版本/说明 | 用途 |
| --- | --- | --- |
| Python | 3.11+ | 后端运行环境 |
| FastAPI | 0.115+ | REST API 与 OpenAPI 文档 |
| Uvicorn | 0.30+ | ASGI 开发与生产服务 |
| SQLite | 内置 | 项目、材料、知识、报告和审计数据持久化 |
| HTTPX | 0.27+ | 合规 HTTP 数据采集 |
| Beautiful Soup | 4.12+ | HTML 解析与正文提取 |
| Playwright | 1.50+ | 动态网页浏览器渲染 |
| Feedparser | 6.x | RSS/Atom 订阅解析 |
| PyPDF / python-docx / openpyxl | 多格式解析 | PDF、DOCX、XLSX 文件处理 |
| ReportLab / python-docx | 文档导出 | PDF 与 Word 报告生成 |
| Pytest | 8+ | 后端接口与业务测试 |

### 前端技术栈
