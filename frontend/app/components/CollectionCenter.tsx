"use client";

import {
  CheckCircleFilled,
  ClockCircleOutlined,
  CloseCircleFilled,
  CloudDownloadOutlined,
  EyeOutlined,
  InboxOutlined,
  ReloadOutlined,
  RetweetOutlined,
  StopOutlined,
  SyncOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  Button,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
  Upload,
  message,
  type TableProps,
  type UploadFile,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  cancelCollectionRun,
  collectionDocumentRawUrl,
  fetchCollectionDocument,
  fetchCollectionDocuments,
  fetchCollectionRuns,
  retryCollectionRun,
  uploadCollectionFile,
  type CollectionDocument,
  type CollectionDocumentDetail,
  type CollectionDocumentListResponse,
  type CollectionRun,
  type CollectionRunListResponse,
  type CollectionRunStatus,
  type DataSource,
} from "../lib/api";

type Props = {
  projectId: string;
  sources: DataSource[];
  onRefresh: () => Promise<void>;
};

const runStatusMeta: Record<CollectionRunStatus, { label: string; color: string }> = {
  queued: { label: "待执行", color: "default" },
  running: { label: "运行中", color: "processing" },
  succeeded: { label: "成功", color: "success" },
  partial: { label: "部分成功", color: "warning" },
  failed: { label: "失败", color: "error" },
  cancelled: { label: "已取消", color: "default" },
  manual_review: { label: "待人工处理", color: "warning" },
};

const triggerLabels: Record<CollectionRun["trigger_type"], string> = {
  manual: "立即采集",
  scheduled: "计划任务",
  event: "事件触发",
  api: "API 触发",
  upload: "文件上传",
  retry: "失败重试",
  recovery: "异常恢复",
};

