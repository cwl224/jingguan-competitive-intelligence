"use client";

import {
  ApiOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  CloseCircleFilled,
  ControlOutlined,
  DeploymentUnitOutlined,
  EditOutlined,
  ExclamationCircleFilled,
  FieldTimeOutlined,
  FireOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RetweetOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Form,
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
  message,
  type TableProps,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  bulkRetryOrchestrationRuns,
  cancelCollectionRun,
  fetchOrchestration,
  recoverOrchestrationRuns,
  triggerOrchestrationRun,
  updateSourceSchedule,
  type CollectionRun,
  type CollectionRunStatus,
  type DataSource,
  type OrchestrationDashboard,
  type Project,
  type SourceSchedulePayload,
  type WorkflowStep,
} from "../lib/api";

type Props = {
  project: Project;
  onDashboardRefresh: () => Promise<void>;
};

const statusMeta: Record<CollectionRunStatus, { label: string; color: string }> = {
  queued: { label: "待执行", color: "default" },
  running: { label: "运行中", color: "processing" },
  succeeded: { label: "成功", color: "success" },
  partial: { label: "部分成功", color: "warning" },
  failed: { label: "失败", color: "error" },
  cancelled: { label: "已取消", color: "default" },
  manual_review: { label: "待人工处理", color: "warning" },
};

const triggerLabels: Record<CollectionRun["trigger_type"], string> = {
  manual: "立即执行",
  scheduled: "定时采集",
  event: "事件触发",
  api: "API 触发",
  upload: "文件上传",
  retry: "失败重试",
  recovery: "异常恢复",
};

const stepMeta: Record<WorkflowStep["status"], { label: string; color: string }> = {
  pending: { label: "等待", color: "#c9c6bf" },
  running: { label: "运行中", color: "#60785f" },
  waiting_retry: { label: "退避等待", color: "#bb7a46" },
  succeeded: { label: "完成", color: "#60785f" },
  failed: { label: "失败", color: "#ac5d52" },
  skipped: { label: "跳过", color: "#aaa79f" },
};

const frequencyLabels: Record<DataSource["schedule_frequency"], string> = {
  manual: "仅手动",
  "15m": "每 15 分钟",
  hourly: "每小时",
  "6h": "每 6 小时",
  daily: "每天",
  weekly: "每周",
};

const recoverableStates: CollectionRunStatus[] = [
  "failed",
  "partial",
  "manual_review",
  "cancelled",
];

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

function workflowProgress(run: CollectionRun) {
  if (!run.workflow_steps.length) return 0;
  const finished = run.workflow_steps.filter((step) =>
    ["succeeded", "failed", "skipped"].includes(step.status),
  ).length;
  return Math.round((finished / run.workflow_steps.length) * 100);
}

function WorkflowDots({ run }: { run: CollectionRun }) {
  return (
    <div className="orchestration-workflow-dots" aria-label={`工作流完成度 ${workflowProgress(run)}%`}>
      {run.workflow_steps.map((step) => (
        <Tooltip key={step.key} title={`${step.agent} · ${stepMeta[step.status].label}`}>
          <i
            className={`orchestration-workflow-dot orchestration-workflow-dot--${step.status}`}
          />
        </Tooltip>
      ))}
      <span>{workflowProgress(run)}%</span>
    </div>
  );
}

