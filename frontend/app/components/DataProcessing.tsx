"use client";

import {
  ApartmentOutlined,
  CheckCircleFilled,
  ClearOutlined,
  CopyOutlined,
  FileSearchOutlined,
  FilterOutlined,
  LoadingOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  ScanOutlined,
  SettingOutlined,
  TagsOutlined,
  TranslationOutlined,
  WarningFilled,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Checkbox,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Progress,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
  message,
  type TableProps,
} from "antd";
import type { Key, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  defaultProcessingOptions,
  fetchProcessingDocument,
  fetchProcessingOverview,
  runProcessingBatch,
  runProcessingDocument,
  type EntityMention,
  type ExtractedEvent,
  type ProcessingDocument,
  type ProcessingDocumentDetail,
  type ProcessingOptions,
  type ProcessingOverview,
  type ProcessingStatus,
  type Project,
} from "../lib/api";

type Props = {
  project: Project;
};

const statusMeta: Record<ProcessingStatus, { label: string; color: string }> = {
  pending: { label: "待处理", color: "default" },
  processing: { label: "处理中", color: "processing" },
  completed: { label: "已完成", color: "success" },
  review_required: { label: "待复核", color: "warning" },
  failed: { label: "失败", color: "error" },
};

const entityLabels: Record<EntityMention["type"], string> = {
  company: "企业",
  brand: "品牌",
  product: "产品",
  person: "人物",
  version: "版本",
  price: "价格",
  location: "地点",
  date: "日期",
  feature: "功能",
};

const optionLabels: Array<{ key: keyof ProcessingOptions; label: string; note: string }> = [
  { key: "extract_body", label: "正文提取", note: "优先 article/main 等语义节点并保留原始快照" },
  { key: "denoise", label: "内容去噪", note: "移除导航、版权、Cookie 提示和重复行" },
  { key: "deduplicate", label: "跨来源去重", note: "结合规范化哈希与文本相似度合并近似重复" },
  { key: "detect_language", label: "语言识别", note: "识别中、英、日、韩及未知语言" },
  { key: "ocr", label: "OCR", note: "图片及无文本扫描 PDF 自动进入 OCR" },
  { key: "extract_entities", label: "实体抽取", note: "企业、品牌、产品、人物、版本、价格、地点、日期与功能" },
  { key: "extract_events", label: "事件抽取", note: "发布、价格、合作、融资、市场进退和功能变化" },
];

const pipeline: Array<{ label: string; note: string; icon: ReactNode }> = [
  { label: "正文提取", note: "语义正文", icon: <FileSearchOutlined /> },
  { label: "内容去噪", note: "导航与广告", icon: <ClearOutlined /> },
  { label: "语言识别", note: "多语言", icon: <TranslationOutlined /> },
  { label: "OCR", note: "图片与扫描件", icon: <ScanOutlined /> },
  { label: "去重归并", note: "跨来源", icon: <CopyOutlined /> },
  { label: "实体抽取", note: "9 类实体", icon: <TagsOutlined /> },
  { label: "事件抽取", note: "变化事实", icon: <ApartmentOutlined /> },
];

