# 镜观 FastAPI 后端

该服务为现有竞品分析工作台提供真实 API 与 SQLite 持久化，覆盖项目、工作台指标、趋势、数据源与授权管理、五类数据采集、来源健康、原始快照与版本、数据清洗、知识索引、洞察证据、人工复核、专题集合、报告任务和搜索。

## 本地启动

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

服务地址为 `http://127.0.0.1:8000`，接口文档为 `http://127.0.0.1:8000/docs`。首次启动会自动创建 `data/jinguan.db` 并写入与前端工作台一致的演示数据。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 认证与访问控制

- 生产环境必须设置至少 32 个字符的 `AUTH_SECRET`，所有 `/api/v1` 接口只接受 `Authorization: Bearer <token>`。
- 开发/测试环境可通过 `ALLOW_LEGACY_USER_HEADER=true` 保留 `X-User-Id` 和 `DEFAULT_USER_ID`，该兼容入口在生产环境始终关闭。
- 服务端同时校验角色权限、成员状态、项目范围和数据域；搜索、来源、采集材料、处理结果与知识条目不会越权返回。
- `DELETE /api/v1/sources/{id}` 只归档已停用来源并保留配置、运行记录和证据；永久清除仅限管理员调用 `/purge`，请求体必须提供 `PURGE:{id}` 精确确认值。

## 采集器配置

- `webpage`：静态 HTML 正文抽取，可配置 `content_selector`
- `dynamic_webpage`：通过 Playwright + Edge/Chromium 渲染，可配置 `wait_selector`、`wait_ms` 和 `browser_channel`
- `rss`：解析 RSS 2.0 与 Atom，可配置 `max_items`
- `public_api` / `social_api` / `public_database`：只允许 GET，可配置 `items_path`、标题/正文/URL/发布时间字段路径
- `file_upload`：支持 TXT、Markdown、HTML、JSON、CSV、XML、PDF、DOCX、XLSX、PNG、JPEG、WebP、TIFF 和 BMP

默认禁止采集解析到私网、本机、链路本地或保留地址的 URL。只有受控的本地测试环境才应设置 `COLLECTOR_ALLOW_PRIVATE_NETWORKS=true`。非公开 API 的密钥引用由运行环境的 `SOURCE_CREDENTIALS_JSON` 解析，数据库和接口只保存/返回引用及掩码，不保存明文凭据。

## 调度与异常恢复

每个任务会保存优先级、任务级超时、最大尝试次数、退避基数和四个 Agent 工作流节点。可通过来源调度策略配置采集周期、每分钟速率、单来源并发、超时、重试与优先级。连续失败达到阈值后来源进入熔断，恢复任务以半开状态试探；服务重启时遗留的运行中任务会自动重新排队或进入人工异常队列。

## 数据清洗、OCR 与抽取

新采集材料会自动进入独立处理结果层，原始响应和采集快照不会被改写。处理链包括正文提取、去噪、语言识别、OCR、跨来源精确/近似去重、实体抽取、事件抽取和质量门禁；所有抽取项均返回原文位置、方法与置信度。

OCR 默认调用部署机上的 Tesseract。可通过 `OCR_ENABLED`、`OCR_COMMAND`、`OCR_LANGUAGES` 和 `OCR_TIMEOUT_SECONDS` 配置；扫描 PDF 还需要 `pdftoppm`。引擎不可用或识别失败时任务不会污染正文，而是进入待人工复核。近似重复阈值可通过 `NEAR_DUPLICATE_THRESHOLD` 配置。

## 数据与知识存储

知识层与原始快照、处理结果分表保存。处理链成功后会自动生成材料事实、实体和事件条目，并绑定来源、文档版本、内容哈希、证据位置、抽取方法、置信度和质量分。知识条目支持复核状态版本、审计记录及专题集合关系；来源授权或新鲜度存在风险时可保留条目，但会在展示层显式提示。

## 检索、RAG 与竞品分析 Agent

RAG 引擎先按项目、来源授权、知识有效期及用户筛选条件确定候选集，再以中英文词项扩展、字段权重、置信度、复核状态和来源风险进行重排。回答采用证据约束的抽取式生成，不依赖外部模型；没有可信证据时返回明确拒答。每次查询均保留过滤条件、召回知识 ID、生成模式和审计事件。