export default function TaskOrchestration({ project, onDashboardRefresh }: Props) {
  const [dashboard, setDashboard] = useState<OrchestrationDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<CollectionRun | null>(null);
  const [selectedRunIds, setSelectedRunIds] = useState<React.Key[]>([]);
  const [statusFilter, setStatusFilter] = useState<CollectionRunStatus | "all">("all");
  const [editingSource, setEditingSource] = useState<DataSource | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [recoveringAll, setRecoveringAll] = useState(false);
  const [scheduleForm] = Form.useForm<SourceSchedulePayload>();
  const [messageApi, messageContext] = message.useMessage();

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const data = await fetchOrchestration(project.id);
      setDashboard(data);
      setSelectedRun((current) =>
        current ? data.runs.find((run) => run.id === current.id) ?? current : null,
      );
      setLoadError(null);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "任务编排数据加载失败";
      setLoadError(detail);
      if (!quiet) messageApi.error(detail);
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [messageApi, project.id]);

  useEffect(() => {
    const timeout = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timeout);
  }, [load]);

  const hasActiveRuns = dashboard?.runs.some((run) =>
    ["queued", "running"].includes(run.status),
  ) ?? false;

  useEffect(() => {
    if (!hasActiveRuns) return;
    const interval = window.setInterval(() => void load(true), 2500);
    return () => window.clearInterval(interval);
  }, [hasActiveRuns, load]);

  const filteredRuns = useMemo(
    () => dashboard?.runs.filter((run) => statusFilter === "all" || run.status === statusFilter) ?? [],
    [dashboard?.runs, statusFilter],
  );

  const openSchedule = (source: DataSource) => {
    setEditingSource(source);
    scheduleForm.setFieldsValue({
      schedule_frequency: source.schedule_frequency,
      rate_limit_per_minute: source.rate_limit_per_minute,
      concurrency_limit: source.concurrency_limit,
      task_timeout_seconds: source.task_timeout_seconds,
      max_attempts: source.max_attempts,
      retry_backoff_seconds: source.retry_backoff_seconds,
      priority: source.priority,
    });
  };

  const saveSchedule = async () => {
    if (!editingSource) return;
    try {
      const values = await scheduleForm.validateFields();
      setBusyId(editingSource.id);
      await updateSourceSchedule(editingSource.id, values);
      setEditingSource(null);
      await load(true);
      messageApi.success("调度与容错策略已更新");
    } catch (error) {
      if (error instanceof Error) messageApi.error(error.message);
    } finally {
      setBusyId(null);
    }
  };

  const triggerRun = async (source: DataSource, triggerType: "manual" | "event" | "api") => {
    setBusyId(source.id);
    try {
      await triggerOrchestrationRun(source.id, triggerType);
      await Promise.all([load(true), onDashboardRefresh()]);
      messageApi.success(`${triggerType === "event" ? "事件" : triggerType === "api" ? "API" : "立即"}任务已进入队列`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "任务触发失败");
    } finally {
      setBusyId(null);
    }
  };

  const retryRuns = async (runIds: string[]) => {
    if (!runIds.length) {
      messageApi.warning("请选择可重试的任务");
      return;
    }
    setBusyId("bulk-retry");
    try {
      const result = await bulkRetryOrchestrationRuns(runIds);
      setSelectedRunIds([]);
      await Promise.all([load(true), onDashboardRefresh()]);
      if (result.queued.length) messageApi.success(`已提交 ${result.queued.length} 个重试任务`);
      if (Object.keys(result.skipped).length) messageApi.warning(`${Object.keys(result.skipped).length} 个任务因状态或并发限制被跳过`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "批量重试失败");
    } finally {
      setBusyId(null);
    }
  };

  const recoverRuns = async (runIds: string[] = []) => {
    setRecoveringAll(true);
    try {
      const result = await recoverOrchestrationRuns(project.id, runIds);
      await Promise.all([load(true), onDashboardRefresh()]);
      if (result.queued.length) messageApi.success(`已启动 ${result.queued.length} 个恢复任务`);
      else messageApi.info("当前没有可恢复的异常任务");
      if (Object.keys(result.skipped).length) messageApi.warning(`${Object.keys(result.skipped).length} 个异常项暂未恢复`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "异常恢复失败");
    } finally {
      setRecoveringAll(false);
    }
  };

  const cancelRun = async (run: CollectionRun) => {
    setBusyId(run.id);
    try {
      await cancelCollectionRun(run.id);
      await load(true);
      messageApi.success("待执行任务已取消");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "取消任务失败");
    } finally {
      setBusyId(null);
    }
  };

  const scheduleColumns: TableProps<OrchestrationDashboard["schedules"][number]>["columns"] = [
    {
      title: "来源 / 计划",
      key: "source",
      width: 245,
      render: (_, item) => (
        <div className="orchestration-source-cell">
          <span className="orchestration-source-icon"><ApiOutlined /></span>
          <span><strong>{item.source.name}</strong><small>{frequencyLabels[item.source.schedule_frequency]} · 下次 {formatDateTime(item.source.next_run_at)}</small></span>
        </div>
      ),
    },
    {
      title: "优先级",
      dataIndex: ["source", "priority"],
      width: 90,
      align: "center",
      render: (value: number) => <Tag variant="filled" color={value >= 8 ? "volcano" : value >= 5 ? "gold" : "default"}>P{11 - value}</Tag>,
    },
    {
      title: "执行保护",
      key: "guardrails",
      width: 245,
      render: (_, item) => (
        <div className="orchestration-guardrails">
          <span><FieldTimeOutlined /> {item.source.task_timeout_seconds}s 超时</span>
          <span><RetweetOutlined /> {item.source.max_attempts} 次 / {item.source.retry_backoff_seconds}s</span>
          <span><ControlOutlined /> {item.source.rate_limit_per_minute}/min · 并发 {item.source.concurrency_limit}</span>
        </div>
      ),
    },
    {
      title: "工作状态",
      key: "state",
      width: 155,
      render: (_, item) => (
        <div className="orchestration-state-cell">
          <Tag color={item.source.circuit_state === "open" ? "error" : item.source.circuit_state === "half_open" ? "warning" : "success"}>
            {item.source.circuit_state === "open" ? "熔断" : item.source.circuit_state === "half_open" ? "试探恢复" : "正常"}
          </Tag>
          <small>{item.active_runs ? `${item.active_runs} 个活动任务` : item.last_run_status ? `上次${statusMeta[item.last_run_status].label}` : "尚未执行"}</small>
        </div>
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 150,
      align: "right",
      render: (_, item) => (
        <Space size={2}>
          <Tooltip title="立即执行"><Button type="text" size="small" icon={<PlayCircleOutlined />} loading={busyId === item.source.id} disabled={!item.source.enabled} onClick={() => void triggerRun(item.source, "manual")} /></Tooltip>
          <Tooltip title="模拟事件触发"><Button type="text" size="small" icon={<ThunderboltOutlined />} disabled={!item.source.enabled} onClick={() => void triggerRun(item.source, "event")} /></Tooltip>
          <Tooltip title="编辑调度策略"><Button type="text" size="small" icon={<EditOutlined />} onClick={() => openSchedule(item.source)} /></Tooltip>
        </Space>
      ),
    },
  ];

  const runColumns: TableProps<CollectionRun>["columns"] = [
    {
      title: "任务 / 来源",
      dataIndex: "source_name",
      width: 230,
      render: (_, run) => (
        <button className="orchestration-run-link" onClick={() => setSelectedRun(run)}>
          <strong>{run.source_name}</strong>
          <small>{run.id} · {triggerLabels[run.trigger_type]}</small>
        </button>
      ),
    },
    {
      title: "工作流",
      key: "workflow",
      width: 160,
      render: (_, run) => <WorkflowDots run={run} />,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 115,
      render: (value: CollectionRunStatus) => <Tag color={statusMeta[value].color}>{statusMeta[value].label}</Tag>,
    },
    {
      title: "重试 / 超时",
      key: "policy",
      width: 135,
      render: (_, run) => <span className="orchestration-run-meta"><strong>{run.attempt}/{run.max_attempts} 次</strong><small>{run.timeout_seconds}s · {run.retry_delays.length ? `退避 ${run.retry_delays.join("/")}s` : "未触发退避"}</small></span>,
    },
    {
      title: "执行时间",
      dataIndex: "created_at",
      width: 150,
      render: (value: string, run) => <span className="orchestration-run-meta"><strong>{formatDateTime(value)}</strong><small>{run.next_retry_at ? `重试 ${formatDateTime(run.next_retry_at)}` : run.finished_at ? `结束 ${formatDateTime(run.finished_at)}` : "等待结束"}</small></span>,
    },
    {
      title: "操作",
      key: "actions",
      width: 100,
      align: "right",
      render: (_, run) => (
        <Space size={2}>
          {run.status === "queued" && <Tooltip title="取消"><Button type="text" size="small" danger icon={<CloseCircleFilled />} loading={busyId === run.id} onClick={() => void cancelRun(run)} /></Tooltip>}
          {recoverableStates.includes(run.status) && <Tooltip title="重试"><Button type="text" size="small" icon={<RetweetOutlined />} loading={busyId === run.id} onClick={() => void retryRuns([run.id])} /></Tooltip>}
          <Tooltip title="查看工作流"><Button type="text" size="small" icon={<DeploymentUnitOutlined />} onClick={() => setSelectedRun(run)} /></Tooltip>
        </Space>
      ),
    },
  ];

  if (!dashboard && loadError && !loading) {
    return (
      <section className="orchestration-error-state">
        {messageContext}
        <ExclamationCircleFilled />
        <h2>任务编排暂时不可用</h2>
        <p>{loadError}</p>
        <Button type="primary" onClick={() => void load()}>重新加载</Button>
      </section>
    );
  }

  return (
    <section className="task-orchestration">
      {messageContext}
      <div className="orchestration-page-heading">
        <div>
          <span className="eyebrow">MODULE 03 · TASK ORCHESTRATION</span>
          <h1>任务调度与 Agent 编排</h1>
          <p>统一管理定时采集、优先级队列、指数退避、超时限流、工作流状态与异常补偿。</p>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新状态</Button>
          <Button type="primary" icon={<SafetyCertificateOutlined />} loading={recoveringAll} onClick={() => void recoverRuns()}>恢复异常任务</Button>
        </Space>
      </div>

      <div className="orchestration-summary-grid">
        <article><span className="orchestration-summary-icon"><ClockCircleOutlined /></span><div><small>计划采集来源</small><strong>{dashboard?.summary.scheduled_sources ?? 0}</strong><p>启用且配置了周期计划</p></div></article>
        <article><span className="orchestration-summary-icon orchestration-summary-icon--active"><SyncOutlined spin={Boolean(dashboard?.summary.running)} /></span><div><small>队列 / 运行</small><strong>{dashboard?.summary.queued ?? 0}<em>/</em>{dashboard?.summary.running ?? 0}</strong><p>按优先级与可执行时间派发</p></div></article>
        <article><span className="orchestration-summary-icon orchestration-summary-icon--success"><CheckCircleFilled /></span><div><small>24h 任务成功率</small><strong>{dashboard?.summary.success_rate_24h ?? 0}<em>%</em></strong><p>{dashboard?.summary.recovered_24h ?? 0} 个任务完成恢复</p></div></article>
        <article className={(dashboard?.summary.exceptions ?? 0) ? "orchestration-summary-card--alert" : ""}><span className="orchestration-summary-icon orchestration-summary-icon--alert"><FireOutlined /></span><div><small>异常队列</small><strong>{dashboard?.summary.exceptions ?? 0}</strong><p>失败、部分成功与待人工处理</p></div></article>
      </div>

      <article className="orchestration-flow-panel">
        <div className="orchestration-panel-head"><div><span className="panel-kicker">AGENT WORKFLOW</span><h2>采集工作流状态</h2><p>每个节点独立记录状态、耗时、错误与输出摘要。</p></div><Tag color="green">collection-v1</Tag></div>
        <div className="orchestration-flow">
          {dashboard?.workflow_nodes.map((node, index) => {
            const liveStep = selectedRun?.workflow_steps.find((step) => step.key === node.key);
            const state = liveStep?.status ?? "pending";
            return (
              <div className="orchestration-flow-fragment" key={node.key}>
                <div className={`orchestration-flow-node orchestration-flow-node--${state}`}>
                  <span className="orchestration-node-index">0{index + 1}</span>
                  <span className="orchestration-node-icon">{state === "succeeded" ? <CheckCircleFilled /> : state === "running" ? <SyncOutlined spin /> : state === "failed" ? <CloseCircleFilled /> : <DeploymentUnitOutlined />}</span>
                  <div><small>{node.agent}</small><strong>{node.name}</strong><p>{liveStep?.output_summary ?? node.description}</p></div>
                </div>
                {index < (dashboard?.workflow_nodes.length ?? 0) - 1 && <span className="orchestration-flow-arrow">→</span>}
              </div>
            );
          })}
        </div>
        <div className="orchestration-flow-foot"><span>{selectedRun ? `当前展示 ${selectedRun.source_name} · ${selectedRun.id}` : "选择任务后可查看节点实时状态"}</span>{selectedRun && <Button type="link" size="small" onClick={() => setSelectedRun(null)}>清除选择</Button>}</div>
      </article>

      <article className="orchestration-table-panel">
        <Tabs
          items={[
            {
              key: "schedules",
              label: `调度计划 ${dashboard?.schedules.length ?? 0}`,
              children: dashboard?.schedules.length ? <Table rowKey={(item) => item.source.id} columns={scheduleColumns} dataSource={dashboard.schedules} loading={loading} pagination={{ pageSize: 8, hideOnSinglePage: true }} scroll={{ x: 1000 }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据源调度计划" />,
            },
            {
              key: "runs",
              label: `任务队列 ${dashboard?.runs.length ?? 0}`,
              children: (
                <div>
                  <div className="orchestration-table-toolbar">
                    <Select value={statusFilter} onChange={setStatusFilter} options={[{ value: "all", label: "全部任务状态" }, ...Object.entries(statusMeta).map(([value, meta]) => ({ value, label: meta.label }))]} />
                    <Button icon={<RetweetOutlined />} disabled={!selectedRunIds.length} loading={busyId === "bulk-retry"} onClick={() => void retryRuns(selectedRunIds.map(String))}>批量重试</Button>
                  </div>
                  {filteredRuns.length ? <Table rowKey="id" columns={runColumns} dataSource={filteredRuns} loading={loading} rowSelection={{ selectedRowKeys: selectedRunIds, onChange: setSelectedRunIds, getCheckboxProps: (run) => ({ disabled: !recoverableStates.includes(run.status) }) }} pagination={{ pageSize: 8, hideOnSinglePage: true }} scroll={{ x: 980 }} onRow={(run) => ({ onClick: () => setSelectedRun(run) })} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选下没有任务" />}
                </div>
              ),
            },
            {
              key: "exceptions",
              label: `异常恢复 ${dashboard?.exceptions.length ?? 0}`,
              children: dashboard?.exceptions.length ? (
                <div className="orchestration-exception-list">
                  {dashboard.exceptions.map((run) => (
                    <article key={run.id}>
                      <span className="orchestration-exception-icon"><ExclamationCircleFilled /></span>
                      <div><Tag color={statusMeta[run.status].color}>{statusMeta[run.status].label}</Tag><strong>{run.source_name}</strong><p>{run.error_message ?? "任务产生部分结果，需要确认后补偿执行。"}</p><small>{run.error_type ?? "partial_result"} · 尝试 {run.attempt}/{run.max_attempts} · {formatDateTime(run.finished_at)}</small></div>
                      <Button icon={<SafetyCertificateOutlined />} loading={recoveringAll} onClick={() => void recoverRuns([run.id])}>恢复并补采</Button>
                    </article>
                  ))}
                </div>
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="异常队列为空，所有工作流运行正常" />,
            },
          ]}
        />
      </article>

      <Drawer title={selectedRun ? `Agent 工作流 · ${selectedRun.source_name}` : "Agent 工作流"} open={Boolean(selectedRun)} onClose={() => setSelectedRun(null)} size={620} className="orchestration-run-drawer">
        {selectedRun && (
          <>
            <div className={`orchestration-run-hero orchestration-run-hero--${selectedRun.status}`}>
              {selectedRun.status === "succeeded" ? <CheckCircleFilled /> : selectedRun.status === "running" ? <SyncOutlined spin /> : selectedRun.status === "failed" || selectedRun.status === "manual_review" ? <CloseCircleFilled /> : <ClockCircleOutlined />}
              <div><Space size={6}><Tag color={statusMeta[selectedRun.status].color}>{statusMeta[selectedRun.status].label}</Tag><Tag>{triggerLabels[selectedRun.trigger_type]}</Tag></Space><h3>{selectedRun.request_summary ?? selectedRun.id}</h3><p>{selectedRun.error_message ?? `发现 ${selectedRun.items_discovered} 条内容，新增 ${selectedRun.documents_created} 条，更新 ${selectedRun.documents_updated} 条。`}</p></div>
            </div>
            <Progress percent={workflowProgress(selectedRun)} status={selectedRun.status === "failed" ? "exception" : "active"} strokeColor="#687c67" trailColor="#eae7e0" />
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="优先级">{selectedRun.priority}</Descriptions.Item>
              <Descriptions.Item label="工作流版本">{selectedRun.workflow_version}</Descriptions.Item>
              <Descriptions.Item label="尝试次数">{selectedRun.attempt}/{selectedRun.max_attempts}</Descriptions.Item>
              <Descriptions.Item label="任务超时">{selectedRun.timeout_seconds} 秒</Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatDateTime(selectedRun.started_at)}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{formatDateTime(selectedRun.finished_at)}</Descriptions.Item>
              <Descriptions.Item label="下次重试" span={2}>{formatDateTime(selectedRun.next_retry_at)}</Descriptions.Item>
              <Descriptions.Item label="退避记录" span={2}>{selectedRun.retry_delays.length ? selectedRun.retry_delays.map((value) => `${value}s`).join(" → ") : "未触发"}</Descriptions.Item>
            </Descriptions>
            {selectedRun.recovered_from_restart && <Alert className="orchestration-recovery-alert" type="warning" showIcon message="该任务曾因服务重启被自动恢复" />}
            <h4 className="orchestration-drawer-title">Agent 节点</h4>
            <Timeline items={selectedRun.workflow_steps.map((step) => ({ color: stepMeta[step.status].color, dot: step.status === "running" ? <SyncOutlined spin /> : step.status === "succeeded" ? <CheckCircleFilled /> : step.status === "failed" ? <CloseCircleFilled /> : undefined, children: <div className="orchestration-step-detail"><div><strong>{step.name}</strong><Tag>{step.agent}</Tag><span>{stepMeta[step.status].label}</span></div><p>{step.error_message ?? step.output_summary ?? "等待上游节点完成"}</p><small>尝试 {step.attempt}/{step.max_attempts}{step.duration_ms !== null ? ` · ${step.duration_ms}ms` : ""}</small></div> }))} />
            <h4 className="orchestration-drawer-title">运行日志</h4>
            <Timeline items={(selectedRun.parser_steps.length ? selectedRun.parser_steps : ["任务等待调度器领取"]).map((step, index) => ({ color: index === selectedRun.parser_steps.length - 1 && ["failed", "manual_review"].includes(selectedRun.status) ? "red" : "green", children: step }))} />
          </>
        )}
      </Drawer>

      <Modal title={editingSource ? `调度策略 · ${editingSource.name}` : "调度策略"} open={Boolean(editingSource)} onCancel={() => setEditingSource(null)} onOk={() => void saveSchedule()} confirmLoading={Boolean(editingSource && busyId === editingSource.id)} okText="保存策略" cancelText="取消" width={680} forceRender destroyOnHidden>
        <div className="orchestration-policy-note"><SafetyCertificateOutlined /><p><strong>策略会应用到新任务。</strong> 已运行任务继续使用创建时的超时、重试和优先级快照，确保审计口径稳定。</p></div>
        <Form form={scheduleForm} layout="vertical" className="orchestration-policy-form">
          <Form.Item name="schedule_frequency" label="采集周期" rules={[{ required: true }]}><Select options={Object.entries(frequencyLabels).map(([value, label]) => ({ value, label }))} /></Form.Item>
          <Form.Item name="priority" label="队列优先级（10 最高）" rules={[{ required: true }]}><InputNumber min={1} max={10} style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="task_timeout_seconds" label="任务级超时（秒）" rules={[{ required: true }]}><InputNumber min={5} max={900} style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="max_attempts" label="最大尝试次数" rules={[{ required: true }]}><InputNumber min={1} max={10} style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="retry_backoff_seconds" label="指数退避基数（秒）" rules={[{ required: true }]}><InputNumber min={1} max={300} style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="rate_limit_per_minute" label="单来源速率上限（次/分钟）" rules={[{ required: true }]}><InputNumber min={1} max={600} style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="concurrency_limit" label="单来源并发上限" rules={[{ required: true }]}><InputNumber min={1} max={10} style={{ width: "100%" }} /></Form.Item>
        </Form>
      </Modal>
    </section>
  );
}