function formatDateTime(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function runProgress(run: CollectionRun) {
  if (run.status === "queued") return 8;
  if (run.status === "running") return 55;
  if (run.status === "succeeded" || run.status === "partial") return 100;
  return 0;
}

export default function CollectionCenter({ projectId, sources, onRefresh }: Props) {
  const [runs, setRuns] = useState<CollectionRunListResponse | null>(null);
  const [documents, setDocuments] = useState<CollectionDocumentListResponse | null>(null);
  const [selectedRun, setSelectedRun] = useState<CollectionRun | null>(null);
  const [selectedDocument, setSelectedDocument] = useState<CollectionDocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [runStatusFilter, setRunStatusFilter] = useState<CollectionRunStatus | "all">("all");
  const [documentSearch, setDocumentSearch] = useState("");
  const [appliedDocumentSearch, setAppliedDocumentSearch] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [uploadForm] = Form.useForm<{
    name: string;
    subject: string;
    authorization_basis: string;
    retention_days: number;
  }>();
  const [messageApi, messageContext] = message.useMessage();

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const [runResult, documentResult] = await Promise.all([
        fetchCollectionRuns(projectId, {
          sourceId: sourceFilter === "all" ? undefined : sourceFilter,
          status: runStatusFilter === "all" ? undefined : runStatusFilter,
        }),
        fetchCollectionDocuments(projectId, {
          sourceId: sourceFilter === "all" ? undefined : sourceFilter,
          query: appliedDocumentSearch || undefined,
        }),
      ]);
      setRuns(runResult);
      setDocuments(documentResult);
      setSelectedRun((current) => current ? runResult.items.find((item) => item.id === current.id) ?? current : null);
    } catch (error) {
      if (!quiet) messageApi.error(error instanceof Error ? error.message : "采集中心加载失败");
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [appliedDocumentSearch, messageApi, projectId, runStatusFilter, sourceFilter]);

  useEffect(() => {
    const timeout = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timeout);
  }, [load]);

  const hasActiveRun = useMemo(
    () => runs?.items.some((run) => run.status === "queued" || run.status === "running") ?? false,
    [runs],
  );

  useEffect(() => {
    if (!hasActiveRun) return;
    const interval = window.setInterval(() => void load(true), 3000);
    return () => window.clearInterval(interval);
  }, [hasActiveRun, load]);

  useEffect(() => {
    if (uploadOpen) uploadForm.setFieldsValue({ retention_days: 365 });
  }, [uploadForm, uploadOpen]);

  const retryRun = async (run: CollectionRun) => {
    setBusyId(run.id);
    try {
      await retryCollectionRun(run.id);
      messageApi.success("重试任务已进入队列");
      await Promise.all([load(true), onRefresh()]);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "重试失败");
    } finally {
      setBusyId(null);
    }
  };

  const cancelRun = async (run: CollectionRun) => {
    setBusyId(run.id);
    try {
      await cancelCollectionRun(run.id);
      messageApi.success("任务已取消");
      await load(true);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "取消失败");
    } finally {
      setBusyId(null);
    }
  };

  const openDocument = async (document: CollectionDocument) => {
    setBusyId(document.id);
    try {
      setSelectedDocument(await fetchCollectionDocument(document.id));
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "材料加载失败");
    } finally {
      setBusyId(null);
    }
  };

  const openUpload = () => {
    setFileList([]);
    setUploadOpen(true);
  };

  const submitUpload = async () => {
    try {
      const values = await uploadForm.validateFields();
      const originFile = fileList[0]?.originFileObj;
      if (!originFile) {
        messageApi.warning("请选择要采集的文件");
        return;
      }
      setUploading(true);
      await uploadCollectionFile({
        projectId,
        name: values.name,
        subject: values.subject,
        authorizationBasis: values.authorization_basis,
        retentionDays: values.retention_days,
        file: originFile,
      });
      setUploadOpen(false);
      messageApi.success("文件已上传，解析任务正在执行");
      await Promise.all([load(true), onRefresh()]);
    } catch (error) {
      if (error instanceof Error) messageApi.error(error.message);
    } finally {
      setUploading(false);
    }
  };

  const runColumns: TableProps<CollectionRun>["columns"] = [
    {
      title: "任务 / 来源",
      dataIndex: "source_name",
      width: 230,
      render: (_, run) => (
        <button className="collection-name-button" onClick={() => setSelectedRun(run)}>
          <strong>{run.source_name}</strong>
          <small>{run.id} · {triggerLabels[run.trigger_type]}</small>
        </button>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 125,
      render: (value: CollectionRunStatus, run) => (
        <div className="collection-status-cell">
          <Tag variant="filled" color={runStatusMeta[value].color}>{runStatusMeta[value].label}</Tag>
          <Progress percent={runProgress(run)} showInfo={false} size="small" status={value === "failed" ? "exception" : undefined} />
        </div>
      ),
    },
    {
      title: "结果",
      key: "result",
      width: 190,
      render: (_, run) => (
        <span className="collection-result-copy">
          <strong>{run.documents_created} 新增 · {run.documents_updated} 更新</strong>
          <small>{run.duplicates_skipped} 条重复跳过 · 发现 {run.items_discovered} 条</small>
        </span>
      ),
    },
    {
      title: "重试",
      dataIndex: "attempt",
      width: 85,
      align: "center",
      render: (value: number, run) => `${value}/${run.max_attempts}`,
    },
    {
      title: "时间",
      dataIndex: "created_at",
      width: 150,
      render: (value: string, run) => (
        <span className="collection-result-copy"><strong>{formatDateTime(value)}</strong><small>{run.finished_at ? `完成 ${formatDateTime(run.finished_at)}` : "等待完成"}</small></span>
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 105,
      align: "right",
      render: (_, run) => (
        <Space size={2}>
          <Tooltip title="查看日志"><Button type="text" size="small" icon={<EyeOutlined />} onClick={() => setSelectedRun(run)} /></Tooltip>
          {run.status === "queued" && <Tooltip title="取消"><Button type="text" size="small" danger icon={<StopOutlined />} loading={busyId === run.id} onClick={() => void cancelRun(run)} /></Tooltip>}
          {["failed", "partial", "cancelled"].includes(run.status) && <Tooltip title="重试"><Button type="text" size="small" icon={<RetweetOutlined />} loading={busyId === run.id} onClick={() => void retryRun(run)} /></Tooltip>}
        </Space>
      ),
    },
  ];

  const documentColumns: TableProps<CollectionDocument>["columns"] = [
    {
      title: "采集材料",
      dataIndex: "title",
      width: 330,
      render: (_, document) => (
        <button className="collection-name-button" onClick={() => void openDocument(document)}>
          <strong>{document.title}</strong>
          <small>{document.readable_excerpt || "暂无正文摘要"}</small>
        </button>
      ),
    },
    {
      title: "来源",
      dataIndex: "source_name",
      width: 180,
      render: (value: string, document) => <span className="collection-result-copy"><strong>{value}</strong><small>{document.content_type}</small></span>,
    },
    { title: "版本", dataIndex: "version", width: 85, align: "center", render: (value: number) => <Tag variant="filled">v{value}</Tag> },
    { title: "正文", dataIndex: "word_count", width: 95, align: "right", render: (value: number) => `${value.toLocaleString()} 词` },
    { title: "采集时间", dataIndex: "collected_at", width: 150, render: (value: string) => formatDateTime(value) },
    { title: "", key: "action", width: 55, render: (_, document) => <Button type="text" icon={<EyeOutlined />} loading={busyId === document.id} onClick={() => void openDocument(document)} /> },
  ];

  const sourceOptions = [
    { value: "all", label: "全部来源" },
    ...sources.map((source) => ({ value: source.id, label: source.name })),
  ];

  return (
    <section className="collection-center">
      {messageContext}
      <div className="collection-center-head">
        <div><span className="eyebrow">COLLECTION PIPELINE</span><h2>采集任务与原始材料</h2><p>跟踪抓取、重试、指纹去重、版本留存与解析结果。</p></div>
        <Space><Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button><Button type="primary" icon={<UploadOutlined />} onClick={openUpload}>上传文件采集</Button></Space>
      </div>

      <div className="collection-filter-row">
        <Select value={sourceFilter} onChange={setSourceFilter} options={sourceOptions} className="collection-filter" showSearch optionFilterProp="label" />
        <Select value={runStatusFilter} onChange={setRunStatusFilter} className="collection-filter" options={[{ value: "all", label: "全部任务状态" }, ...Object.entries(runStatusMeta).map(([value, meta]) => ({ value, label: meta.label }))]} />
      </div>

      <Tabs
        className="collection-tabs"
        items={[
          {
            key: "runs",
            label: `采集任务 ${runs?.summary.total ?? 0}`,
            children: runs?.items.length ? <Table rowKey="id" columns={runColumns} dataSource={runs.items} loading={loading} pagination={{ pageSize: 6, hideOnSinglePage: true }} scroll={{ x: 980 }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有采集任务" />,
          },
          {
            key: "documents",
            label: `原始材料 ${documents?.summary.total ?? 0}`,
            children: (
              <div>
                <Input.Search className="collection-document-search" value={documentSearch} onChange={(event) => setDocumentSearch(event.target.value)} onSearch={(value) => setAppliedDocumentSearch(value.trim())} allowClear placeholder="搜索标题或正文…" />
                {documents?.items.length ? <Table rowKey="id" columns={documentColumns} dataSource={documents.items} loading={loading} pagination={{ pageSize: 6, hideOnSinglePage: true }} scroll={{ x: 980 }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="完成一次采集后，原始材料会显示在这里" />}
              </div>
            ),
          },
        ]}
      />

      <Drawer title={selectedRun ? `采集任务 · ${selectedRun.source_name}` : "采集任务"} open={Boolean(selectedRun)} onClose={() => setSelectedRun(null)} size={560} className="collection-detail-drawer">
        {selectedRun && (
          <>
            <div className={`collection-run-hero collection-run-hero--${selectedRun.status}`}>
              {selectedRun.status === "succeeded" ? <CheckCircleFilled /> : selectedRun.status === "failed" ? <CloseCircleFilled /> : selectedRun.status === "running" ? <SyncOutlined spin /> : <ClockCircleOutlined />}
              <div><Tag color={runStatusMeta[selectedRun.status].color}>{runStatusMeta[selectedRun.status].label}</Tag><h3>{selectedRun.request_summary ?? selectedRun.id}</h3><p>{selectedRun.error_message ?? `发现 ${selectedRun.items_discovered} 条，新增 ${selectedRun.documents_created} 条，更新 ${selectedRun.documents_updated} 条。`}</p></div>
            </div>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="触发方式">{triggerLabels[selectedRun.trigger_type]}</Descriptions.Item>
              <Descriptions.Item label="尝试次数">{selectedRun.attempt}/{selectedRun.max_attempts}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatDateTime(selectedRun.started_at)}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{formatDateTime(selectedRun.finished_at)}</Descriptions.Item>
              <Descriptions.Item label="错误类型" span={2}>{selectedRun.error_type ?? "—"}</Descriptions.Item>
            </Descriptions>
            <h4 className="collection-drawer-title">处理链路</h4>
            <Timeline items={(selectedRun.parser_steps.length ? selectedRun.parser_steps : ["任务等待执行"]).map((step, index) => ({ color: index === selectedRun.parser_steps.length - 1 && selectedRun.status === "failed" ? "red" : "green", children: step }))} />
          </>
        )}
      </Drawer>

      <Drawer title={selectedDocument?.title ?? "采集材料"} open={Boolean(selectedDocument)} onClose={() => setSelectedDocument(null)} size={640} className="collection-detail-drawer" extra={selectedDocument && <Button icon={<CloudDownloadOutlined />} href={collectionDocumentRawUrl(selectedDocument.id)}>下载原始快照</Button>}>
        {selectedDocument && (
          <>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="来源">{selectedDocument.source_name}</Descriptions.Item>
              <Descriptions.Item label="版本">v{selectedDocument.version}</Descriptions.Item>
              <Descriptions.Item label="采集时间">{formatDateTime(selectedDocument.collected_at)}</Descriptions.Item>
              <Descriptions.Item label="内容指纹"><Tooltip title={selectedDocument.content_hash}>{selectedDocument.content_hash.slice(0, 14)}…</Tooltip></Descriptions.Item>
              <Descriptions.Item label="规范地址" span={2}><a href={selectedDocument.canonical_url} target="_blank" rel="noreferrer">{selectedDocument.canonical_url}</a></Descriptions.Item>
            </Descriptions>
            <h4 className="collection-drawer-title">可读正文</h4>
            <article className="collection-document-body">{selectedDocument.readable_text}</article>
            <h4 className="collection-drawer-title">结构化字段</h4>
            <pre className="collection-json">{JSON.stringify(selectedDocument.structured_fields, null, 2)}</pre>
            <h4 className="collection-drawer-title">采集元数据</h4>
            <pre className="collection-json">{JSON.stringify(selectedDocument.metadata, null, 2)}</pre>
          </>
        )}
      </Drawer>

      <Modal title="上传文件并立即采集" open={uploadOpen} onCancel={() => setUploadOpen(false)} onOk={() => void submitUpload()} confirmLoading={uploading} okText="上传并采集" cancelText="取消" width={620} styles={{ body: { maxHeight: "calc(100vh - 220px)", overflowY: "auto" } }} forceRender destroyOnHidden>
        <div className="source-form-note"><InboxOutlined /> 文件会保存原始快照并提取可读正文；同内容再次上传会按指纹跳过。</div>
        <Form form={uploadForm} layout="vertical">
          <Form.Item label="选择文件" required>
            <Upload.Dragger beforeUpload={(file) => { setFileList([{ ...file, uid: file.uid, originFileObj: file }]); if (!uploadForm.getFieldValue("name")) uploadForm.setFieldValue("name", file.name); return false; }} fileList={fileList} onRemove={() => { setFileList([]); return true; }} maxCount={1} accept=".txt,.md,.html,.htm,.json,.csv,.xml,.rss,.atom,.pdf,.docx,.xlsx">
              <p className="ant-upload-drag-icon"><InboxOutlined /></p><p className="ant-upload-text">点击或拖拽文件到这里</p><p className="ant-upload-hint">支持 TXT、Markdown、HTML、JSON、CSV、XML、PDF、DOCX、XLSX</p>
            </Upload.Dragger>
          </Form.Item>
          <Form.Item name="name" label="来源名称" rules={[{ required: true, message: "请填写来源名称" }]}><Input placeholder="例如：季度产品价格表" /></Form.Item>
          <Form.Item name="subject" label="来源主体" rules={[{ required: true, message: "请填写来源主体" }]}><Input placeholder="文件所属企业或团队" /></Form.Item>
          <Form.Item name="authorization_basis" label="授权依据" rules={[{ required: true, message: "请登记文件使用依据" }]}><Input.TextArea rows={2} placeholder="例如：内部业务资料，经项目负责人授权" /></Form.Item>
          <Form.Item name="retention_days" label="保留天数" rules={[{ required: true }]}><InputNumber min={1} max={3650} style={{ width: "100%" }} /></Form.Item>
        </Form>
      </Modal>
    </section>
  );
}
