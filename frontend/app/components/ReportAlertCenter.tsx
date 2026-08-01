"use client";

import {
  AlertOutlined,
  BellOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  CloudDownloadOutlined,
  FileDoneOutlined,
  FileTextOutlined,
  MailOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  SettingOutlined,
  SyncOutlined,
  WarningFilled,
} from "@ant-design/icons";
import {
  Button,
  Drawer,
  Empty,
  Input,
  InputNumber,
  Modal,
  Progress,
  Segmented,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  message,
} from "antd";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  actOnAlert,
  approveReport,
  createAlertRule,
  downloadReport,
  fetchReportingDashboard,
  generateConfiguredReport,
  updateAlertRule,
  updateReportSubscription,
  type AlertRecord,
  type Project,
  type ReportRecord,
  type ReportingDashboard,
} from "../lib/api";

const reportStateMeta = {
  已交付: { color: "success", icon: <CheckCircleFilled /> },
  生成中: { color: "processing", icon: <SyncOutlined spin /> },
  待审批: { color: "warning", icon: <ClockCircleOutlined /> },
  生成失败: { color: "error", icon: <WarningFilled /> },
} as const;

const impactMeta = {
  critical: { label: "紧急", className: "critical" },
  high: { label: "高影响", className: "high" },
  medium: { label: "中影响", className: "medium" },
  low: { label: "低影响", className: "low" },
} as const;

const audienceOptions = [
  { value: "analyst", label: "分析师" },
  { value: "product", label: "产品团队" },
  { value: "management", label: "管理层" },
  { value: "general", label: "通用读者" },
];

