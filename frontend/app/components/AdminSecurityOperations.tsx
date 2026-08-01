"use client";

import {
  ApiOutlined,
  AuditOutlined,
  CheckCircleFilled,
  CloudServerOutlined,
  DatabaseOutlined,
  DollarOutlined,
  ExportOutlined,
  FieldTimeOutlined,
  LockOutlined,
  ReloadOutlined,
  SafetyCertificateFilled,
  SafetyCertificateOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  UserOutlined,
  WarningFilled,
} from "@ant-design/icons";
import {
  Avatar,
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
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  actOnIncident,
  fetchAdminDashboard,
  runAdminBackup,
  updateAdminModel,
  updateAdminPolicy,
  updateAdminUserAccess,
  type AdminDashboard,
} from "../lib/api";

type AdminUser = AdminDashboard["users"][number];
type AdminModel = AdminDashboard["models"][number];

const serviceStatus = {
  healthy: { label: "正常", color: "success" },
  degraded: { label: "降级", color: "warning" },
  outage: { label: "中断", color: "error" },
  maintenance: { label: "维护", color: "default" },
} as const;

const actionLabels: Record<string, string> = {
  "report.generate": "生成报告",
  "report.approve": "审批报告",
  "report.subscription.update": "调整报告订阅",
  "alert.acknowledge": "确认预警",
  "alert.resolve": "关闭预警",
  "admin.user_access.update": "修改成员权限",
  "admin.model.update": "修改模型策略",
  "admin.policy.update": "修改安全策略",
  "operations.backup.run": "执行备份",
  "source.create": "创建数据源",
  "source.update": "更新数据源",
  "rag.query": "执行 RAG 查询",
};