竞品分析 Agent 复用同一 RAG 与引用链，依次执行任务拆解、知识检索、证据门禁、矩阵/SWOT 和策略建议。分析结果会持久化，包含样本量、来源数、覆盖率、缺失/冲突状态、事实与推断标签、引用和 Agent 轨迹。

## 报告、预警与治理运维

报告中心将模板、版本、证据覆盖、审批、订阅与导出记录分层保存。报告任务完成后根据模板进入自动交付或人工审批，在线正文与 Word/PDF 导出均带数据截止时间、版本、证据和来源口径。预警规则支持影响等级、置信度、变化幅度、静默与升级，相同信号合并后可确认或关闭。

管理中心以服务端 RBAC 保护组织、成员、模型、安全策略、事故和备份操作。系统保存 MFA、项目范围、数据域与导出级别，展示模型预算及黄金集评测，并从真实任务、报告、服务组件、事故和备份记录计算运维指标。备份操作会在 `data/backups/` 生成 SQLite 全量快照并执行完整性校验。所有配置与处置动作继续写入统一审计表。

## 主要接口

- `GET /health`
- `GET /api/v1/workbench?project_id=...&range=7d`
- `GET /api/v1/projects`
- `POST /api/v1/projects`
- `GET /api/v1/sources?project_id=...`
- `POST /api/v1/sources`
- `PATCH /api/v1/sources/{id}`
- `POST /api/v1/sources/{id}/checks`
- `PATCH /api/v1/sources/{id}/status`
- `POST /api/v1/sources/{id}/runs`
- `PATCH /api/v1/sources/{id}/schedule`
- `GET /api/v1/orchestration?project_id=...`
- `POST /api/v1/orchestration/triggers`
- `POST /api/v1/orchestration/runs/retry`
- `POST /api/v1/orchestration/recover`
- `GET /api/v1/collection/runs?project_id=...`
- `GET /api/v1/collection/runs/{id}`
- `POST /api/v1/collection/runs/{id}/retry`
- `POST /api/v1/collection/runs/{id}/cancel`
- `GET /api/v1/collection/documents?project_id=...`
- `GET /api/v1/collection/documents/{id}`
- `GET /api/v1/collection/documents/{id}/raw`
- `POST /api/v1/collection/files`
- `GET /api/v1/processing?project_id=...`
- `GET /api/v1/processing/documents/{id}`
- `POST /api/v1/processing/jobs`
- `POST /api/v1/processing/documents/{id}/run`
- `GET /api/v1/knowledge?project_id=...`
- `GET /api/v1/knowledge/items/{id}`
- `PATCH /api/v1/knowledge/items/{id}/review`
- `POST /api/v1/knowledge/collections`
- `POST /api/v1/knowledge/collections/{collection_id}/items/{item_id}`
- `DELETE /api/v1/knowledge/collections/{collection_id}/items/{item_id}`
- `POST /api/v1/sources/{id}/credentials/rotate`
- `DELETE /api/v1/sources/{id}`
- `DELETE /api/v1/sources/{id}/purge`
- `GET /api/v1/insights/{id}`
- `POST /api/v1/reviews/{id}/claim`
- `POST /api/v1/reports/generate`
- `GET /api/v1/reports?project_id=...`
- `GET /api/v1/reports/{id}`
- `POST /api/v1/reports/{id}/approval`
- `GET /api/v1/reports/{id}/export?format=pdf|docx`
- `PATCH /api/v1/report-subscriptions/{id}`
- `POST /api/v1/alert-rules`
- `PATCH /api/v1/alert-rules/{id}`
- `POST /api/v1/alerts/{id}/actions`
- `GET /api/v1/admin`
- `PATCH /api/v1/admin/users/{id}/access`
- `PATCH /api/v1/admin/models/{id}`
- `PATCH /api/v1/admin/policies/{id}`
- `POST /api/v1/admin/incidents/{id}/actions`
- `POST /api/v1/admin/backups`
- `GET /api/v1/search?q=...`
- `POST /api/v1/rag/query`
- `GET /api/v1/competitive-analysis?project_id=...`
- `POST /api/v1/competitive-analysis/runs`
- `GET /api/v1/competitive-analysis/runs/{id}`

本地前端默认通过 Vite 代理访问 `/api/v1`。跨域或独立部署时，在前端配置 `NEXT_PUBLIC_API_BASE_URL` 和 `NEXT_PUBLIC_AUTH_TOKEN`，并同步更新后端 `CORS_ORIGINS`。
