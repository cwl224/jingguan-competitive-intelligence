"use client";

import {
  CheckCircleFilled,
  ClockCircleOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  LinkOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  WarningFilled,
} from "@ant-design/icons";
import {
  Button,
  Drawer,
  Empty,
  Input,
  Progress,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
  message,
} from "antd";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchKnowledgeOverview,
  queryRAG,
  type KnowledgeItemType,
  type Project,
  type RAGCitation,
  type RAGResponse,
} from "../lib/api";

type Props = {
  project: Project;
  initialQuestion?: string;
};

const quickQuestions = [
  "哪些竞品正在强化企业治理能力？",
  "最近有哪些高可信产品发布事件？",
  "定价相关信息中有哪些冲突或待复核项？",
  "现有证据能支持哪些 Agent 产品趋势判断？",
];

const typeOptions: Array<{ label: string; value: KnowledgeItemType }> = [
  { label: "事实", value: "fact" },
  { label: "事件", value: "event" },
  { label: "实体", value: "entity" },
  { label: "洞察 / 推断", value: "insight" },
];

function formatDate(value: string | null) {
  if (!value) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function typeLabel(type: KnowledgeItemType) {
  return type === "insight" ? "推断" : type === "event" ? "事件" : type === "entity" ? "实体" : "事实";
}

export default function RetrievalRAG({ project, initialQuestion = "" }: Props) {
  const [question, setQuestion] = useState(initialQuestion);
  const [competitors, setCompetitors] = useState<string[]>([]);
  const [availableCompetitors, setAvailableCompetitors] = useState<string[]>([]);
  const [itemTypes, setItemTypes] = useState<KnowledgeItemType[]>([]);
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [includeAtRisk, setIncludeAtRisk] = useState(true);
  const [topK, setTopK] = useState(6);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RAGResponse | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<RAGCitation | null>(null);
  const [messageApi, contextHolder] = message.useMessage();
  const lastInitialQuestion = useRef("");

  useEffect(() => {
    let active = true;
    void fetchKnowledgeOverview(project.id)
      .then((data) => {
        if (!active) return;
        setAvailableCompetitors(
          Array.from(new Set(data.items.map((item) => item.subject).filter(Boolean) as string[])).sort(),
        );
      })
      .catch(() => {
        if (active) setAvailableCompetitors([]);
      });
    return () => {
      active = false;
    };
  }, [project.id]);

  const ask = useCallback(async (nextQuestion?: string) => {
    const normalized = (nextQuestion ?? question).trim();
    if (!normalized) {
      messageApi.warning("请输入需要基于证据回答的问题");
      return;
    }
    setQuestion(normalized);
    setLoading(true);
    try {
      const response = await queryRAG(project.id, normalized, {
        competitors,
        item_types: itemTypes,
        review_statuses: verifiedOnly ? ["verified"] : [],
        include_at_risk: includeAtRisk,
        top_k: topK,
      });
      setResult(response);
      if (response.answer_type === "insufficient") {
        messageApi.warning("证据不足，系统已拒绝补写答案");
      }
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "RAG 检索失败");
    } finally {
      setLoading(false);
    }
  }, [competitors, includeAtRisk, itemTypes, messageApi, project.id, question, topK, verifiedOnly]);

  useEffect(() => {
    const normalized = initialQuestion.trim();
    if (!normalized || normalized === lastInitialQuestion.current) return;
    lastInitialQuestion.current = normalized;
    const timeoutId = window.setTimeout(() => void ask(normalized), 0);
    return () => window.clearTimeout(timeoutId);
  }, [ask, initialQuestion]);

  const citationMap = useMemo(
    () => new Map((result?.citations ?? []).map((citation) => [citation.id, citation])),
    [result],
  );

  const renderAnswer = (answer: string) => answer.split("\n").map((line, lineIndex) => {
    const parts = line.split(/(\[\d+\])/g);
    return (
      <p key={`${lineIndex}-${line}`} className={line.startsWith("- ") ? "rag-answer__bullet" : ""}>
        {parts.map((part, index) => {
          const match = part.match(/^\[(\d+)\]$/);
          const citation = match ? citationMap.get(Number(match[1])) : null;
          return citation ? (
            <button
              key={`${part}-${index}`}
              className="citation-chip"
              onClick={() => setSelectedCitation(citation)}
              aria-label={`查看引用 ${citation.id}`}
            >
              {citation.id}
            </button>
          ) : <Fragment key={`${part}-${index}`}>{part}</Fragment>;
        })}
      </p>
    );
  });

  return (
    <div className="rag-page">
      {contextHolder}
      <section className="module-hero rag-hero">
        <div>
          <div className="eyebrow"><SafetyCertificateOutlined /> 权限过滤 · 证据约束 · 可审计轨迹</div>
          <h1>检索与 RAG</h1>
          <p>向项目知识库提问。系统只引用已授权、未过期的材料，并明确区分事实、推断与未知。</p>
        </div>
        <div className="rag-hero__guardrail">
          <SafetyCertificateOutlined />
          <div><strong>拒绝无证据补写</strong><span>空值不会被解释为竞品劣势</span></div>
        </div>
      </section>

      <section className="rag-query-card">
        <div className="rag-query-card__main">
          <Input.TextArea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onPressEnter={(event) => {
              if (!event.shiftKey) {
                event.preventDefault();
                void ask();
              }
            }}
            autoSize={{ minRows: 2, maxRows: 5 }}
            placeholder="例如：哪些竞品最近强化了企业治理能力？相关证据是否一致？"
            aria-label="RAG 问题"
          />
          <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={() => void ask()}>
            检索并回答
          </Button>
        </div>
        <div className="rag-filters">
          <Select
            mode="multiple"
            value={competitors}
            onChange={setCompetitors}
            options={availableCompetitors.map((item) => ({ label: item, value: item }))}
            placeholder="全部竞品"
            maxTagCount="responsive"
            aria-label="筛选竞品"
          />
          <Select
            mode="multiple"
            value={itemTypes}
            onChange={setItemTypes}
            options={typeOptions}
            placeholder="全部知识类型"
            maxTagCount="responsive"
            aria-label="筛选知识类型"
          />
          <label><Switch size="small" checked={verifiedOnly} onChange={setVerifiedOnly} /> 仅已核验</label>
          <label><Switch size="small" checked={includeAtRisk} onChange={setIncludeAtRisk} /> 含风险来源</label>
          <Select
            value={topK}
            onChange={setTopK}
            options={[3, 6, 9, 12].map((value) => ({ label: `最多 ${value} 条`, value }))}
            aria-label="召回数量"
          />
        </div>
        <div className="quick-query-row">
          <span>推荐问题</span>
          {quickQuestions.map((item) => (
            <button key={item} onClick={() => void ask(item)}>{item}</button>
          ))}
        </div>
      </section>

      {!result ? (
        <section className="rag-empty">
          <div className="rag-empty__visual"><FileSearchOutlined /><i /><i /></div>
          <h2>从问题下钻到原始证据</h2>
          <p>回答会显示召回数量、数据截止时间、置信度、证据片段与完整检索轨迹。</p>
        </section>
      ) : (
        <div className="rag-result-grid">
          <div className="rag-result-main">
            <section className={`rag-answer ${result.answer_type === "insufficient" ? "rag-answer--warning" : ""}`}>
              <div className="rag-answer__head">
                <div>
                  <Tag color={result.answer_type === "grounded" ? "green" : "orange"}>
                    {result.answer_type === "grounded" ? "证据化回答" : "证据不足 / 已拒答"}
                  </Tag>
                  <span>数据截止 {formatDate(result.data_cutoff === "暂无可信数据" ? null : result.data_cutoff)}</span>
                </div>
                <div className="rag-confidence">
                  <Progress type="circle" size={48} percent={result.confidence} strokeColor="#687c67" />
                  <span>综合置信度</span>
                </div>
              </div>
              <h2>{result.question}</h2>
              <div className="rag-answer__body">{renderAnswer(result.answer)}</div>
              <div className="rag-notices">
                {result.notices.map((notice) => <span key={notice}><SafetyCertificateOutlined /> {notice}</span>)}
              </div>
            </section>

            <section className="rag-citations-section">
              <div className="section-heading-row">
                <div><span>Grounding evidence</span><h2>引用证据</h2></div>
                <Tag>{result.citations.length} 条</Tag>
              </div>
              {result.citations.length ? (
                <div className="rag-citation-list">
                  {result.citations.map((citation) => (
                    <button key={citation.item_id} className="rag-citation-card" onClick={() => setSelectedCitation(citation)}>
                      <span className="rag-citation-card__number">{citation.id}</span>
                      <div>
                        <div className="rag-citation-card__meta">
                          <Tag>{typeLabel(citation.item_type)}</Tag>
                          <strong>{citation.subject}</strong>
                          <span>相关度 {Math.round(citation.relevance * 100)}%</span>
                        </div>
                        <h3>{citation.title}</h3>
                        <p>“{citation.evidence_excerpt}”</p>
                        <small>{citation.source_name} · {formatDate(citation.published_at)}</small>
                      </div>
                      <span className="rag-citation-card__open">查看证据 →</span>
                    </button>
                  ))}
                </div>
              ) : <Empty description="当前筛选范围内没有可引用证据" />}
            </section>
          </div>

          <aside className="rag-trace-panel">
            <div className="section-heading-row"><div><span>Retrieval trace</span><h2>检索轨迹</h2></div></div>
            <div className="rag-trace-stats">
              <div><strong>{result.trace.candidate_count}</strong><span>权限内候选</span></div>
              <div><strong>{result.trace.retrieved_count}</strong><span>最终引用</span></div>
            </div>
            <div className="rag-trace-steps">
              {result.trace.stages.map((stage) => (
                <div key={stage.key} className={stage.status === "warning" ? "is-warning" : ""}>
                  <i>{stage.status === "warning" ? <WarningFilled /> : <CheckCircleFilled />}</i>
                  <strong>{stage.label}</strong>
                  <p>{stage.detail}</p>
                </div>
              ))}
            </div>
            <div className="rag-query-terms">
              <strong>查询扩展词</strong>
              <Space size={[4, 6]} wrap>
                {result.trace.query_terms.slice(0, 18).map((term) => <Tag key={term}>{term}</Tag>)}
              </Space>
            </div>
            <div className="rag-model-note"><DatabaseOutlined /> 本地抽取式生成 · 不调用外部模型</div>
          </aside>
        </div>
      )}

      <Drawer
        title="证据详情"
        size={520}
        open={Boolean(selectedCitation)}
        onClose={() => setSelectedCitation(null)}
      >
        {selectedCitation && (
          <div className="evidence-drawer">
            <div className="evidence-drawer__tags">
              <Tag color="green">{typeLabel(selectedCitation.item_type)}</Tag>
              <Tag>{selectedCitation.review_status === "verified" ? "已核验" : selectedCitation.review_status === "conflict" ? "来源冲突" : "待复核"}</Tag>
              {selectedCitation.validity_status === "at_risk" && <Tag color="orange">来源风险</Tag>}
            </div>
            <h2>{selectedCitation.title}</h2>
            <p>{selectedCitation.summary}</p>
            <blockquote>{selectedCitation.evidence_excerpt}</blockquote>
            <dl>
              <div><dt>主体</dt><dd>{selectedCitation.subject}</dd></div>
              <div><dt>来源</dt><dd>{selectedCitation.source_name}</dd></div>
              <div><dt>发布时间</dt><dd>{formatDate(selectedCitation.published_at)}</dd></div>
              <div><dt>置信度</dt><dd>{selectedCitation.confidence}%</dd></div>
              <div><dt>检索相关度</dt><dd>{Math.round(selectedCitation.relevance * 100)}%</dd></div>
            </dl>
            {selectedCitation.source_url ? (
              <Button icon={<LinkOutlined />} href={selectedCitation.source_url} target="_blank">打开原始来源</Button>
            ) : (
              <Tooltip title="该知识来自内部材料，未登记公开 URL"><Button disabled>无公开链接</Button></Tooltip>
            )}
            <div className="evidence-drawer__audit"><ClockCircleOutlined /> 引用 ID {selectedCitation.item_id}</div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
