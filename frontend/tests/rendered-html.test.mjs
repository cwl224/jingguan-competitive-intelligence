import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the API connection state with product metadata", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<html[^>]*lang="zh-CN"/i);
  assert.match(html, /<title>镜观 · Agent 竞品分析<\/title>/);
  assert.match(html, /正在连接竞品情报服务/);
  assert.match(html, /api-state/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|Building your site/i);
});

test("keeps the FastAPI contract wired through the frontend client and dev proxy", async () => {
  const [page, layout, workbench, sourceManagement, collectionCenter, taskOrchestration, dataProcessing, knowledgeStorage, retrievalRag, competitiveAnalysis, reportAlertCenter, adminSecurityOperations, apiClient, viteConfig] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/Workbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/DataSourceManagement.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/CollectionCenter.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/TaskOrchestration.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/DataProcessing.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/KnowledgeStorage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/RetrievalRAG.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/CompetitiveAnalysis.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ReportAlertCenter.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/AdminSecurityOperations.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/lib/api.ts", import.meta.url), "utf8"),
    readFile(new URL("../vite.config.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /<Workbench\s*\/>/);
  assert.match(layout, /镜观 · Agent 竞品分析/);
  assert.match(workbench, /fetchWorkbench/);
  assert.match(workbench, /createProjectRequest/);
  assert.match(workbench, /claimReview/);
  assert.match(workbench, /generateReport/);
  assert.match(workbench, /DataSourceManagement/);
  assert.match(workbench, /TaskOrchestration/);
  assert.match(workbench, /DataProcessing/);
  assert.match(workbench, /KnowledgeStorage/);
  assert.match(workbench, /RetrievalRAG/);
  assert.match(workbench, /CompetitiveAnalysis/);
  assert.match(workbench, /ReportAlertCenter/);
  assert.match(workbench, /AdminSecurityOperations/);
  assert.match(sourceManagement, /数据源管理/);
  assert.match(sourceManagement, /dynamic_webpage/);
  assert.match(sourceManagement, /CollectionCenter/);
  assert.match(sourceManagement, /runSourceChecks/);
  assert.match(sourceManagement, /rotateSourceCredential/);
  assert.match(sourceManagement, /setSourceStatus/);
  assert.match(apiClient, /\/api\/v1\/workbench/);
  assert.match(apiClient, /\/api\/v1\/projects/);
  assert.match(apiClient, /\/api\/v1\/insights/);
  assert.match(apiClient, /\/api\/v1\/sources/);
  assert.match(collectionCenter, /采集任务与原始材料/);
  assert.match(collectionCenter, /uploadCollectionFile/);
  assert.match(collectionCenter, /fetchCollectionDocuments/);
  assert.match(apiClient, /\/api\/v1\/collection\/runs/);
  assert.match(apiClient, /\/api\/v1\/collection\/documents/);
  assert.match(taskOrchestration, /任务调度与 Agent 编排/);
  assert.match(taskOrchestration, /工作流状态/);
  assert.match(taskOrchestration, /recoverOrchestrationRuns/);
  assert.match(apiClient, /\/api\/v1\/orchestration/);
  assert.match(dataProcessing, /数据清洗与信息抽取/);
  assert.match(dataProcessing, /正文提取/);
  assert.match(dataProcessing, /OCR/);
  assert.match(dataProcessing, /实体抽取/);
  assert.match(dataProcessing, /事件抽取/);
  assert.match(dataProcessing, /runProcessingBatch/);
  assert.match(apiClient, /\/api\/v1\/processing/);
  assert.match(apiClient, /\/api\/v1\/processing\/documents\/\$\{documentId\}\/run/);
  assert.match(knowledgeStorage, /数据与知识存储/);
  assert.match(knowledgeStorage, /原始快照层/);
  assert.match(knowledgeStorage, /分层存储与证据链/);
  assert.match(knowledgeStorage, /reviewKnowledgeItem/);
  assert.match(knowledgeStorage, /createKnowledgeCollection/);
  assert.match(apiClient, /\/api\/v1\/knowledge/);
  assert.match(apiClient, /\/api\/v1\/knowledge\/items\/\$\{itemId\}\/review/);
  assert.match(apiClient, /\/api\/v1\/knowledge\/collections/);
  assert.match(apiClient, /\/api\/v1\/sources\/\$\{sourceId\}\/schedule/);
  assert.match(retrievalRag, /检索与 RAG/);
  assert.match(retrievalRag, /queryRAG/);
  assert.match(retrievalRag, /拒绝无证据补写/);
  assert.match(competitiveAnalysis, /竞品分析 Agent/);
  assert.match(competitiveAnalysis, /runCompetitiveAnalysis/);
  assert.match(competitiveAnalysis, /证据化对比矩阵/);
  assert.match(apiClient, /\/api\/v1\/rag\/query/);
  assert.match(apiClient, /\/api\/v1\/competitive-analysis\/runs/);
  assert.match(reportAlertCenter, /报告、订阅与预警/);
  assert.match(reportAlertCenter, /downloadReport/);
  assert.match(reportAlertCenter, /actOnAlert/);
  assert.match(apiClient, /\/api\/v1\/reports\?/);
  assert.match(apiClient, /\/api\/v1\/alert-rules/);
  assert.match(adminSecurityOperations, /管理、安全与运维/);
  assert.match(adminSecurityOperations, /updateAdminUserAccess/);
  assert.match(adminSecurityOperations, /runAdminBackup/);
  assert.match(apiClient, /\/api\/v1\/admin/);
  assert.match(viteConfig, /target:\s*"http:\/\/127\.0\.0\.1:8000"/);
  assert.doesNotMatch(workbench, /const insights:\s*Insight\[\]/);
});