function formatTime(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function qualityColor(score: number) {
  if (score >= 85) return "#687c67";
  if (score >= 65) return "#ba885e";
  return "#ad5c51";
}

function statusTag(status: ProcessingStatus) {
  const meta = statusMeta[status];
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

function eventTag(event: ExtractedEvent) {
  const color = event.impact_level === "high" ? "volcano" : event.impact_level === "medium" ? "gold" : "default";
  return <Tag color={color}>{event.label}</Tag>;
}

export default function DataProcessing({ project }: Props) {
  const [overview, setOverview] = useState<ProcessingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Key[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<ProcessingDocumentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<ProcessingStatus | "all">("all");
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [options, setOptions] = useState<ProcessingOptions>({ ...defaultProcessingOptions });
  const [messageApi, contextHolder] = message.useMessage();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchProcessingOverview(project.id, {
        status: statusFilter === "all" ? undefined : statusFilter,
        query: appliedQuery || undefined,
      });
      setOverview(data);
      setSelectedKeys((current) => current.filter((key) => data.items.some((item) => item.document_id === key)));
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "处理中心加载失败");
    } finally {
      setLoading(false);
    }
  }, [appliedQuery, messageApi, project.id, statusFilter]);

  useEffect(() => {
    const timeout = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timeout);
  }, [load]);

  const openDetail = async (item: ProcessingDocument) => {
    setDetailLoading(true);
    try {
      setSelectedDocument(await fetchProcessingDocument(item.document_id));
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "处理结果加载失败");
    } finally {
      setDetailLoading(false);
    }
  };

  const processDocuments = async (documentIds: string[]) => {
    if (!documentIds.length) {
      messageApi.info("当前没有待处理材料");
      return;
    }
    setBusy(true);
    try {
      const result = await runProcessingBatch(project.id, documentIds, options);
      messageApi.success(`已处理 ${result.requested} 条：自动通过 ${result.completed}，待复核 ${result.review_required}`);
      setSelectedKeys([]);
      await load();
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "批量处理失败");
    } finally {
      setBusy(false);
    }
  };

  const rerunDocument = async (item: ProcessingDocument) => {
    setBusyId(item.document_id);
    try {
      const result = await runProcessingDocument(item.document_id, options);
      messageApi.success(result.needs_review ? "处理完成，结果已进入人工复核" : "处理完成，质量门禁已通过");
      setSelectedDocument(result);
      await load();
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "重新处理失败");
    } finally {
      setBusyId(null);
    }
  };

  const pendingIds = useMemo(
    () => overview?.items.filter((item) => item.status === "pending" || item.status === "failed").map((item) => item.document_id) ?? [],
    [overview],
  );

  const columns: TableProps<ProcessingDocument>["columns"] = [
    {
      title: "采集材料",
      dataIndex: "title",
      width: 290,
      render: (_, item) => (
        <button className="processing-document-link" onClick={() => void openDetail(item)}>
          <strong>{item.title}</strong>
          <small>{item.source_name} · {formatTime(item.collected_at)}</small>
        </button>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value: ProcessingStatus) => statusTag(value),
    },
    {
      title: "质量",
      dataIndex: "quality_score",
      width: 130,
      render: (value: number, item) => (
        <div className="processing-quality-cell">
          <Progress percent={value} showInfo={false} strokeColor={qualityColor(value)} railColor="#ebe7df" size="small" />
          <span>{item.status === "pending" ? "尚未评分" : `${value} / 100`}</span>
        </div>
      ),
    },
    {
      title: "语言 / OCR",
      key: "language",
      width: 120,
      render: (_, item) => (
        <div className="processing-pair-cell">
          <strong>{item.language?.toUpperCase() ?? "—"}</strong>
          <small>{item.ocr_status === "completed" ? "OCR 已完成" : item.ocr_status === "not_required" ? "无需 OCR" : item.ocr_status === "unavailable" ? "OCR 不可用" : "OCR 失败"}</small>
        </div>
      ),
    },
    {
      title: "去重",
      key: "duplicate",
      width: 120,
      render: (_, item) => item.duplicate.type === "none" ? <span className="processing-muted">独立材料</span> : (
        <Tooltip title={item.duplicate.title ? `匹配：${item.duplicate.title}` : "已归入重复簇"}>
          <Tag color={item.duplicate.type === "exact" ? "purple" : "geekblue"}>
            {item.duplicate.type === "exact" ? "精确重复" : "近似重复"} {Math.round(item.duplicate.similarity * 100)}%
          </Tag>
        </Tooltip>
      ),
    },
    {
      title: "抽取结果",
      key: "extractions",
      width: 128,
      render: (_, item) => (
        <div className="processing-extraction-counts">
          <span><TagsOutlined /> {item.entity_count} 实体</span>
          <span><ApartmentOutlined /> {item.event_count} 事件</span>
        </div>
      ),
    },
    {
      title: "操作",
      key: "action",
      width: 122,
      fixed: "right",
      render: (_, item) => (
        <Space size={2}>
          <Button type="link" size="small" onClick={() => void openDetail(item)}>详情</Button>
          <Tooltip title="按当前处理配置重跑">
            <Button
              type="text"
              size="small"
              icon={busyId === item.document_id ? <LoadingOutlined /> : <ReloadOutlined />}
              disabled={Boolean(busyId)}
              onClick={() => void rerunDocument(item)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const summary = overview?.summary;
  const detailTabs = selectedDocument ? [
    {
      key: "text",
      label: `清洗正文 (${selectedDocument.clean_text.length})`,
      children: selectedDocument.clean_text ? (
        <article className="processing-clean-text">{selectedDocument.clean_text}</article>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚无可用正文" />
      ),
    },
    {
      key: "entities",
      label: `实体 (${selectedDocument.entities.length})`,
      children: selectedDocument.entities.length ? (
        <div className="processing-entity-list">
          {selectedDocument.entities.map((entity) => (
            <article key={entity.id}>
              <Tag>{entityLabels[entity.type]}</Tag>
              <div><strong>{entity.text}</strong><small>位置 {entity.start}–{entity.end} · {entity.method}</small></div>
              <span>{Math.round(entity.confidence * 100)}%</span>
            </article>
          ))}
        </div>
      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未抽取到实体" />,
    },
    {
      key: "events",
      label: `事件 (${selectedDocument.events.length})`,
      children: selectedDocument.events.length ? (
        <div className="processing-event-list">
          {selectedDocument.events.map((event) => (
            <article key={event.id}>
              <div>{eventTag(event)}<span>置信度 {Math.round(event.confidence * 100)}%</span></div>
              <strong>{event.subject ?? "主体待确认"}{event.object ? ` · ${event.object}` : ""}</strong>
              <p>“{event.evidence_text}”</p>
              <small>原文位置 {event.start}–{event.end}{event.occurred_at ? ` · 发生时间 ${event.occurred_at}` : ""}</small>
            </article>
          ))}
        </div>
      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未识别到变化事件" />,
    },
  ] : [];

  return (
    <div className="data-processing">
      {contextHolder}
      <section className="processing-page-heading">
        <div>
          <div className="eyebrow">DATA QUALITY · {project.name}</div>
          <h1>数据清洗与信息抽取</h1>
          <p>正文提取、去噪、跨来源去重、语言识别、OCR，以及带证据位置的实体与事件抽取。</p>
        </div>
        <Space wrap>
          <Button icon={<SettingOutlined />} onClick={() => setSettingsOpen(true)}>处理设置</Button>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={busy}
            disabled={!pendingIds.length}
            onClick={() => void processDocuments(pendingIds)}
          >处理待处理材料 ({pendingIds.length})</Button>
        </Space>
      </section>

      <section className="processing-summary-grid" aria-label="处理概览">
        <article><span className="processing-summary-icon"><CheckCircleFilled /></span><div><small>已处理材料</small><strong>{summary?.processed ?? 0}<em>/ {summary?.total ?? 0}</em></strong><p>{summary?.pending ?? 0} 条等待处理</p></div></article>
        <article><span className="processing-summary-icon processing-summary-icon--duplicate"><CopyOutlined /></span><div><small>重复材料</small><strong>{summary?.duplicates ?? 0}</strong><p>精确与近似重复归并</p></div></article>
        <article><span className="processing-summary-icon processing-summary-icon--entity"><TagsOutlined /></span><div><small>已抽取实体</small><strong>{summary?.entities ?? 0}</strong><p>{summary?.events ?? 0} 个变化事件</p></div></article>
        <article className={(summary?.review_required ?? 0) > 0 ? "processing-summary-card--alert" : ""}><span className="processing-summary-icon processing-summary-icon--review"><WarningFilled /></span><div><small>待人工复核</small><strong>{summary?.review_required ?? 0}</strong><p>{summary?.failed ?? 0} 条处理失败 · {summary?.ocr_completed ?? 0} 条完成 OCR</p></div></article>
      </section>

      <section className="processing-pipeline-panel">
        <div className="processing-panel-head"><div><span className="panel-kicker">PROCESSING PIPELINE</span><h2>可追溯处理链</h2><p>每一步记录方法、耗时、输出摘要与质量门禁结论。</p></div><Tag color="green">processor v1</Tag></div>
        <div className="processing-pipeline">
          {pipeline.map((step, index) => (
            <div className="processing-pipeline-fragment" key={step.label}>
              <article><span>{step.icon}</span><div><small>0{index + 1}</small><strong>{step.label}</strong><p>{step.note}</p></div></article>
              {index < pipeline.length - 1 && <i>→</i>}
            </div>
          ))}
        </div>
      </section>

      <section className="processing-table-panel">
        <div className="processing-table-toolbar">
          <Space wrap>
            <Input.Search
              value={query}
              allowClear
              prefix={<FileSearchOutlined />}
              placeholder="搜索标题、来源或正文"
              onChange={(event) => setQuery(event.target.value)}
              onSearch={(value) => setAppliedQuery(value.trim())}
            />
            <Select
              value={statusFilter}
              suffixIcon={<FilterOutlined />}
              onChange={setStatusFilter}
              options={[
                { value: "all", label: "全部状态" },
                ...Object.entries(statusMeta).map(([value, meta]) => ({ value, label: meta.label })),
              ]}
            />
          </Space>
          <Space wrap>
            <span className="processing-selection-note">已选 {selectedKeys.length} 条</span>
            <Button disabled={!selectedKeys.length || busy} onClick={() => void processDocuments(selectedKeys.map(String))}>按当前配置重跑</Button>
            <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button>
          </Space>
        </div>
        <Table<ProcessingDocument>
          rowKey="document_id"
          loading={loading}
          dataSource={overview?.items ?? []}
          columns={columns}
          rowSelection={{ selectedRowKeys: selectedKeys, onChange: setSelectedKeys }}
          pagination={{ pageSize: 10, showSizeChanger: false, showTotal: (total) => `共 ${total} 条` }}
          scroll={{ x: 1120 }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无采集材料，请先在数据运营中完成采集或文件上传" /> }}
        />
      </section>

      <Drawer
        title="处理结果与证据"
        size={620}
        open={Boolean(selectedDocument)}
        onClose={() => setSelectedDocument(null)}
        className="processing-detail-drawer"
        extra={selectedDocument && <Button icon={<ReloadOutlined />} loading={busyId === selectedDocument.document_id} onClick={() => void rerunDocument(selectedDocument)}>重新处理</Button>}
      >
        <Spin spinning={detailLoading}>
          {selectedDocument && (
            <>
              <div className={`processing-detail-hero processing-detail-hero--${selectedDocument.status}`}>
                <span>{selectedDocument.status === "completed" ? <CheckCircleFilled /> : <WarningFilled />}</span>
                <div><Space>{statusTag(selectedDocument.status)}<Tag>{selectedDocument.source_name}</Tag></Space><h3>{selectedDocument.title}</h3><p>处理于 {formatTime(selectedDocument.processed_at)} · {selectedDocument.processor_version}</p></div>
                <strong>{selectedDocument.quality_score}<small>/100</small></strong>
              </div>
              {selectedDocument.review_reasons.length > 0 && (
                <Alert type="warning" showIcon message="需要人工复核" description={selectedDocument.review_reasons.join("；")} />
              )}
              {selectedDocument.error_message && <Alert type="error" showIcon message="处理失败" description={selectedDocument.error_message} />}
              {selectedDocument.duplicate.type !== "none" && (
                <Alert
                  type="info"
                  showIcon
                  message={`${selectedDocument.duplicate.type === "exact" ? "精确" : "近似"}重复 · 相似度 ${Math.round(selectedDocument.duplicate.similarity * 100)}%`}
                  description={`已归入 ${selectedDocument.duplicate.cluster_id}${selectedDocument.duplicate.title ? `，匹配材料：${selectedDocument.duplicate.title}` : ""}`}
                />
              )}
              <Descriptions size="small" column={2} bordered className="processing-descriptions" items={[
                { key: "language", label: "语言", children: `${selectedDocument.language?.toUpperCase() ?? "未知"} · ${Math.round(selectedDocument.language_confidence * 100)}%` },
                { key: "ocr", label: "OCR", children: selectedDocument.ocr_status },
                { key: "method", label: "正文方法", children: selectedDocument.body_extraction_method },
                { key: "noise", label: "去噪", children: `移除 ${selectedDocument.noise_removed_lines} 行` },
              ]} />
              <h4 className="processing-drawer-title">处理链路</h4>
              <Timeline items={selectedDocument.steps.map((step) => ({
                color: step.status === "completed" ? "green" : step.status === "warning" || step.status === "failed" ? "red" : "gray",
                content: <div className="processing-step-detail"><div><strong>{step.label}</strong><span>{step.duration_ms} ms</span></div><p>{step.summary}</p></div>,
              }))} />
              <Tabs items={detailTabs} className="processing-detail-tabs" />
            </>
          )}
        </Spin>
      </Drawer>

      <Drawer title="处理设置" size={430} open={settingsOpen} onClose={() => setSettingsOpen(false)} className="processing-settings-drawer">
        <Alert type="info" showIcon message="原始材料始终只读" description="重跑只会更新独立的处理结果与版本信息，不会改写采集快照。" />
        <div className="processing-option-list">
          {optionLabels.map((item) => (
            <label key={item.key}>
              <Checkbox
                checked={options[item.key]}
                onChange={(event) => setOptions((current) => ({ ...current, [item.key]: event.target.checked }))}
              />
              <span><strong>{item.label}</strong><small>{item.note}</small></span>
            </label>
          ))}
        </div>
        <Button block onClick={() => setOptions({ ...defaultProcessingOptions })}>恢复默认设置</Button>
      </Drawer>
    </div>
  );
}