function formatTime(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function bytesLabel(value: number) {
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  return `${(value / 1024 ** 2).toFixed(0)} MB`;
}

export default function AdminSecurityOperations() {
  const [messageApi, contextHolder] = message.useMessage();
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveView] = useState<"overview" | "access" | "models" | "security" | "audit">("overview");
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [selectedModel, setSelectedModel] = useState<AdminModel | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [auditQuery, setAuditQuery] = useState("");
  const [userRole, setUserRole] = useState("");
  const [userMfa, setUserMfa] = useState(false);
  const [userExport, setUserExport] = useState<AdminUser["export_permission"]>("none");
  const [userStatus, setUserStatus] = useState<AdminUser["status"]>("active");
  const [modelStatus, setModelStatus] = useState<AdminModel["status"]>("active");
  const [modelBudget, setModelBudget] = useState(0);
  const [modelFallback, setModelFallback] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDashboard(await fetchAdminDashboard());
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "管理中心数据加载失败");
    } finally {
      setLoading(false);
    }
  }, [messageApi]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [load]);

  const openUser = (user: AdminUser) => {
    setSelectedUser(user);
    setUserRole(user.role_id);
    setUserMfa(user.mfa_enabled);
    setUserExport(user.export_permission);
    setUserStatus(user.status);
  };

  const openModel = (model: AdminModel) => {
    setSelectedModel(model);
    setModelStatus(model.status);
    setModelBudget(model.monthly_budget);
    setModelFallback(model.fallback_model);
  };

  const saveUser = async () => {
    if (!selectedUser) return;
    setSubmitting(true);
    try {
      await updateAdminUserAccess(selectedUser.id, {
        role_id: userRole,
        mfa_enabled: userMfa,
        export_permission: userExport,
        status: userStatus,
      });
      setSelectedUser(null);
      await load();
      messageApi.success("成员访问边界已更新并写入审计日志");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "权限更新失败");
    } finally {
      setSubmitting(false);
    }
  };

  const saveModel = async () => {
    if (!selectedModel) return;
    setSubmitting(true);
    try {
      await updateAdminModel(selectedModel.id, {
        status: modelStatus,
        monthly_budget: modelBudget,
        fallback_model: modelFallback,
      });
      setSelectedModel(null);
      await load();
      messageApi.success("模型路由、配额与降级策略已更新");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "模型配置更新失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleBackup = async () => {
    setSubmitting(true);
    try {
      const result = await runAdminBackup();
      await load();
      messageApi.success(result.message);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "备份任务失败");
    } finally {
      setSubmitting(false);
    }
  };

  const filteredAudits = useMemo(() => {
    const query = auditQuery.trim().toLowerCase();
    if (!dashboard || !query) return dashboard?.audit_events ?? [];
    return dashboard.audit_events.filter((item) =>
      [item.actor_name, item.action, item.entity_type, item.entity_id, JSON.stringify(item.detail)]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [auditQuery, dashboard]);

  return (
    <div className="admin-center">
      {contextHolder}
      <section className="module-hero admin-center__hero">
        <div>
          <div className="eyebrow"><SafetyCertificateOutlined /> GOVERNANCE, SECURITY &amp; OPERATIONS</div>
          <h1>管理、安全与运维</h1>
          <p>统一管理组织权限、模型与费用、安全策略、审计轨迹和服务恢复，所有高风险变更均可追溯。</p>
        </div>
        <div className="module-hero__actions">
          <Tooltip title="生成 SQLite 全量备份并立即完成完整性校验"><Button icon={<DatabaseOutlined />} loading={submitting} onClick={() => void handleBackup()}>立即备份</Button></Tooltip>
          <Button type="primary" icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新状态</Button>
        </div>
      </section>

      <Spin spinning={loading && !dashboard}>
        {dashboard ? (
          <>
            <section className="admin-summary-grid">
              <article><span><CloudServerOutlined /></span><div><small>服务可用性</small><strong>{dashboard.summary.availability}%</strong><p>目标 ≥ 99.5%</p></div></article>
              <article><span><CheckCircleFilled /></span><div><small>任务成功率</small><strong>{dashboard.summary.task_success_rate}%</strong><p>报告成功率 {dashboard.summary.report_success_rate}%</p></div></article>
              <article className={dashboard.summary.active_incidents ? "is-warning" : ""}><span><WarningFilled /></span><div><small>活跃事故</small><strong>{dashboard.summary.active_incidents}</strong><p>RPO {dashboard.summary.rpo_minutes} 分钟 · RTO {dashboard.summary.rto_hours} 小时</p></div></article>
              <article><span><DollarOutlined /></span><div><small>本月模型费用</small><strong>¥{dashboard.summary.monthly_cost.toLocaleString()}</strong><p>预算使用 {dashboard.summary.budget_utilization}%</p></div></article>
            </section>

            <div className="admin-view-switch">
              <Segmented
                value={activeView}
                onChange={(value) => setActiveView(value as typeof activeView)}
                options={[
                  { value: "overview", label: "运行总览" },
                  { value: "access", label: "组织与权限" },
                  { value: "models", label: "模型与评测" },
                  { value: "security", label: "安全与合规" },
                  { value: "audit", label: "审计日志" },
                ]}
              />
            </div>

            {activeView === "overview" && (
              <div className="operations-grid">
                <section className="panel service-health-panel">
                  <div className="panel-head"><div><span className="panel-kicker">SERVICE HEALTH</span><h3>全链路服务健康</h3></div><span className="live-indicator"><i /> 实时</span></div>
                  <div className="service-health-list">
                    {dashboard.services.map((service) => (
                      <article key={service.id}>
                        <span className={`service-signal service-signal--${service.status}`}><ApiOutlined /></span>
                        <div><div><strong>{service.name}</strong><Tag color={serviceStatus[service.status].color}>{serviceStatus[service.status].label}</Tag></div><p>{service.detail}</p></div>
                        <aside><strong>{service.uptime}%</strong><span>P95 {service.latency_p95_ms} ms</span></aside>
                      </article>
                    ))}
                  </div>
                </section>
                <div className="operations-side-stack">
                  <section className="panel incident-panel">
                    <div className="panel-head"><div><span className="panel-kicker">INCIDENTS</span><h3>事故与降级</h3></div><Tag>{dashboard.incidents.length}</Tag></div>
                    <div className="incident-list">
                      {dashboard.incidents.map((incident) => (
                        <article key={incident.id}>
                          <div><Tag color={incident.severity === "sev1" || incident.severity === "sev2" ? "error" : incident.severity === "sev3" ? "warning" : "default"}>{incident.severity.toUpperCase()}</Tag><strong>{incident.title}</strong></div>
                          <p>{incident.detail}</p>
                          <footer><span>{incident.owner} · {formatTime(incident.updated_at)}</span><Space size={4}>{incident.status !== "resolved" && incident.status !== "acknowledged" && <Button size="small" onClick={async () => { await actOnIncident(incident.id, "acknowledge"); await load(); }}>确认</Button>}{incident.status !== "resolved" && <Button type="link" size="small" onClick={async () => { await actOnIncident(incident.id, "resolve"); await load(); }}>关闭</Button>}</Space></footer>
                        </article>
                      ))}
                    </div>
                  </section>
                  <section className="panel backup-panel">
                    <div className="panel-head"><div><span className="panel-kicker">BACKUP &amp; RESTORE</span><h3>备份恢复</h3></div><DatabaseOutlined /></div>
                    <div className="backup-list">
                      {dashboard.backups.slice(0, 4).map((backup) => (
                        <div key={backup.id}><CheckCircleFilled /><span><strong>{backup.backup_type === "full" ? "全量备份" : "增量备份"}</strong><small>{formatTime(backup.completed_at)} · {bytesLabel(backup.size_bytes)}</small></span><Tag color={backup.restore_verified ? "success" : "warning"}>{backup.restore_verified ? "恢复已校验" : "待校验"}</Tag></div>
                      ))}
                    </div>
                  </section>
                </div>
              </div>
            )}

            {activeView === "access" && (
              <div className="access-grid">
                <section className="panel organization-panel">
                  <div className="organization-identity"><span><SafetyCertificateFilled /></span><div><small>ENTERPRISE ORGANIZATION</small><h2>{dashboard.organization.name}</h2><p>{dashboard.organization.domain} · {dashboard.organization.plan}</p></div></div>
                  <div className="organization-controls"><div><LockOutlined /><span><strong>统一身份 SSO</strong><small>企业身份源强制接入</small></span><Tag color={dashboard.organization.sso_enforced ? "success" : "default"}>{dashboard.organization.sso_enforced ? "已执行" : "未启用"}</Tag></div><div><SafetyCertificateOutlined /><span><strong>多因素认证</strong><small>会话超时 {dashboard.organization.session_timeout_minutes} 分钟</small></span><Tag color={dashboard.organization.mfa_required ? "success" : "default"}>{dashboard.organization.mfa_required ? "强制" : "可选"}</Tag></div></div>
                </section>
                <section className="panel member-panel">
                  <div className="panel-head"><div><span className="panel-kicker">MEMBERS &amp; RBAC</span><h3>成员与最小权限</h3></div><Tag>{dashboard.users.length} 人</Tag></div>
                  <div className="member-list">
                    {dashboard.users.map((user) => (
                      <button key={user.id} onClick={() => openUser(user)}>
                        <Avatar>{user.initial}</Avatar><div><strong>{user.name}</strong><span>{user.email}</span></div><Tag>{user.role_name}</Tag><span className={user.mfa_enabled ? "is-secure" : "is-risk"}>{user.mfa_enabled ? <SafetyCertificateOutlined /> : <WarningFilled />} {user.mfa_enabled ? "MFA" : "未启用 MFA"}</span><b>→</b>
                      </button>
                    ))}
                  </div>
                </section>
                <section className="panel role-panel">
                  <div className="panel-head"><div><span className="panel-kicker">ROLE BOUNDARIES</span><h3>角色权限边界</h3></div><TeamOutlined /></div>
                  <div className="role-grid">{dashboard.roles.map((role) => <article key={role.id}><span><UserOutlined /></span><strong>{role.name}</strong><p>{role.description}</p><small>{role.permissions.includes("*") ? "全局管理权限" : `${role.permissions.length} 项最小权限`}</small></article>)}</div>
                </section>
              </div>
            )}

            {activeView === "models" && (
              <div className="model-governance-grid">
                <section className="panel model-panel">
                  <div className="panel-head"><div><span className="panel-kicker">MODEL ROUTING &amp; QUOTA</span><h3>模型、费用与降级</h3></div><ThunderboltOutlined /></div>
                  <div className="model-list">
                    {dashboard.models.map((model) => {
                      const usage = Math.round(model.spent_amount * 100 / model.monthly_budget);
                      return <button key={model.id} onClick={() => openModel(model)}><span className={`model-provider model-provider--${model.routing_class}`}><ThunderboltOutlined /></span><div><div><strong>{model.provider} · {model.model_name}</strong><Tag color={model.status === "active" ? "success" : model.status === "degraded" ? "warning" : "default"}>{model.status}</Tag></div><p>{model.routing_class} 路由 · {model.allowed_data_classifications.join(" / ")} · 降级 {model.fallback_model ?? "无"}</p><Progress percent={usage} size="small" strokeColor={usage >= model.quota_warning_percent ? "#b96f57" : "#687c67"} /></div><aside><strong>¥{model.spent_amount.toLocaleString()}</strong><span>/ ¥{model.monthly_budget.toLocaleString()}</span></aside></button>;
                    })}
                  </div>
                </section>
                <section className="panel evaluation-panel">
                  <div className="panel-head"><div><span className="panel-kicker">EVALUATION</span><h3>离线评测与线上质量</h3></div><Tag color="success">引用完整率 100%</Tag></div>
                  <div className="evaluation-table"><div className="evaluation-row evaluation-row--head"><span>评测集</span><span>准确率</span><span>拒答率</span><span>P95</span><span>单次成本</span></div>{dashboard.evaluations.map((evaluation) => <div className="evaluation-row" key={evaluation.id}><span><strong>{evaluation.dataset_name}</strong><small>{evaluation.sample_size} 条样本</small></span><span>{evaluation.accuracy}%</span><span>{evaluation.refusal_rate}%</span><span>{evaluation.latency_p95_ms} ms</span><span>¥{evaluation.cost_per_run}</span></div>)}</div>
                </section>
              </div>
            )}

            {activeView === "security" && (
              <section className="panel policy-panel">
                <div className="panel-head"><div><span className="panel-kicker">POLICY GATES</span><h3>安全、隐私与合规策略</h3></div><p>策略变更实时审计，高敏操作二次确认</p></div>
                <div className="policy-grid">
                  {dashboard.policies.map((policy) => (
                    <article key={policy.id}>
                      <span className={`policy-icon policy-icon--${policy.category}`}>{policy.category === "identity" ? <LockOutlined /> : policy.category === "export" ? <ExportOutlined /> : policy.category === "retention" ? <FieldTimeOutlined /> : policy.category === "model" ? <ThunderboltOutlined /> : <SafetyCertificateOutlined />}</span>
                      <div><div><strong>{policy.name}</strong><Tag color={policy.status === "enforced" ? "success" : policy.status === "monitoring" ? "warning" : "default"}>{policy.status === "enforced" ? "强制执行" : policy.status === "monitoring" ? "监控" : "停用"}</Tag></div><p>{Object.entries(policy.value).map(([key, value]) => `${key}: ${String(value)}`).join(" · ")}</p><small>更新于 {formatTime(policy.updated_at)}</small></div>
                      <Switch checked={policy.status === "enforced"} onChange={async (checked) => { await updateAdminPolicy(policy.id, { status: checked ? "enforced" : "monitoring" }); await load(); messageApi.success("策略状态已更新"); }} />
                    </article>
                  ))}
                </div>
              </section>
            )}

            {activeView === "audit" && (
              <section className="panel audit-panel">
                <div className="panel-head"><div><span className="panel-kicker">IMMUTABLE TRAIL</span><h3>审计事件</h3></div><Input allowClear prefix={<AuditOutlined />} value={auditQuery} onChange={(event) => setAuditQuery(event.target.value)} placeholder="搜索操作者、动作或对象…" /></div>
                <div className="audit-list">
                  {filteredAudits.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的审计事件" />}
                  {filteredAudits.map((event) => (
                    <article key={event.id}><span className="audit-sequence">{String(event.id).padStart(4, "0")}</span><div><div><strong>{actionLabels[event.action] ?? event.action}</strong><Tag>{event.entity_type}</Tag></div><p>{event.actor_name} · {event.entity_id}</p><small>{Object.entries(event.detail).slice(0, 3).map(([key, value]) => `${key}: ${String(value)}`).join(" · ")}</small></div><time>{formatTime(event.created_at)}</time></article>
                  ))}
                </div>
              </section>
            )}
          </>
        ) : (
          !loading && <div className="module-empty"><WarningFilled /><h2>管理中心暂不可用</h2><Button onClick={() => void load()}>重新加载</Button></div>
        )}
      </Spin>

      <Drawer title={null} size={520} open={Boolean(selectedUser)} onClose={() => setSelectedUser(null)} className="admin-drawer">
        {selectedUser && <div className="admin-drawer-content"><div className="drawer-eyebrow">MEMBER ACCESS</div><div className="admin-user-title"><Avatar size={54}>{selectedUser.initial}</Avatar><div><h2>{selectedUser.name}</h2><p>{selectedUser.email}</p></div></div><div className="admin-form"><label><span>角色</span><Select value={userRole} onChange={setUserRole} options={dashboard?.roles.map((role) => ({ value: role.id, label: role.name }))} /></label><label><span>账号状态</span><Select value={userStatus} onChange={setUserStatus} options={[{ value: "active", label: "正常" }, { value: "invited", label: "待加入" }, { value: "suspended", label: "已停用" }]} /></label><label><span>导出权限</span><Select value={userExport} onChange={setUserExport} options={[{ value: "none", label: "禁止导出" }, { value: "standard", label: "标准导出" }, { value: "sensitive", label: "高敏导出（需审批）" }]} /></label><div className="admin-switch-row"><span><strong>多因素认证</strong><small>高敏导出和管理操作需要额外认证</small></span><Switch checked={userMfa} onChange={setUserMfa} /></div></div><div className="admin-risk-note"><WarningFilled /><p>权限变更会立即影响页面、搜索、接口与导出，并记录操作者、时间和变更范围。</p></div><Button block type="primary" loading={submitting} onClick={() => void saveUser()}>保存访问边界</Button></div>}
      </Drawer>

      <Modal title="模型路由与配额" open={Boolean(selectedModel)} onCancel={() => setSelectedModel(null)} onOk={() => void saveModel()} confirmLoading={submitting} okText="保存策略" cancelText="取消">
        {selectedModel && <div className="admin-form model-config-form"><div className="model-config-title"><span><ThunderboltOutlined /></span><div><strong>{selectedModel.provider} · {selectedModel.model_name}</strong><p>{selectedModel.version} · 成功率 {selectedModel.success_rate}% · P95 {selectedModel.latency_p95_ms} ms</p></div></div><label><span>运行状态</span><Select value={modelStatus} onChange={setModelStatus} options={[{ value: "active", label: "启用" }, { value: "degraded", label: "降级" }, { value: "disabled", label: "停用" }]} /></label><label><span>月度预算</span><InputNumber value={modelBudget} onChange={(value) => setModelBudget(value ?? 0)} min={0} addonBefore="¥" style={{ width: "100%" }} /></label><label><span>降级模型</span><Select allowClear value={modelFallback} onChange={setModelFallback} options={dashboard?.models.filter((item) => item.id !== selectedModel.id).map((item) => ({ value: item.id, label: `${item.provider} · ${item.model_name}` }))} /></label><div className="admin-risk-note"><SafetyCertificateOutlined /><p>受限数据只会路由到允许 restricted 分类的模型；预算达到阈值时自动告警并执行降级。</p></div></div>}
      </Modal>
    </div>
  );
}