function formatTime(value: string | null) {
  if (!value) return "尚未执行";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function renderSection(value: unknown): ReactNode {
  if (typeof value === "string" || typeof value === "number") return <p>{String(value)}</p>;
  if (Array.isArray(value)) {
    return (
      <div className="report-section-list">
        {value.map((item, index) => (
          <article key={index}>
            {typeof item === "object" && item !== null ? (
              Object.entries(item as Record<string, unknown>).map(([key, nested]) => (
                <div key={key}>
                  <span>{key}</span>
                  <strong>{Array.isArray(nested) ? nested.join("、") : String(nested)}</strong>
                </div>
              ))
            ) : (
              <p>{String(item)}</p>
            )}
          </article>
        ))}
      </div>
    );
  }
  if (typeof value === "object" && value !== null) {
    return (
      <div className="report-definition-grid">
        {Object.entries(value as Record<string, unknown>).map(([key, nested]) => (
          <div key={key}><span>{key}</span><strong>{String(nested)}</strong></div>
        ))}
      </div>
    );
  }
  return null;
}

export default function ReportAlertCenter({ project }: { project: Project }) {
  const [messageApi, contextHolder] = message.useMessage();
  const [dashboard, setDashboard] = useState<ReportingDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveView] = useState<"reports" | "alerts" | "delivery">("reports");
  const [selectedReport, setSelectedReport] = useState<ReportRecord | null>(null);
  const [selectedAlert, setSelectedAlert] = useState<AlertRecord | null>(null);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [ruleOpen, setRuleOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [templateId, setTemplateId] = useState("tpl_daily");
  const [timeWindow, setTimeWindow] = useState<"24h" | "7d" | "30d" | "90d">("24h");
  const [audience, setAudience] = useState<"analyst" | "product" | "management" | "general">("analyst");
  const [length, setLength] = useState<"brief" | "standard" | "detailed">("standard");
  const [ruleName, setRuleName] = useState("");
  const [ruleKeywords, setRuleKeywords] = useState<string[]>([]);
  const [ruleCompetitors, setRuleCompetitors] = useState<string[]>([]);
  const [ruleImpact, setRuleImpact] = useState<"low" | "medium" | "high">("medium");
  const [ruleConfidence, setRuleConfidence] = useState(80);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDashboard(await fetchReportingDashboard(project.id));
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "报告与预警数据加载失败");
    } finally {
      setLoading(false);
    }
  }, [messageApi, project.id]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [load]);

  const selectedTemplate = useMemo(
    () => dashboard?.templates.find((item) => item.id === templateId) ?? dashboard?.templates[0],
    [dashboard, templateId],
  );

  const handleGenerate = async () => {
    if (!selectedTemplate) return;
    setSubmitting(true);
    try {
      await generateConfiguredReport({
        project_id: project.id,
        template: selectedTemplate.report_type,
        template_id: selectedTemplate.id,
        time_window: timeWindow,
        language: selectedTemplate.language,
        audience,
        length,
        approval_required: selectedTemplate.approval_required,
      });
      setGenerateOpen(false);
      await load();
      window.setTimeout(() => void load(), 900);
      messageApi.success("报告生成任务已提交，完成后会按审批流程流转");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "报告生成失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleApproval = async (report: ReportRecord, decision: "approve" | "reject") => {
    setSubmitting(true);
    try {
      const updated = await approveReport(report.id, decision, decision === "reject" ? "需补充证据后重新提交" : "证据与引用完整");
      setSelectedReport(updated);
      await load();
      messageApi.success(decision === "approve" ? "报告已审批并交付" : "报告已退回补充证据");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "审批操作失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDownload = async (report: ReportRecord, format: "docx" | "pdf") => {
    try {
      const blob = await downloadReport(report.id, format);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${report.title}-V${report.version}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      messageApi.success(`${format.toUpperCase()} 已开始下载`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "导出失败");
    }
  };

  const handleAlertAction = async (alert: AlertRecord, action: "acknowledge" | "resolve") => {
    setSubmitting(true);
    try {
      const updated = await actOnAlert(alert.id, action);
      setSelectedAlert(updated);
      await load();
      messageApi.success(action === "acknowledge" ? "预警已确认并进入处置" : "预警已关闭");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "预警操作失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreateRule = async () => {
    if (!ruleName.trim()) {
      messageApi.warning("请填写预警规则名称");
      return;
    }
    setSubmitting(true);
    try {
      await createAlertRule({
        project_id: project.id,
        name: ruleName.trim(),
        competitors: ruleCompetitors,
        keywords: ruleKeywords,
        event_types: [],
        min_impact: ruleImpact,
        min_confidence: ruleConfidence,
        change_threshold: 0,
        quiet_minutes: 120,
        escalation_minutes: 60,
        channels: ["in_app", "email"],
        enabled: true,
      });
      setRuleOpen(false);
      setRuleName("");
      setRuleKeywords([]);
      setRuleCompetitors([]);
      await load();
      messageApi.success("预警规则已启用");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "规则创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="report-center">
      {contextHolder}
      <section className="module-hero report-center__hero">
        <div>
          <div className="eyebrow"><FileDoneOutlined /> REPORTING &amp; EARLY WARNING</div>
          <h1>报告、订阅与预警</h1>
          <p>从证据集合生成可审批、可追溯的报告，并将高影响变化按规则去重、静默与升级。</p>
        </div>
        <div className="module-hero__actions">
          <Button icon={<AlertOutlined />} onClick={() => setRuleOpen(true)}>新建预警规则</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setGenerateOpen(true)}>生成报告</Button>
        </div>
      </section>

      <Spin spinning={loading && !dashboard}>
        {dashboard ? (
          <>
            <section className="report-summary-grid">
              <article><span className="report-summary-icon"><FileTextOutlined /></span><div><small>已交付报告</small><strong>{dashboard.summary.delivered}</strong><p>准时率 {dashboard.summary.on_time_rate}%</p></div></article>
              <article><span className="report-summary-icon report-summary-icon--approval"><ClockCircleOutlined /></span><div><small>待审批</small><strong>{dashboard.summary.pending_approval}</strong><p>{dashboard.summary.generating} 份正在生成</p></div></article>
              <article className={dashboard.summary.active_alerts ? "is-alert" : ""}><span className="report-summary-icon report-summary-icon--alert"><BellOutlined /></span><div><small>活跃预警</small><strong>{dashboard.summary.active_alerts}</strong><p>{dashboard.summary.critical_alerts} 条紧急</p></div></article>
              <article><span className="report-summary-icon report-summary-icon--evidence"><SafetyCertificateOutlined /></span><div><small>事实引用完整率</small><strong>{dashboard.summary.evidence_coverage}%</strong><p>缺失证据不自动入报告</p></div></article>
            </section>

            <div className="report-view-switch">
              <Segmented
                value={activeView}
                onChange={(value) => setActiveView(value as typeof activeView)}
                options={[
                  { value: "reports", label: `报告与模板 · ${dashboard.reports.length}` },
                  { value: "alerts", label: `预警中心 · ${dashboard.summary.active_alerts}` },
                  { value: "delivery", label: `订阅与规则 · ${dashboard.subscriptions.length + dashboard.alert_rules.length}` },
                ]}
              />
            </div>

            {activeView === "reports" && (
              <div className="report-workspace-grid">
                <section className="report-template-panel panel">
                  <div className="panel-head"><div><span className="panel-kicker">TEMPLATES</span><h3>内置报告模板</h3></div><Tag>{dashboard.templates.length} 个</Tag></div>
                  <div className="report-template-list">
                    {dashboard.templates.map((template) => (
                      <button key={template.id} onClick={() => { setTemplateId(template.id); setAudience((template.audience as typeof audience) || "analyst"); setGenerateOpen(true); }}>
                        <i><FileTextOutlined /></i>
                        <div><strong>{template.name}</strong><p>{template.description}</p><span>{template.sections.length} 个章节 · {template.approval_required ? "需审批" : "自动交付"}</span></div>
                        <b>→</b>
                      </button>
                    ))}
                  </div>
                </section>

                <section className="report-history-panel panel">
                  <div className="panel-head"><div><span className="panel-kicker">VERSIONS &amp; DELIVERY</span><h3>报告版本与交付</h3></div><Button type="text" icon={<SyncOutlined />} loading={loading} onClick={() => void load()}>刷新</Button></div>
                  <div className="report-history-list">
                    {dashboard.reports.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无报告" />}
                    {dashboard.reports.map((report) => (
                      <button key={report.id} onClick={() => setSelectedReport(report)}>
                        <span className={`report-state-icon report-state-icon--${report.state}`}>{reportStateMeta[report.state].icon}</span>
                        <div className="report-history-main">
                          <div><strong>{report.title}</strong><Tag color={reportStateMeta[report.state].color}>{report.state}</Tag></div>
                          <p>V{report.version} · {report.time_window} · 数据截止 {formatTime(report.data_cutoff)}</p>
                          <div className="report-history-meta"><span>{report.evidence_count} 条证据</span><span>{report.source_count} 个来源</span><span>置信度 {report.confidence}%</span></div>
                          {report.state === "生成中" && <Progress percent={report.progress} showInfo={false} size="small" />}
                        </div>
                        <b>→</b>
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {activeView === "alerts" && (
              <section className="alert-center-panel panel">
                <div className="panel-head"><div><span className="panel-kicker">SIGNAL TRIAGE</span><h3>预警处置队列</h3></div><p>按影响等级、置信度和重复次数排序</p></div>
                <div className="alert-card-grid">
                  {dashboard.alerts.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无预警" />}
                  {dashboard.alerts.map((alert) => (
                    <button key={alert.id} className={`alert-card alert-card--${impactMeta[alert.impact].className}`} onClick={() => setSelectedAlert(alert)}>
                      <div className="alert-card__top"><Tag>{alert.competitor}</Tag><span>{formatTime(alert.last_seen_at)}</span></div>
                      <div className="alert-card__impact"><i /><strong>{impactMeta[alert.impact].label}</strong><span>{alert.status === "new" ? "待确认" : alert.status === "acknowledged" ? "处置中" : "已关闭"}</span></div>
                      <h3>{alert.title}</h3>
                      <p>{alert.summary}</p>
                      <footer><span>{alert.source_count} 个来源 · 置信度 {alert.confidence}%</span>{alert.occurrence_count > 1 && <b>合并 {alert.occurrence_count} 次</b>}</footer>
                    </button>
                  ))}
                </div>
              </section>
            )}

            {activeView === "delivery" && (
              <div className="delivery-grid">
                <section className="panel delivery-panel">
                  <div className="panel-head"><div><span className="panel-kicker">SUBSCRIPTIONS</span><h3>报告订阅与交付</h3></div><SendOutlined /></div>
                  <div className="delivery-list">
                    {dashboard.subscriptions.map((subscription) => (
                      <article key={subscription.id}>
                        <span className="delivery-channel"><MailOutlined /></span>
                        <div><strong>{subscription.name}</strong><p>{subscription.cadence} · {subscription.delivery_time} · {subscription.timezone}</p><small>{subscription.recipients.join("、")} · 下次 {formatTime(subscription.next_run_at)}</small></div>
                        <Switch checked={subscription.enabled} onChange={async (checked) => { await updateReportSubscription(subscription.id, checked); await load(); messageApi.success(checked ? "订阅已启用" : "订阅已暂停"); }} />
                      </article>
                    ))}
                  </div>
                </section>
                <section className="panel delivery-panel">
                  <div className="panel-head"><div><span className="panel-kicker">ALERT RULES</span><h3>预警规则</h3></div><Button size="small" icon={<PlusOutlined />} onClick={() => setRuleOpen(true)}>新建</Button></div>
                  <div className="delivery-list rule-list">
                    {dashboard.alert_rules.map((rule) => (
                      <article key={rule.id}>
                        <span className="delivery-channel delivery-channel--alert"><SettingOutlined /></span>
                        <div><strong>{rule.name}</strong><p>≥ {rule.min_impact === "high" ? "高" : rule.min_impact === "medium" ? "中" : "低"}影响 · 置信度 {rule.min_confidence}%</p><small>静默 {rule.quiet_minutes} 分钟 · {rule.channels.join(" + ")}</small></div>
                        <Switch checked={rule.enabled} onChange={async (checked) => { await updateAlertRule(rule.id, { enabled: checked }); await load(); }} />
                      </article>
                    ))}
                  </div>
                </section>
              </div>
            )}
          </>
        ) : (
          !loading && <div className="module-empty"><WarningFilled /><h2>报告服务暂不可用</h2><Button onClick={() => void load()}>重新加载</Button></div>
        )}
      </Spin>

      <Drawer title={null} size={620} open={Boolean(selectedReport)} onClose={() => setSelectedReport(null)} className="report-detail-drawer">
        {selectedReport && (
          <div className="report-detail">
            <div className="drawer-eyebrow">ONLINE REPORT · V{selectedReport.version}</div>
            <Space wrap><Tag color={reportStateMeta[selectedReport.state].color}>{selectedReport.state}</Tag><Tag>{selectedReport.audience}</Tag><Tag>{selectedReport.time_window}</Tag></Space>
            <h2>{selectedReport.title}</h2>
            <p className="report-detail__cutoff">数据截止 {formatTime(selectedReport.data_cutoff)} · 更新 {formatTime(selectedReport.updated_at)}</p>
            <div className="report-proof-strip"><div><strong>{selectedReport.evidence_count}</strong><span>证据</span></div><div><strong>{selectedReport.source_count}</strong><span>来源</span></div><div><strong>{selectedReport.confidence}%</strong><span>置信度</span></div></div>
            {Object.entries(selectedReport.sections).map(([heading, value]) => <section key={heading}><h3>{heading}</h3>{renderSection(value)}</section>)}
            {selectedReport.failure_reason && <div className="report-failure-note"><WarningFilled />{selectedReport.failure_reason}</div>}
            <div className="report-drawer-actions">
              <Tooltip title="导出文件包含项目、版本、数据截止时间与来源说明"><Button icon={<CloudDownloadOutlined />} onClick={() => void handleDownload(selectedReport, "docx")}>Word</Button></Tooltip>
              <Button icon={<CloudDownloadOutlined />} onClick={() => void handleDownload(selectedReport, "pdf")}>PDF</Button>
              {selectedReport.state === "待审批" && <><Button danger loading={submitting} onClick={() => void handleApproval(selectedReport, "reject")}>退回</Button><Button type="primary" loading={submitting} onClick={() => void handleApproval(selectedReport, "approve")}>审批并交付</Button></>}
            </div>
          </div>
        )}
      </Drawer>

      <Drawer title={null} size={500} open={Boolean(selectedAlert)} onClose={() => setSelectedAlert(null)} className="alert-detail-drawer">
        {selectedAlert && (
          <div className="alert-detail">
            <div className="drawer-eyebrow">EARLY WARNING · {selectedAlert.event_type}</div>
            <div className={`alert-detail__signal alert-detail__signal--${selectedAlert.impact}`}><WarningFilled /><span>{impactMeta[selectedAlert.impact].label}</span></div>
            <h2>{selectedAlert.title}</h2><p>{selectedAlert.summary}</p>
            <div className="alert-detail__facts"><div><span>竞品</span><strong>{selectedAlert.competitor}</strong></div><div><span>置信度</span><strong>{selectedAlert.confidence}%</strong></div><div><span>来源</span><strong>{selectedAlert.source_count} 个</strong></div><div><span>重复信号</span><strong>{selectedAlert.occurrence_count} 次</strong></div></div>
            <div className="alert-trace"><h3>处置轨迹</h3><p>首次发现 {formatTime(selectedAlert.first_seen_at)}</p><p>最近信号 {formatTime(selectedAlert.last_seen_at)}</p><p>静默至 {formatTime(selectedAlert.quiet_until)}</p></div>
            <div className="report-drawer-actions">
              {selectedAlert.status === "new" && <Button type="primary" loading={submitting} onClick={() => void handleAlertAction(selectedAlert, "acknowledge")}>确认并处置</Button>}
              {selectedAlert.status !== "resolved" && <Button loading={submitting} onClick={() => void handleAlertAction(selectedAlert, "resolve")}>关闭预警</Button>}
            </div>
          </div>
        )}
      </Drawer>

      <Modal title="生成证据化报告" open={generateOpen} onCancel={() => setGenerateOpen(false)} onOk={() => void handleGenerate()} confirmLoading={submitting} okText="开始生成" cancelText="取消" width={620}>
        <div className="report-config-form">
          <label><span>报告模板</span><Select value={selectedTemplate?.id} onChange={setTemplateId} options={dashboard?.templates.map((item) => ({ value: item.id, label: `${item.name}${item.approval_required ? " · 需审批" : ""}` }))} /></label>
          <div><label><span>时间窗口</span><Select value={timeWindow} onChange={setTimeWindow} options={[{ value: "24h", label: "过去 24 小时" }, { value: "7d", label: "过去 7 天" }, { value: "30d", label: "过去 30 天" }, { value: "90d", label: "过去 90 天" }]} /></label><label><span>读者角色</span><Select value={audience} onChange={setAudience} options={audienceOptions} /></label></div>
          <label><span>篇幅</span><Segmented block value={length} onChange={(value) => setLength(value as typeof length)} options={[{ value: "brief", label: "简报" }, { value: "standard", label: "标准" }, { value: "detailed", label: "详细" }]} /></label>
          <div className="report-config-note"><SafetyCertificateOutlined /><p><strong>证据门禁已启用。</strong> 事实型结论必须绑定有效来源；低置信、授权失效或冲突内容不会静默写入。</p></div>
        </div>
      </Modal>

      <Modal title="新建预警规则" open={ruleOpen} onCancel={() => setRuleOpen(false)} onOk={() => void handleCreateRule()} confirmLoading={submitting} okText="创建并启用" cancelText="取消" width={620}>
        <div className="report-config-form">
          <label><span>规则名称</span><Input value={ruleName} onChange={(event) => setRuleName(event.target.value)} placeholder="例如：重点竞品重大发布" /></label>
          <label><span>竞品范围</span><Select mode="tags" value={ruleCompetitors} onChange={setRuleCompetitors} placeholder="不填写表示全部竞品" /></label>
          <label><span>关键词</span><Select mode="tags" value={ruleKeywords} onChange={setRuleKeywords} placeholder="输入后回车，例如：定价、企业版" /></label>
          <div><label><span>最低影响</span><Select value={ruleImpact} onChange={setRuleImpact} options={[{ value: "low", label: "低影响" }, { value: "medium", label: "中影响" }, { value: "high", label: "高影响" }]} /></label><label><span>最低置信度</span><InputNumber value={ruleConfidence} onChange={(value) => setRuleConfidence(value ?? 80)} min={0} max={100} addonAfter="%" /></label></div>
          <div className="report-config-note"><BellOutlined /><p>相同规则命中的重复信号会自动合并；默认静默 120 分钟，紧急预警 60 分钟未确认会升级。</p></div>
        </div>
      </Modal>
    </div>
  );
}
