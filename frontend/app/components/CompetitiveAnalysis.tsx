"use client";

import {
  ApartmentOutlined,
  BulbOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  DeploymentUnitOutlined,
  LinkOutlined,
  RadarChartOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  WarningFilled,
} from "@ant-design/icons";
import {
  Button,
  Drawer,
  Empty,
  Progress,
  Select,
  Space,
  Tag,
  message,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import {
  fetchCompetitiveAnalysis,
  fetchCompetitiveAnalysisOverview,
  runCompetitiveAnalysis,
  type CompetitiveAnalysisOverview,
  type CompetitiveAnalysisResult,
  type CompetitiveDimension,
  type Project,
  type RAGCitation,
} from "../lib/api";

type Props = { project: Project };

const defaultDimensions: CompetitiveDimension[] = ["capability", "pricing", "governance", "release"];
const rangeLabels = { "7d": "近 7 天", "30d": "近 30 天", "90d": "近 90 天", all: "全部时间" } as const;

function formatDate(value: string | null) {
  if (!value || value === "暂无可信数据") return "暂无可信数据";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function CitationButtons({
  ids,
  citations,
  onOpen,
}: {
  ids: number[];
  citations: Map<number, RAGCitation>;
  onOpen: (citation: RAGCitation) => void;
}) {
  return ids.length ? (
    <span className="inline-citations">
      {ids.map((id) => {
        const citation = citations.get(id);
        return citation ? <button key={id} onClick={() => onOpen(citation)}>{id}</button> : null;
      })}
    </span>
  ) : null;
}

export default function CompetitiveAnalysis({ project }: Props) {
  const [overview, setOverview] = useState<CompetitiveAnalysisOverview | null>(null);
  const [competitors, setCompetitors] = useState<string[]>([]);
  const [dimensions, setDimensions] = useState<CompetitiveDimension[]>(defaultDimensions);
  const [rangeKey, setRangeKey] = useState<"7d" | "30d" | "90d" | "all">("30d");
  const [result, setResult] = useState<CompetitiveAnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<RAGCitation | null>(null);
  const [messageApi, contextHolder] = message.useMessage();

  const loadOverview = async () => {
    try {
      const data = await fetchCompetitiveAnalysisOverview(project.id);
      setOverview(data);
      setCompetitors((current) => current.length ? current : data.suggested_competitors.slice(0, 3));
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "竞品分析配置加载失败");
    }
  };

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadOverview(), 0);
    return () => window.clearTimeout(timeoutId);
    // Project switches intentionally reset the analysis canvas.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  const run = async () => {
    if (competitors.length < 2) {
      messageApi.warning("请至少选择两个竞品");
      return;
    }
    if (!dimensions.length) {
      messageApi.warning("请至少选择一个对比维度");
      return;
    }
    setLoading(true);
    try {
      const data = await runCompetitiveAnalysis({
        project_id: project.id,
        competitors,
        dimensions,
        range_key: rangeKey,
      });
      setResult(data);
      await loadOverview();
      messageApi.success("竞品分析 Agent 已完成证据化对比");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "竞品分析运行失败");
    } finally {
      setLoading(false);
    }
  };

  const openHistory = async (runId: string) => {
    setHistoryLoading(runId);
    try {
      setResult(await fetchCompetitiveAnalysis(runId));
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "历史分析加载失败");
    } finally {
      setHistoryLoading(null);
    }
  };

  const citationMap = useMemo(
    () => new Map((result?.citations ?? []).map((citation) => [citation.id, citation])),
    [result],
  );
  const matrixMap = useMemo(
    () => new Map((result?.matrix ?? []).map((cell) => [`${cell.competitor}:${cell.dimension}`, cell])),
    [result],
  );
  const dimensionLabels = overview?.dimensions ?? {
    capability: "产品能力",
    pricing: "套餐定价",
    governance: "企业治理",
    release: "发布节奏",
    market: "市场与生态",
    reputation: "口碑信号",
  };

  return (
    <div className="analysis-page">
      {contextHolder}
      <section className="module-hero analysis-hero">
        <div>
          <div className="eyebrow"><DeploymentUnitOutlined /> 多 Agent 协作 · 统一证据链</div>
          <h1>竞品分析 Agent</h1>
          <p>自动完成范围拆解、RAG 检索、证据门禁、对比矩阵、SWOT 与可验证的商业建议。</p>
        </div>
        <div className="analysis-hero__metric">
          <RadarChartOutlined />
          <div><strong>{overview?.suggested_competitors.length ?? 0}</strong><span>可分析竞品</span></div>
        </div>
      </section>

      <section className="analysis-builder">
        <div className="analysis-builder__field analysis-builder__field--wide">
          <label>竞品范围</label>
          <Select
            mode="multiple"
            value={competitors}
            onChange={setCompetitors}
            options={(overview?.suggested_competitors ?? []).map((item) => ({ label: item, value: item }))}
            placeholder="至少选择两个竞品"
            maxTagCount="responsive"
          />
        </div>
        <div className="analysis-builder__field analysis-builder__field--wide">
          <label>对比维度</label>
          <Select
            mode="multiple"
            value={dimensions}
            onChange={setDimensions}
            options={Object.entries(dimensionLabels).map(([value, label]) => ({ label, value }))}
            maxTagCount="responsive"
          />
        </div>
        <div className="analysis-builder__field">
          <label>时间窗口</label>
          <Select
            value={rangeKey}
            onChange={setRangeKey}
            options={Object.entries(rangeLabels).map(([value, label]) => ({ label, value }))}
          />
        </div>
        <Button type="primary" icon={<ThunderboltOutlined />} loading={loading} onClick={() => void run()}>
          运行分析 Agent
        </Button>
      </section>

      {overview?.runs.length ? (
        <section className="analysis-history">
          <span><ClockCircleOutlined /> 最近分析</span>
          <div>
            {overview.runs.slice(0, 4).map((item) => (
              <Button
                key={item.id}
                size="small"
                loading={historyLoading === item.id}
                onClick={() => void openHistory(item.id)}
              >
                {item.title} · {item.coverage_rate}%
              </Button>
            ))}
          </div>
        </section>
      ) : null}

      {!result ? (
        <section className="analysis-empty">
          <div className="analysis-empty__orbit"><ApartmentOutlined /><i /><i /><i /></div>
          <h2>配置一次可复现的竞品分析</h2>
          <p>所有矩阵结论都会绑定证据；数据缺失会明确显示“暂无可信数据”。</p>
          <div className="analysis-empty__steps">
            {["范围拆解", "知识检索", "证据校验", "对比与建议"].map((item, index) => (
              <span key={item}><b>{index + 1}</b>{item}</span>
            ))}
          </div>
        </section>
      ) : (
        <>
          <section className="analysis-summary">
            <div className="analysis-summary__title">
              <Tag color={result.status === "completed" ? "green" : "orange"}>
                {result.status === "completed" ? "分析完成" : "部分完成 / 有证据空缺"}
              </Tag>
              <h2>{result.title}</h2>
              <p>{result.executive_summary}</p>
              <div className="analysis-summary__meta">
                <span>数据截止 {formatDate(result.data_cutoff)}</span>
                <span>{rangeLabels[result.range_key]}</span>
                <span>{result.source_count} 个来源</span>
                <span>{result.sample_size} 条证据</span>
              </div>
            </div>
            <div className="analysis-summary__coverage">
              <Progress type="dashboard" percent={result.coverage_rate} strokeColor="#687c67" />
              <span>矩阵证据覆盖率</span>
            </div>
          </section>

          <div className="analysis-top-grid">
            <section className="agent-pipeline">
              <div className="section-heading-row"><div><span>Agent workflow</span><h2>分析轨迹</h2></div></div>
              {result.agent_steps.map((step, index) => (
                <div className={`agent-step ${step.status === "warning" ? "is-warning" : ""}`} key={step.key}>
                  <div className="agent-step__index">{step.status === "warning" ? <WarningFilled /> : <CheckCircleFilled />}</div>
                  <div>
                    <span>{step.agent}</span>
                    <strong>{index + 1}. {step.label}</strong>
                    <p>{step.detail}</p>
                  </div>
                  <Tag>{step.evidence_count} 条</Tag>
                </div>
              ))}
            </section>

            <section className="analysis-findings">
              <div className="section-heading-row"><div><span>Evidence-backed findings</span><h2>关键发现</h2></div></div>
              {result.findings.length ? result.findings.slice(0, 5).map((finding) => (
                <article key={`${finding.title}-${finding.competitors.join()}`}>
                  <div>
                    <Tag color={finding.type === "fact" ? "green" : "blue"}>{finding.type === "fact" ? "事实" : "推断"}</Tag>
                    <Tag color={finding.impact_level === "high" ? "red" : finding.impact_level === "medium" ? "orange" : "default"}>
                      {finding.impact_level === "high" ? "高影响" : finding.impact_level === "medium" ? "中影响" : "低影响"}
                    </Tag>
                  </div>
                  <h3>{finding.title}</h3>
                  <p>{finding.detail}</p>
                  <small>{finding.competitors.join(" / ")}</small>
                  <CitationButtons ids={finding.citation_ids} citations={citationMap} onOpen={setSelectedCitation} />
                </article>
              )) : <Empty description="暂无可被证据支持的发现" />}
            </section>
          </div>

          <section className="comparison-section">
            <div className="section-heading-row">
              <div><span>Comparison matrix</span><h2>证据化对比矩阵</h2></div>
              <Space><Tag color="green">证据充分</Tag><Tag color="orange">证据有限</Tag><Tag color="red">来源冲突</Tag><Tag>暂无数据</Tag></Space>
            </div>
            <div className="comparison-table-wrap">
              <table className="comparison-table">
                <thead><tr><th>竞品</th>{result.dimensions.map((dimension) => <th key={dimension}>{dimensionLabels[dimension]}</th>)}</tr></thead>
                <tbody>
                  {result.competitors.map((competitor) => (
                    <tr key={competitor}>
                      <th><span className="competitor-avatar">{competitor.slice(0, 1)}</span>{competitor}</th>
                      {result.dimensions.map((dimension) => {
                        const cell = matrixMap.get(`${competitor}:${dimension}`);
                        return (
                          <td key={dimension} className={`matrix-cell matrix-cell--${cell?.status ?? "missing"}`}>
                            <div className="matrix-cell__status">
                              <i />
                              {cell?.status === "evidence" ? "证据充分" : cell?.status === "limited" ? "证据有限" : cell?.status === "conflict" ? "来源冲突" : "暂无可信数据"}
                              {cell?.confidence ? <span>{cell.confidence}%</span> : null}
                            </div>
                            <p>{cell?.summary ?? "暂无可信数据；不据此推断竞争劣势。"}</p>
                            {cell && <CitationButtons ids={cell.citation_ids} citations={citationMap} onOpen={setSelectedCitation} />}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="swot-section">
            <div className="section-heading-row"><div><span>Grounded SWOT</span><h2>SWOT 分析</h2></div></div>
            <div className="swot-grid">
              {result.swot.map((item) => (
                <article key={item.competitor} className="swot-card">
                  <header><span className="competitor-avatar">{item.competitor.slice(0, 1)}</span><h3>{item.competitor}</h3></header>
                  {([
                    ["S", "证据支持的优势信号", item.strengths],
                    ["W", "弱势或证据风险", item.weaknesses],
                    ["O", "机会", item.opportunities],
                    ["T", "威胁", item.threats],
                  ] as const).map(([code, label, entries]) => (
                    <div className={`swot-row swot-row--${code.toLowerCase()}`} key={code}>
                      <b>{code}</b>
                      <div><strong>{label}</strong>{entries.map((entry) => (
                        <p key={entry.text}>{entry.text}<CitationButtons ids={entry.citation_ids} citations={citationMap} onOpen={setSelectedCitation} /></p>
                      ))}</div>
                    </div>
                  ))}
                </article>
              ))}
            </div>
          </section>

          <section className="recommendation-section">
            <div className="section-heading-row"><div><span>Actionable recommendations</span><h2>商业建议</h2></div></div>
            <div className="recommendation-list">
              {result.recommendations.map((recommendation, index) => (
                <article key={recommendation.action}>
                  <div className="recommendation-index"><BulbOutlined /><span>{String(index + 1).padStart(2, "0")}</span></div>
                  <div className="recommendation-content">
                    <Tag>{recommendation.applicable_to}</Tag>
                    <h3>{recommendation.action}</h3>
                    <dl>
                      <div><dt>依据</dt><dd>{recommendation.basis}<CitationButtons ids={recommendation.citation_ids} citations={citationMap} onOpen={setSelectedCitation} /></dd></div>
                      <div><dt>预期影响</dt><dd>{recommendation.expected_impact}</dd></div>
                      <div><dt>风险</dt><dd>{recommendation.risk}</dd></div>
                      <div><dt>验证方式</dt><dd>{recommendation.validation}</dd></div>
                    </dl>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="analysis-notices">
            <SafetyCertificateOutlined />
            <div>{result.notices.map((notice) => <p key={notice}>{notice}</p>)}</div>
          </section>
        </>
      )}

      <Drawer title="分析引用证据" size={520} open={Boolean(selectedCitation)} onClose={() => setSelectedCitation(null)}>
        {selectedCitation && (
          <div className="evidence-drawer">
            <div className="evidence-drawer__tags">
              <Tag color="green">引用 {selectedCitation.id}</Tag>
              <Tag>{selectedCitation.review_status === "verified" ? "已核验" : selectedCitation.review_status === "conflict" ? "来源冲突" : "待复核"}</Tag>
            </div>
            <h2>{selectedCitation.title}</h2>
            <p>{selectedCitation.summary}</p>
            <blockquote>{selectedCitation.evidence_excerpt}</blockquote>
            <dl>
              <div><dt>主体</dt><dd>{selectedCitation.subject}</dd></div>
              <div><dt>来源</dt><dd>{selectedCitation.source_name}</dd></div>
              <div><dt>发布时间</dt><dd>{formatDate(selectedCitation.published_at)}</dd></div>
              <div><dt>置信度</dt><dd>{selectedCitation.confidence}%</dd></div>
            </dl>
            {selectedCitation.source_url ? <Button icon={<LinkOutlined />} href={selectedCitation.source_url} target="_blank">打开原始来源</Button> : null}
          </div>
        )}
      </Drawer>
    </div>
  );
}
