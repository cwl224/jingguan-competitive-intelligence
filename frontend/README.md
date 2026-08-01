# 镜观竞品分析工作台

这是“镜观”Agent 竞品分析系统的现有前端，使用 React、Vinext、Ant Design 和 ECharts。工作台已接入 `../backend` 中的 FastAPI 服务，不再依赖组件内的静态演示数组。数据运营页包含来源配置、采集任务日志、失败重试、原始材料与文件上传采集；情报库包含分层存储概览、统一知识检索、证据链、人工复核和专题集合管理；检索与 RAG 页提供带过滤器、引用抽屉和检索轨迹的证据化问答；竞品分析 Agent 页提供运行配置、历史结果、对比矩阵、SWOT 和商业建议；报告与预警页提供模板生成、审批、在线阅读、Word/PDF 导出、订阅交付和预警处置；系统管理页覆盖 RBAC、MFA、模型与预算、安全策略、评测、审计、服务健康、事故和备份恢复。

## 本地启动

请先按 `../backend/README.md` 启动后端，再执行：

```powershell
npm install
npm run dev
```

前端默认把 `/api` 和 `/health` 代理到 `http://127.0.0.1:8000`。如果前后端独立部署，请复制 `.env.example` 为 `.env.local`，并设置：

```text
NEXT_PUBLIC_API_BASE_URL=https://your-api.example.com
```

## 验证

```powershell
npm run lint
npm test
```

`npm test` 会完成生产构建，并验证服务端首屏和 FastAPI 接口契约是否仍然接通。
