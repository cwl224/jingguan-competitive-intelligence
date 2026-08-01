"use client";

import {
  ApiOutlined,
  ArrowLeftOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  CloudSyncOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  ExclamationCircleFilled,
  FileAddOutlined,
  KeyOutlined,
  LinkOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
  WarningFilled,
} from "@ant-design/icons";
import {
  Button,
  Checkbox,
  Col,
  Descriptions,
  Drawer,
  Dropdown,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
  message,
  type TableProps,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import CollectionCenter from "./CollectionCenter";
import {
  createSource,
  deleteSource,
  fetchSources,
  rotateSourceCredential,
  runSourceChecks,
  runSourceNow,
  setSourceStatus,
  updateSource,
  type DataSource,
  type Project,
  type SourceCreatePayload,
  type SourceListResponse,
  type SourceStatus,
  type SourceType,
  type SourceUpdatePayload,
} from "../lib/api";

type Props = {
  project: Project;
  onBack: () => void;
  onDashboardRefresh: () => Promise<void>;
};

type SourceFormValues = Omit<SourceCreatePayload, "project_id">;

const sourceTypeLabels: Record<SourceType, string> = {
  webpage: "静态网页",
  dynamic_webpage: "动态网页",
  sitemap: "站点地图",
  rss: "RSS",
  public_api: "公开 API",
  social_api: "授权社媒 API",
  public_database: "公开数据库",
  file_upload: "上传文件",
};

const statusMeta: Record<SourceStatus, { label: string; color: string }> = {
  healthy: { label: "正常", color: "green" },
  warning: { label: "关注", color: "gold" },
  error: { label: "异常", color: "red" },
  disabled: { label: "停用", color: "default" },
};

const authorizationMeta: Record<DataSource["authorization_status"], { label: string; color: string }> = {
  approved: { label: "已授权", color: "green" },
  pending: { label: "待确认", color: "gold" },
  expired: { label: "已过期", color: "red" },
  rejected: { label: "已拒绝", color: "red" },
};

const frequencyLabels: Record<DataSource["schedule_frequency"], string> = {
  manual: "仅手动",
  "15m": "每 15 分钟",
  hourly: "每小时",
  "6h": "每 6 小时",
  daily: "每天",
  weekly: "每周",
};

const regionLabels: Record<string, string> = {
  cn: "中国",
  global: "全球",
  jp: "日本",
  sea: "东南亚",
  eu: "欧洲",
  us: "美国",
};

const defaultSourceValues: SourceFormValues = {
  name: "",
  source_type: "webpage",
  endpoint: "",
  subject: "",
  access_method: "public",
  crawl_strategy: "增量采集",
  regions: ["global"],
  authorization_basis: "",
  authorization_status: "pending",
  data_classification: "public",
  retention_days: 365,
  schedule_frequency: "daily",
  rate_limit_per_minute: 30,
  credential_ref: null,
  credential_expires_at: null,
  fields_available: [],
  collection_config: { max_items: 50, timeout_seconds: 20 },
  robots_acknowledged: false,
  terms_acknowledged: false,
};

function formatDateTime(value: string | null) {
  if (!value) return "尚无记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function healthColor(score: number) {
  if (score >= 85) return "#687c67";
  if (score >= 70) return "#bd8a60";
  return "#b76554";
}

export default function DataSourceManagement({ project, onBack, onDashboardRefresh }: Props) {
  const [data, setData] = useState<SourceListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<SourceStatus | "all">("all");
  const [sourceTypeFilter, setSourceTypeFilter] = useState<SourceType | "all">("all");
  const [searchText, setSearchText] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [selectedSource, setSelectedSource] = useState<DataSource | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<DataSource | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [busySourceId, setBusySourceId] = useState<string | null>(null);
  const [rotationSource, setRotationSource] = useState<DataSource | null>(null);
  const [credentialRef, setCredentialRef] = useState("");
  const [credentialExpiry, setCredentialExpiry] = useState("");
  const [rotating, setRotating] = useState(false);
  const [form] = Form.useForm<SourceFormValues>();
  const formSourceType = Form.useWatch("source_type", form) ?? "webpage";
  const [messageApi, messageContext] = message.useMessage();
  const [modalApi, modalContext] = Modal.useModal();

  const loadSources = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchSources(project.id, {
        status: statusFilter === "all" ? undefined : statusFilter,
        sourceType: sourceTypeFilter === "all" ? undefined : sourceTypeFilter,
        query: appliedSearch || undefined,
      });
      setData(result);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "数据源加载失败");
    } finally {
      setLoading(false);
    }
  }, [appliedSearch, project.id, sourceTypeFilter, statusFilter]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadSources(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadSources]);

  const refresh = async () => {
    await Promise.all([loadSources(), onDashboardRefresh()]);
  };

  const openCreate = () => {
    setEditingSource(null);
    form.setFieldsValue(defaultSourceValues);
    setFormOpen(true);
  };

  const openEdit = (source: DataSource) => {
    setEditingSource(source);
    form.setFieldsValue({
      name: source.name,
      source_type: source.source_type,
      endpoint: source.endpoint,
      subject: source.subject,
      access_method: source.access_method,
      crawl_strategy: source.crawl_strategy,
      regions: source.regions,
      authorization_basis: source.authorization_basis,
      authorization_status: source.authorization_status,
      data_classification: source.data_classification,
      retention_days: source.retention_days,
      schedule_frequency: source.schedule_frequency,
      rate_limit_per_minute: source.rate_limit_per_minute,
      credential_ref: null,
      credential_expires_at: source.credential_expires_at,
      fields_available: source.fields_available,
      collection_config: source.collection_config,
      robots_acknowledged: source.robots_acknowledged,
      terms_acknowledged: source.terms_acknowledged,
    });
    setFormOpen(true);
  };

  const submitSource = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      if (editingSource) {
        const payload: SourceUpdatePayload = { ...values };
        if (!values.credential_ref) delete payload.credential_ref;
        await updateSource(editingSource.id, payload);
        messageApi.success("数据源配置已保存；关键配置变更后需重新检查再启用");
      } else {
        await createSource({ ...values, project_id: project.id });
        messageApi.success("数据源已创建为停用状态，请完成启用前检查");
      }
      setFormOpen(false);
      form.resetFields();
      await refresh();
    } catch (submitError) {
      if (submitError instanceof Error) messageApi.error(submitError.message);
    } finally {
      setSubmitting(false);
    }
  };

  const performSourceAction = async (
    source: DataSource,
    action: () => Promise<{ item: DataSource; message: string }>,
  ) => {
    setBusySourceId(source.id);
    try {
      const result = await action();
      setSelectedSource((current) => current?.id === source.id ? result.item : current);
      messageApi.success(result.message);
      await refresh();
    } catch (actionError) {
      messageApi.error(actionError instanceof Error ? actionError.message : "操作失败");
    } finally {
      setBusySourceId(null);
    }
  };

  const toggleSource = (source: DataSource, enabled: boolean) => {
    if (enabled && !source.activation_ready) {
      setSelectedSource(source);
      messageApi.warning("请先执行启用前检查，并修复未通过项");
      return;
    }
    if (!enabled) {
      modalApi.confirm({
        title: "停用这个数据源？",
        icon: <StopOutlined />,
        content: "停用后不会再发起新的计划或手动采集，历史数据仍会保留。",
        okText: "确认停用",
        cancelText: "取消",
        okButtonProps: { danger: true },
        onOk: () => performSourceAction(source, () => setSourceStatus(source.id, false)),
      });
      return;
    }
    void performSourceAction(source, () => setSourceStatus(source.id, true));
  };

  const runNow = async (source: DataSource) => {
    setBusySourceId(source.id);
    try {
      await runSourceNow(source.id);
      messageApi.success("采集任务已进入队列");
      await refresh();
    } catch (runError) {
      messageApi.error(runError instanceof Error ? runError.message : "采集任务创建失败");
    } finally {
      setBusySourceId(null);
    }
  };

  const confirmDelete = (source: DataSource) => {
    modalApi.confirm({
      title: `归档“${source.name}”？`,
      icon: <ExclamationCircleFilled />,
      content: "只能归档已停用的数据源。归档后不会再参与采集和检索，来源配置、运行记录、历史情报与证据仍会保留。",
      okText: "确认归档",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteSource(source.id);
          setSelectedSource(null);
          messageApi.success("数据源已归档，历史运行与证据仍保留");
          await refresh();
        } catch (deleteError) {
          messageApi.error(deleteError instanceof Error ? deleteError.message : "归档失败");
        }
      },
    });
  };

  const openRotation = (source: DataSource) => {
    setRotationSource(source);
    setCredentialRef("");
    setCredentialExpiry("");
  };

  const rotateCredential = async () => {
    if (!rotationSource || !credentialRef.trim()) {
      messageApi.warning("请填写新的密钥服务引用");
      return;
    }
    setRotating(true);
    try {
      const result = await rotateSourceCredential(
        rotationSource.id,
        credentialRef.trim(),
        credentialExpiry ? new Date(credentialExpiry).toISOString() : null,
      );
      setSelectedSource((current) => current?.id === rotationSource.id ? result.item : current);
      setRotationSource(null);
      messageApi.success(result.message);
      await refresh();
    } catch (rotationError) {
      messageApi.error(rotationError instanceof Error ? rotationError.message : "凭据轮换失败");
    } finally {
      setRotating(false);
    }
  };

  const columns: TableProps<DataSource>["columns"] = [
    {
      title: "数据源",
      dataIndex: "name",
      width: 280,
      render: (_, source) => (
        <button className="source-name-button" onClick={() => setSelectedSource(source)}>
          <span className={`source-type-icon source-type-icon--${source.source_type}`}>
            {source.source_type.includes("api") ? <ApiOutlined /> : source.source_type === "file_upload" ? <FileAddOutlined /> : <LinkOutlined />}
          </span>
          <span><strong>{source.name}</strong><small>{source.subject} · {source.endpoint}</small></span>
        </button>
      ),
    },
    {
      title: "类型",
      dataIndex: "source_type",
      width: 120,
      render: (value: SourceType) => <Tag variant="filled">{sourceTypeLabels[value]}</Tag>,
    },
    {
      title: "授权",
      dataIndex: "authorization_status",
      width: 110,
      render: (value: DataSource["authorization_status"]) => (
        <Tag variant="filled" color={authorizationMeta[value].color}>{authorizationMeta[value].label}</Tag>
      ),
    },
    {
      title: "健康度",
      dataIndex: "health_score",
      width: 150,
      render: (value: number, source) => (
        <div className="source-health-cell">
          <Progress type="circle" percent={source.status === "disabled" ? 0 : value} size={38} strokeWidth={8} strokeColor={healthColor(value)} format={() => source.status === "disabled" ? "—" : value} />
          <span><Tag variant="filled" color={statusMeta[source.status].color}>{statusMeta[source.status].label}</Tag><small>成功率 {source.health.success_rate.toFixed(1)}%</small></span>
        </div>
      ),
    },
    {
      title: "采集计划",
      dataIndex: "schedule_frequency",
      width: 130,
      render: (value: DataSource["schedule_frequency"], source) => (
        <span className="source-table-stack"><strong>{frequencyLabels[value]}</strong><small>{source.rate_limit_per_minute} 次/分钟</small></span>
      ),
    },
    {
      title: "最近成功",
      dataIndex: "last_success_at",
      width: 140,
      render: (value: string | null) => formatDateTime(value),
    },
    {
      title: "启用",
      dataIndex: "enabled",
      width: 78,
      align: "center",
      render: (value: boolean, source) => (
        <Switch
          size="small"
          checked={value}
          loading={busySourceId === source.id}
          onChange={(checked) => toggleSource(source, checked)}
          aria-label={`${value ? "停用" : "启用"}${source.name}`}
        />
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 118,
      fixed: "right",
      render: (_, source) => (
        <Space size={2}>
          <Tooltip title="立即采集"><Button type="text" size="small" icon={<PlayCircleOutlined />} disabled={!source.enabled} loading={busySourceId === source.id} onClick={() => void runNow(source)} /></Tooltip>
          <Tooltip title="运行检查"><Button type="text" size="small" icon={<SafetyCertificateOutlined />} loading={busySourceId === source.id} onClick={() => void performSourceAction(source, () => runSourceChecks(source.id))} /></Tooltip>
          <Dropdown
            trigger={["click"]}
            menu={{
              items: [
                { key: "detail", label: "查看详情" },
                { key: "edit", label: "编辑配置", icon: <EditOutlined /> },
                { key: "rotate", label: "轮换凭据", icon: <KeyOutlined />, disabled: source.access_method === "public" || source.access_method === "upload" },
                { type: "divider" },
                { key: "delete", label: "归档", icon: <DeleteOutlined />, danger: true },
              ],
              onClick: ({ key }) => {
                if (key === "detail") setSelectedSource(source);
                if (key === "edit") openEdit(source);
                if (key === "rotate") openRotation(source);
                if (key === "delete") confirmDelete(source);
              },
            }}
          >
            <Button type="text" size="small" icon={<MoreOutlined />} aria-label={`更多${source.name}操作`} />
          </Dropdown>
        </Space>
      ),
    },
  ];

  const summary = data?.summary;

  return (
    <div className="source-management">
      {messageContext}
      {modalContext}
      <section className="source-page-heading">
        <div>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack} className="source-back-button">返回工作台</Button>
          <div className="eyebrow">DATA OPERATIONS · {project.name}</div>
          <h1>数据源管理</h1>
          <p>登记来源、授权与保留策略，通过启用前检查后再进入采集队列。</p>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void refresh()} loading={loading}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增数据源</Button>
        </Space>
      </section>

      <section className="source-summary-grid" aria-label="数据源概览">
        <article><span className="source-summary-icon"><DatabaseOutlined /></span><div><small>来源总数</small><strong>{summary?.total ?? "—"}</strong><p>{summary?.enabled ?? 0} 个已启用</p></div></article>
        <article><span className="source-summary-icon source-summary-icon--good"><CheckCircleFilled /></span><div><small>整体健康度</small><strong>{summary ? `${summary.average_health}%` : "—"}</strong><p>仅统计已启用来源</p></div></article>
        <article><span className="source-summary-icon source-summary-icon--warn"><WarningFilled /></span><div><small>需要关注</small><strong>{summary?.needs_attention ?? "—"}</strong><p>{summary?.disabled ?? 0} 个来源已停用</p></div></article>
        <article><span className="source-summary-icon source-summary-icon--key"><KeyOutlined /></span><div><small>凭据提醒</small><strong>{summary?.expiring_credentials ?? "—"}</strong><p>30 天内到期或已过期</p></div></article>
      </section>

      <section className="source-list-panel">
        <div className="source-toolbar">
          <Input.Search
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            onSearch={(value) => setAppliedSearch(value.trim())}
            allowClear
            placeholder="搜索名称、主体或入口…"
            className="source-search"
          />
          <Select
            value={sourceTypeFilter}
            onChange={setSourceTypeFilter}
            className="source-filter-select"
            options={[{ value: "all", label: "全部类型" }, ...Object.entries(sourceTypeLabels).map(([value, label]) => ({ value, label }))]}
          />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            className="source-filter-select"
            options={[{ value: "all", label: "全部状态" }, ...Object.entries(statusMeta).map(([value, meta]) => ({ value, label: meta.label }))]}
          />
        </div>

        {error ? (
          <div className="source-error-state"><WarningFilled /><strong>数据源暂时无法加载</strong><span>{error}</span><Button onClick={() => void loadSources()}>重新加载</Button></div>
        ) : (
          <Table<DataSource>
            rowKey="id"
            columns={columns}
            dataSource={data?.items ?? []}
            loading={loading}
            scroll={{ x: 1200 }}
            pagination={{ pageSize: 8, hideOnSinglePage: true, showTotal: (total) => `共 ${total} 个来源` }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选条件下没有数据源" /> }}
          />
        )}
      </section>

      <CollectionCenter projectId={project.id} sources={data?.items ?? []} onRefresh={refresh} />

      <Drawer
        title={selectedSource?.name}
        size={520}
        open={Boolean(selectedSource)}
        onClose={() => setSelectedSource(null)}
        className="source-detail-drawer"
        extra={selectedSource && <Tag color={statusMeta[selectedSource.status].color}>{statusMeta[selectedSource.status].label}</Tag>}
      >
        {selectedSource && (
          <Spin spinning={busySourceId === selectedSource.id}>
            <div className="source-detail-lead">
              <span className={`source-type-icon source-type-icon--${selectedSource.source_type}`}><CloudSyncOutlined /></span>
              <div><strong>{sourceTypeLabels[selectedSource.source_type]} · {selectedSource.subject}</strong><a href={selectedSource.endpoint} target="_blank" rel="noreferrer">{selectedSource.endpoint} <LinkOutlined /></a></div>
            </div>

            <div className="source-detail-section-title">启用前检查</div>
            <div className="source-check-grid">
              {selectedSource.checks.map((check) => (
                <article key={check.key} className={`source-check source-check--${check.status}`}>
                  {check.status === "passed" ? <CheckCircleFilled /> : check.status === "failed" ? <WarningFilled /> : <ClockCircleOutlined />}
                  <div><strong>{check.label}</strong><span>{check.message}</span></div>
                </article>
              ))}
            </div>
            <Button block icon={<SafetyCertificateOutlined />} onClick={() => void performSourceAction(selectedSource, () => runSourceChecks(selectedSource.id))}>重新运行检查</Button>

            <div className="source-detail-section-title">健康指标</div>
            <div className="source-health-overview">
              <Progress type="dashboard" percent={selectedSource.status === "disabled" ? 0 : selectedSource.health_score} strokeColor={healthColor(selectedSource.health_score)} format={() => selectedSource.status === "disabled" ? "停用" : `${selectedSource.health_score}%`} />
              <div className="source-health-metrics">
                <span><small>任务成功率</small><strong>{selectedSource.health.success_rate.toFixed(1)}%</strong></span>
                <span><small>连续失败</small><strong>{selectedSource.health.consecutive_failures} 次</strong></span>
                <span><small>平均延迟</small><strong>{selectedSource.health.average_latency_ms} ms</strong></span>
                <span><small>数据新鲜度</small><strong>{selectedSource.health.freshness_minutes} 分钟</strong></span>
                <span><small>内容变化率</small><strong>{selectedSource.health.content_change_rate.toFixed(1)}%</strong></span>
                <span><small>解析完整度</small><strong>{selectedSource.health.parser_completeness.toFixed(1)}%</strong></span>
              </div>
            </div>

            <div className="source-detail-section-title">来源配置</div>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="访问方式">{selectedSource.access_method}</Descriptions.Item>
              <Descriptions.Item label="采集策略">{selectedSource.crawl_strategy}</Descriptions.Item>
              <Descriptions.Item label="计划 / 限流">{frequencyLabels[selectedSource.schedule_frequency]} · {selectedSource.rate_limit_per_minute} 次/分钟</Descriptions.Item>
              <Descriptions.Item label="适用地区">{selectedSource.regions.map((region) => regionLabels[region] ?? region).join("、")}</Descriptions.Item>
              <Descriptions.Item label="数据分类">{selectedSource.data_classification}</Descriptions.Item>
              <Descriptions.Item label="保留期限">{selectedSource.retention_days} 天</Descriptions.Item>
              <Descriptions.Item label="授权依据">{selectedSource.authorization_basis}</Descriptions.Item>
              <Descriptions.Item label="可用字段">{selectedSource.fields_available.join("、") || "未配置"}</Descriptions.Item>
              <Descriptions.Item label="最近成功">{formatDateTime(selectedSource.last_success_at)}</Descriptions.Item>
              <Descriptions.Item label="凭据">{selectedSource.credential_masked ?? "无需凭据"}{selectedSource.credential_expires_at ? ` · ${formatDateTime(selectedSource.credential_expires_at)} 到期` : ""}</Descriptions.Item>
            </Descriptions>

            <div className="source-drawer-actions">
              <Button icon={<EditOutlined />} onClick={() => openEdit(selectedSource)}>编辑</Button>
              {selectedSource.access_method !== "public" && selectedSource.access_method !== "upload" && <Button icon={<KeyOutlined />} onClick={() => openRotation(selectedSource)}>轮换凭据</Button>}
              <Button icon={<PlayCircleOutlined />} disabled={!selectedSource.enabled} onClick={() => void runNow(selectedSource)}>立即采集</Button>
              <Button type="primary" danger={selectedSource.enabled} onClick={() => toggleSource(selectedSource, !selectedSource.enabled)}>{selectedSource.enabled ? "停用" : "启用"}</Button>
            </div>
          </Spin>
        )}
      </Drawer>

      <Modal
        title={editingSource ? "编辑数据源" : "新增数据源"}
        width={760}
        open={formOpen}
        onCancel={() => setFormOpen(false)}
        onOk={() => void submitSource()}
        confirmLoading={submitting}
        okText={editingSource ? "保存配置" : "创建并继续检查"}
        cancelText="取消"
        forceRender
        destroyOnHidden
      >
        <div className="source-form-note"><SafetyCertificateOutlined /> 新来源默认停用；只有连通性、授权合规、限流和字段检查全部通过后才能启用。</div>
        <Form form={form} layout="vertical" initialValues={defaultSourceValues} className="source-form">
          <Row gutter={16}>
            <Col span={12}><Form.Item name="name" label="来源名称" rules={[{ required: true, message: "请填写来源名称" }]}><Input placeholder="例如：官方产品更新日志" /></Form.Item></Col>
            <Col span={12}><Form.Item name="subject" label="来源主体" rules={[{ required: true, message: "请填写来源主体" }]}><Input placeholder="企业、媒体或数据库名称" /></Form.Item></Col>
            <Col span={12}><Form.Item name="source_type" label="来源类型" rules={[{ required: true }]}><Select options={Object.entries(sourceTypeLabels).map(([value, label]) => ({ value, label, disabled: !editingSource && value === "file_upload" }))} /></Form.Item></Col>
            <Col span={12}><Form.Item name="access_method" label="访问方式" rules={[{ required: true }]}><Select options={[
              { value: "public", label: "公开访问" }, { value: "api_key", label: "API Key" }, { value: "oauth2", label: "OAuth 2.0" }, { value: "secret_ref", label: "密钥服务引用" }, { value: "upload", label: "上传文件" },
            ]} /></Form.Item></Col>
            <Col span={24}><Form.Item name="endpoint" label="入口 URL / 接口 / 文件标识" rules={[{ required: true, message: "请填写来源入口" }]}><Input placeholder="https://example.com/news 或文件批次标识" /></Form.Item></Col>
            <Col span={12}><Form.Item name="crawl_strategy" label="抓取策略" rules={[{ required: true }]}><Input placeholder="增量采集、正文差异、分页游标…" /></Form.Item></Col>
            <Col span={12}><Form.Item name="schedule_frequency" label="采集频率" rules={[{ required: true }]}><Select options={Object.entries(frequencyLabels).map(([value, label]) => ({ value, label }))} /></Form.Item></Col>
            <Col span={12}><Form.Item name={["collection_config", "timeout_seconds"]} label="请求超时（秒）" rules={[{ required: true }]}><InputNumber min={1} max={60} style={{ width: "100%" }} /></Form.Item></Col>
            <Col span={12}><Form.Item name={["collection_config", "max_items"]} label="单次最多条目"><InputNumber min={1} max={200} style={{ width: "100%" }} /></Form.Item></Col>
            {(["webpage", "dynamic_webpage"] as SourceType[]).includes(formSourceType) && <Col span={12}><Form.Item name={["collection_config", "content_selector"]} label="正文 CSS 选择器（可选）"><Input placeholder="例如 main article" /></Form.Item></Col>}
            {formSourceType === "dynamic_webpage" && <>
              <Col span={12}><Form.Item name={["collection_config", "wait_selector"]} label="等待元素（可选）"><Input placeholder="例如 [data-loaded=true]" /></Form.Item></Col>
              <Col span={12}><Form.Item name={["collection_config", "wait_ms"]} label="渲染后等待（毫秒）"><InputNumber min={0} max={15000} style={{ width: "100%" }} /></Form.Item></Col>
              <Col span={12}><Form.Item name={["collection_config", "browser_channel"]} label="浏览器通道"><Select options={[{ value: "msedge", label: "Microsoft Edge" }, { value: "chrome", label: "Google Chrome" }]} /></Form.Item></Col>
            </>}
            {(["public_api", "social_api", "public_database"] as SourceType[]).includes(formSourceType) && <>
              <Col span={12}><Form.Item name={["collection_config", "items_path"]} label="列表数据路径（可选）"><Input placeholder="例如 data.items" /></Form.Item></Col>
              <Col span={12}><Form.Item name={["collection_config", "title_path"]} label="标题字段路径"><Input placeholder="例如 name" /></Form.Item></Col>
              <Col span={12}><Form.Item name={["collection_config", "content_path"]} label="正文字段路径"><Input placeholder="例如 description" /></Form.Item></Col>
              <Col span={12}><Form.Item name={["collection_config", "url_path"]} label="原文地址字段路径"><Input placeholder="例如 html_url" /></Form.Item></Col>
              <Col span={12}><Form.Item name={["collection_config", "published_path"]} label="发布时间字段路径"><Input placeholder="例如 published_at" /></Form.Item></Col>
            </>}
            <Col span={12}><Form.Item name="regions" label="适用地区" rules={[{ required: true }]}><Select mode="multiple" options={Object.entries(regionLabels).map(([value, label]) => ({ value, label }))} /></Form.Item></Col>
            <Col span={12}><Form.Item name="fields_available" label="可用字段" tooltip="用于启用前字段可用性检查"><Select mode="tags" tokenSeparators={[","]} placeholder="输入字段后回车，如 title、body" /></Form.Item></Col>
            <Col span={12}><Form.Item name="authorization_status" label="授权状态" rules={[{ required: true }]}><Select options={Object.entries(authorizationMeta).map(([value, meta]) => ({ value, label: meta.label }))} /></Form.Item></Col>
            <Col span={12}><Form.Item name="data_classification" label="数据分类" rules={[{ required: true }]}><Select options={[{ value: "public", label: "公开" }, { value: "internal", label: "内部" }, { value: "restricted", label: "受限" }]} /></Form.Item></Col>
            <Col span={24}><Form.Item name="authorization_basis" label="授权依据 / 使用条款说明" rules={[{ required: true, message: "请登记授权依据" }]}><Input.TextArea rows={2} placeholder="说明公开许可、API 协议、企业授权或法务确认依据" /></Form.Item></Col>
            <Col span={8}><Form.Item name="retention_days" label="保留天数" rules={[{ required: true }]}><InputNumber min={1} max={3650} style={{ width: "100%" }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="rate_limit_per_minute" label="每分钟请求上限" rules={[{ required: true }]}><InputNumber min={1} max={600} style={{ width: "100%" }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="credential_ref" label={editingSource ? "新密钥服务引用（可留空）" : "密钥服务引用"}><Input.Password placeholder="vault://team/source-key" autoComplete="new-password" /></Form.Item></Col>
            <Col span={12}><Form.Item name="robots_acknowledged" valuePropName="checked"><Checkbox>已查看并确认 robots 提示</Checkbox></Form.Item></Col>
            <Col span={12}><Form.Item name="terms_acknowledged" valuePropName="checked"><Checkbox>已查看并确认来源使用条款</Checkbox></Form.Item></Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        title={`轮换凭据${rotationSource ? ` · ${rotationSource.name}` : ""}`}
        open={Boolean(rotationSource)}
        onCancel={() => setRotationSource(null)}
        onOk={() => void rotateCredential()}
        confirmLoading={rotating}
        okText="确认轮换"
        cancelText="取消"
      >
        <div className="credential-rotation-form">
          <p>当前界面仅显示掩码：<strong>{rotationSource?.credential_masked ?? "尚未绑定"}</strong>。新的引用会交由密钥服务托管，不会通过接口回传明文。</p>
          <label>新密钥服务引用</label>
          <Input.Password value={credentialRef} onChange={(event) => setCredentialRef(event.target.value)} placeholder="vault://team/source-key-v2" autoComplete="new-password" />
          <label>到期时间（可选）</label>
          <Input type="datetime-local" value={credentialExpiry} onChange={(event) => setCredentialExpiry(event.target.value)} />
        </div>
      </Modal>
    </div>
  );
}
