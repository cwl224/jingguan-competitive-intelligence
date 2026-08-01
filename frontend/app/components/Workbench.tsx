"use client";

import {
  ApartmentOutlined,
  AppstoreOutlined,
  ArrowDownOutlined,
  ArrowUpOutlined,
  BellOutlined,
  CalendarOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  LinkOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MoreOutlined,
  PlusOutlined,
  SearchOutlined,
  SettingOutlined,
  SyncOutlined,
  TeamOutlined,
  ThunderboltFilled,
  WarningFilled,
} from "@ant-design/icons";
import {
  Avatar,
  Badge,
  Button,
  ConfigProvider,
  Drawer,
  Dropdown,
  Empty,
  Input,
  Modal,
  Progress,
  Segmented,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  message,
} from "antd";
import * as echarts from "echarts";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  claimReview,
  createProject as createProjectRequest,
  fetchInsight,
  fetchWorkbench,
  generateReport,
  type Insight,
  type InsightDetail,
  type ProjectCreatePayload,
  type RangeKey,
  type TrendData,
  type WorkbenchData,
} from "../lib/api";
import DataSourceManagement from "./DataSourceManagement";
import DataProcessing from "./DataProcessing";
import KnowledgeStorage from "./KnowledgeStorage";
import TaskOrchestration from "./TaskOrchestration";
import CompetitiveAnalysis from "./CompetitiveAnalysis";
import RetrievalRAG from "./RetrievalRAG";
import ReportAlertCenter from "./ReportAlertCenter";
import AdminSecurityOperations from "./AdminSecurityOperations";

const navItems = [
  { key: "workbench", label: "工作台", icon: <AppstoreOutlined />, group: "analysis" },
  { key: "competitors", label: "竞品分析 Agent", icon: <ApartmentOutlined />, group: "analysis" },
  { key: "rag", label: "检索与 RAG", icon: <SearchOutlined />, group: "analysis" },
  { key: "intelligence", label: "情报库", icon: <DatabaseOutlined />, group: "analysis" },
  { key: "reports", label: "分析与报告", icon: <FileTextOutlined />, group: "analysis" },
  { key: "operations", label: "数据运营", icon: <SyncOutlined />, group: "governance" },
  { key: "processing", label: "清洗与抽取", icon: <ExperimentOutlined />, group: "governance" },
  { key: "orchestration", label: "任务编排", icon: <DeploymentUnitOutlined />, group: "governance" },
  { key: "settings", label: "系统管理", icon: <SettingOutlined />, group: "governance" },
];

const rangeKeys: Record<string, RangeKey> = {
  "24 小时": "24h",
  "7 天": "7d",
  "30 天": "30d",
};

function TrendChart({ trend }: { trend: TrendData }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const maxValue = Math.max(10, ...trend.events);

    chart.setOption({
      animationDuration: 700,
      color: ["#687c67", "#c58c5d"],
      grid: { top: 26, right: 12, bottom: 26, left: 36 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(31, 35, 31, .94)",
        borderWidth: 0,
        textStyle: { color: "#fff", fontSize: 12 },
        padding: [9, 12],
        axisPointer: { type: "line", lineStyle: { color: "rgba(104,124,103,.28)" } },
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: trend.labels,
        axisLine: { lineStyle: { color: "#e8e4dc" } },
        axisTick: { show: false },
        axisLabel: { color: "#99968f", fontSize: 11, margin: 12 },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: Math.ceil(maxValue / 10) * 10,
        splitNumber: 4,
        axisLabel: { color: "#aaa79f", fontSize: 11 },
        splitLine: { lineStyle: { color: "#f0ede7", type: "dashed" } },
      },
      series: [
        {
          name: "有效事件",
          type: "line",
          smooth: 0.42,
          symbol: "circle",
          symbolSize: 6,
          showSymbol: false,
          lineStyle: { width: 2.5 },
          data: trend.events,
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(104,124,103,.28)" },
              { offset: 1, color: "rgba(104,124,103,0)" },
            ]),
          },
        },
        {
          name: "高影响",
          type: "line",
          smooth: 0.35,
          symbol: "circle",
          symbolSize: 5,
          showSymbol: false,
          lineStyle: { width: 2 },
          data: trend.high_impact,
        },
      ],
    });

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [trend]);

  return <div ref={ref} className="trend-chart" role="img" aria-label="竞品动态趋势图" />;
}

function SourceHealthChart({ score }: { score: number }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chart.setOption({
      animationDuration: 800,
      series: [
        {
          type: "gauge",
          startAngle: 215,
          endAngle: -35,
          radius: "96%",
          center: ["50%", "54%"],
          min: 0,
          max: 100,
          pointer: { show: false },
          progress: { show: true, width: 9, roundCap: true, itemStyle: { color: "#687c67" } },
          axisLine: { lineStyle: { width: 9, color: [[1, "#ece8e0"]] } },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          detail: {
            valueAnimation: true,
            formatter: "{value}%",
            color: "#222721",
            fontSize: 28,
            fontWeight: 500,
            offsetCenter: [0, "4%"],
          },
          title: { show: false },
          data: [{ value: score }],
        },
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [score]);

  return <div ref={ref} className="health-chart" role="img" aria-label={`数据源健康度 ${score}%`} />;
}

function MetricCard({
  label,
  value,
  unit,
  delta,
  deltaDown = false,
  note,
  accent = false,
}: {
  label: string;
  value: string;
  unit?: string;
  delta: string;
  deltaDown?: boolean;
  note: string;
  accent?: boolean;
}) {
  return (
    <article className={`metric-card${accent ? " metric-card--accent" : ""}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value-row">
        <span className="metric-value">{value}</span>
        {unit && <span className="metric-unit">{unit}</span>}
      </div>
      <div className="metric-foot">
        <span className={deltaDown ? "delta delta--down" : "delta"}>
          {deltaDown ? <ArrowDownOutlined /> : <ArrowUpOutlined />} {delta}
        </span>
        <span>{note}</span>
      </div>
    </article>
  );
}

export default function Workbench() {
  const [collapsed, setCollapsed] = useState(false);
  const [range, setRange] = useState("7 天");
  const [dashboard, setDashboard] = useState<WorkbenchData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedInsight, setSelectedInsight] = useState<InsightDetail | null>(null);
  const [insightLoading, setInsightLoading] = useState(false);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [projectTemplate, setProjectTemplate] = useState<ProjectCreatePayload["template"]>("daily");
  const [projectRegions, setProjectRegions] = useState<ProjectCreatePayload["regions"]>(["cn", "global"]);
  const [creatingProject, setCreatingProject] = useState(false);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [ragSeedQuestion, setRagSeedQuestion] = useState({ text: "", id: 0 });
  const [activeNav, setActiveNav] = useState("workbench");
  const [messageApi, contextHolder] = message.useMessage();

  const loadDashboard = useCallback(async (projectId?: string, nextRange = "7 天") => {
    setLoading(true);
    try {
      const data = await fetchWorkbench(projectId, rangeKeys[nextRange] ?? "7d");
      setDashboard(data);
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "工作台数据加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadDashboard(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadDashboard]);

  const todayLabel = useMemo(
    () =>
      new Intl.DateTimeFormat("zh-CN", {
        month: "long",
        day: "numeric",
        weekday: "long",
      }).format(new Date()),
    [],
  );

  const handleNav = (key: string, label: string) => {
    if (key === "workbench" || key === "competitors" || key === "rag" || key === "intelligence" || key === "reports" || key === "operations" || key === "processing" || key === "orchestration" || key === "settings") {
      setActiveNav(key);
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    setActiveNav(key);
    messageApi.open({ type: "info", content: `${label}暂不可用` });
  };

  const createProject = async () => {
    if (!projectName.trim()) {
      messageApi.warning("请先填写项目名称");
      return;
    }
    setCreatingProject(true);
    try {
      const project = await createProjectRequest({
        name: projectName.trim(),
        template: projectTemplate,
        regions: projectRegions,
      });
      setProjectModalOpen(false);
      setProjectName("");
      setProjectTemplate("daily");
      setProjectRegions(["cn", "global"]);
      await loadDashboard(project.id, range);
      messageApi.success(`“${project.name}”已创建并切换为当前项目`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "项目创建失败");
    } finally {
      setCreatingProject(false);
    }
  };

  const changeRange = async (nextRange: string) => {
    setRange(nextRange);
    await loadDashboard(dashboard?.project.id, nextRange);
  };

  const openInsight = async (insight: Insight) => {
    setSelectedInsight({ ...insight, recommendation: "", evidence: [] });
    setInsightLoading(true);
    try {
      setSelectedInsight(await fetchInsight(insight.id));
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "证据详情加载失败");
    } finally {
      setInsightLoading(false);
    }
  };

  const claimReviewItem = async (reviewId: number, field: string) => {
    try {
      await claimReview(reviewId);
      await loadDashboard(dashboard?.project.id, range);
      messageApi.success(`已领取：${field}`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "复核项领取失败");
    }
  };

  const createMorningReport = async () => {
    if (!dashboard) return;
    setGeneratingReport(true);
    try {
      await generateReport(dashboard.project.id);
      await loadDashboard(dashboard.project.id, range);
      messageApi.success("晨报任务已提交，正在生成");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "报告任务创建失败");
    } finally {
      setGeneratingReport(false);
    }
  };

  const submitSearch = () => {
    const query = searchQuery.trim();
    if (!query || !dashboard) return;
    setRagSeedQuestion((current) => ({ text: query, id: current.id + 1 }));
    setActiveNav("rag");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (!dashboard) {
    return (
      <div className="api-state">
        {loading ? (
          <><Spin size="large" /><p>正在连接竞品情报服务…</p></>
        ) : (
          <>
            <WarningFilled />
            <h1>暂时无法加载工作台</h1>
            <p>{loadError ?? "请确认后端服务已启动。"}</p>
            <Button type="primary" onClick={() => void loadDashboard()}>重新连接</Button>
          </>
        )}
      </div>
    );
  }

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#687c67",
          colorInfo: "#687c67",
          colorSuccess: "#687c67",
          colorWarning: "#bc7b45",
          colorError: "#ad5c51",
          colorText: "#242922",
          colorTextSecondary: "#7e8079",
          colorBorder: "#e7e3dc",
          borderRadius: 10,
          fontFamily: '"Noto Sans SC", "Yu Gothic UI", "Microsoft YaHei", sans-serif',
          boxShadowSecondary: "0 20px 50px rgba(55, 59, 50, .14)",
        },
        components: {
          Button: { controlHeight: 40, fontWeight: 500 },
          Input: { controlHeight: 40 },
          Segmented: { trackBg: "#f3f0ea", itemSelectedBg: "#fff" },
        },
      }}
    >
      {contextHolder}
      <div className="app-shell">
        <aside className={`sidebar${collapsed ? " sidebar--collapsed" : ""}`}>
          <div className="brand-block">
            <div className="brand-mark" aria-hidden="true">
              <span />
            </div>
            {!collapsed && (
              <div className="brand-copy">
                <strong>镜观</strong>
                <small>COMPETITIVE INTELLIGENCE</small>
              </div>
            )}
          </div>

          <div className="project-switcher">
            {!collapsed && <span className="project-switcher__label">当前项目</span>}
            <Dropdown
              menu={{
                items: [
                  ...dashboard.projects.map((project) => ({
                    key: `project:${project.id}`,
                    label: project.name,
                  })),
                  { type: "divider" },
                  { key: "manage", label: "管理全部项目" },
                ],
                onClick: ({ key }) => {
                  if (key === "manage") {
                    setActiveNav("settings");
                    return;
                  }
                  const projectId = key.replace("project:", "");
                  void loadDashboard(projectId, range);
                },
              }}
              placement="bottomLeft"
            >
              <button className="project-pill" aria-label="切换当前项目">
                <span className="project-avatar">{dashboard.project.avatar}</span>
                {!collapsed && (
                  <>
                    <span className="project-pill__text">{dashboard.project.name}</span>
                    <MoreOutlined />
                  </>
                )}
              </button>
            </Dropdown>
          </div>

          <nav className="main-nav" aria-label="主导航">
            {!collapsed && <div className="nav-section-label">分析空间</div>}
            {navItems.filter((item) => item.group === "analysis").map((item) => (
              <Tooltip key={item.key} title={collapsed ? item.label : ""} placement="right">
                <button
                  className={`nav-item${activeNav === item.key ? " nav-item--active" : ""}`}
                  onClick={() => handleNav(item.key, item.label)}
                >
                  <span className="nav-icon">{item.icon}</span>
                  {!collapsed && <span>{item.label}</span>}
                  {item.key === "workbench" && !collapsed && <i className="nav-dot" />}
                </button>
              </Tooltip>
            ))}
            {!collapsed && <div className="nav-section-label nav-section-label--second">治理与配置</div>}
            {navItems.filter((item) => item.group === "governance").map((item) => (
              <Tooltip key={item.key} title={collapsed ? item.label : ""} placement="right">
                <button
                  className={`nav-item${activeNav === item.key ? " nav-item--active" : ""}`}
                  onClick={() => handleNav(item.key, item.label)}
                >
                  <span className="nav-icon">{item.icon}</span>
                  {!collapsed && <span>{item.label}</span>}
                </button>
              </Tooltip>
            ))}
          </nav>

          <div className="sidebar-bottom">
            {!collapsed && (
              <div className="collection-status">
                <div className="collection-status__top">
                  <span><i /> {dashboard.source_health.abnormal ? "部分来源异常" : "采集服务正常"}</span>
                  <strong>{dashboard.source_health.score}%</strong>
                </div>
                <Progress percent={dashboard.source_health.score} showInfo={false} strokeColor="#687c67" railColor="#e7e2d9" size="small" />
                <small>最后同步 · {dashboard.source_health.last_sync}</small>
              </div>
            )}
            <button className="collapse-button" onClick={() => setCollapsed((value) => !value)} aria-label="折叠侧边栏">
              {collapsed ? <MenuUnfoldOutlined /> : <><MenuFoldOutlined /> <span>收起导航</span></>}
            </button>
          </div>
        </aside>

        <main className="main-area">
          <header className="topbar">
            <div className="mobile-brand">镜观</div>
            <div className="search-wrap">
              <SearchOutlined />
              <Input
                variant="borderless"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                onPressEnter={submitSearch}
                placeholder="向情报库提问，回车进入 RAG…"
                aria-label="全局搜索"
              />
              <kbd>⌘ K</kbd>
            </div>
            <div className="topbar-actions">
              <Tooltip title="团队成员">
                <Button type="text" shape="circle" icon={<TeamOutlined />} onClick={() => setActiveNav("settings")} />
              </Tooltip>
              <Badge dot offset={[-5, 6]} color="#b86f5b">
                <Tooltip title={`${dashboard.headline.priority_changes} 条重大预警`}>
                  <Button type="text" shape="circle" icon={<BellOutlined />} onClick={() => setActiveNav("reports")} />
                </Tooltip>
              </Badge>
              <div className="topbar-separator" />
              <button className="profile-button">
                <Avatar size={34} style={{ background: "#263028", color: "#f2eee6" }}>{dashboard.user.initial}</Avatar>
                <span>{dashboard.user.name}</span>
              </button>
            </div>
          </header>

          <div className={`workspace${activeNav === "operations" ? " workspace--sources" : activeNav === "processing" ? " workspace--processing" : activeNav === "orchestration" ? " workspace--orchestration" : activeNav === "intelligence" ? " workspace--knowledge" : activeNav === "rag" ? " workspace--rag" : activeNav === "competitors" ? " workspace--analysis" : activeNav === "reports" ? " workspace--reports" : activeNav === "settings" ? " workspace--admin" : ""}`}>
            {activeNav === "operations" ? (
              <DataSourceManagement
                project={dashboard.project}
                onBack={() => setActiveNav("workbench")}
                onDashboardRefresh={() => loadDashboard(dashboard.project.id, range)}
              />
            ) : activeNav === "orchestration" ? (
              <TaskOrchestration
                project={dashboard.project}
                onDashboardRefresh={() => loadDashboard(dashboard.project.id, range)}
              />
            ) : activeNav === "processing" ? (
              <DataProcessing project={dashboard.project} />
            ) : activeNav === "competitors" ? (
              <CompetitiveAnalysis key={dashboard.project.id} project={dashboard.project} />
            ) : activeNav === "rag" ? (
              <RetrievalRAG
                key={`${dashboard.project.id}:${ragSeedQuestion.id}`}
                project={dashboard.project}
                initialQuestion={ragSeedQuestion.text}
              />
            ) : activeNav === "intelligence" ? (
              <KnowledgeStorage key={dashboard.project.id} project={dashboard.project} />
            ) : activeNav === "reports" ? (
              <ReportAlertCenter key={dashboard.project.id} project={dashboard.project} />
            ) : activeNav === "settings" ? (
              <AdminSecurityOperations />
            ) : (
            <>
            <section className="page-heading">
              <div>
                <div className="eyebrow">{todayLabel} · 数据截止 {dashboard.data_cutoff}</div>
                <h1>{dashboard.headline.greeting}</h1>
                <p>昨夜新增 <strong>{dashboard.headline.new_changes}</strong> 条有效变化，其中 <strong>{dashboard.headline.priority_changes}</strong> 条值得优先关注。</p>
              </div>
              <div className="heading-actions">
                <Button icon={<CalendarOutlined />} loading={generatingReport} onClick={() => void createMorningReport()}>生成晨报</Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setProjectModalOpen(true)}>新建分析</Button>
              </div>
            </section>

            <section className="summary-strip">
              <div className="summary-orb" aria-hidden="true" />
              <div className="summary-kicker"><ThunderboltFilled /> 今日要点</div>
              <h2>{dashboard.daily_brief.title}</h2>
              <p>{dashboard.daily_brief.summary}</p>
              <button
                className="text-link"
                disabled={!dashboard.daily_brief.insight_id}
                onClick={() => {
                  const insight = dashboard.insights.find((item) => item.id === dashboard.daily_brief.insight_id);
                  if (insight) void openInsight(insight);
                }}
              >查看证据摘要 <span>→</span></button>
              <div className="summary-meta">
                <span>{dashboard.daily_brief.evidence_count} 条证据</span><i />
                <span>置信度 {dashboard.daily_brief.confidence}%</span><i />
                <span>{dashboard.daily_brief.impact_level === "high" ? "高影响" : dashboard.daily_brief.impact_level === "medium" ? "中影响" : "低影响"}</span>
              </div>
            </section>

            <section className="metric-grid" aria-label="项目概览指标">
              {dashboard.metrics.map((metric) => (
                <MetricCard
                  key={metric.key}
                  label={metric.label}
                  value={metric.value}
                  unit={metric.unit ?? undefined}
                  delta={metric.delta}
                  deltaDown={metric.trend === "down"}
                  note={metric.note}
                  accent={metric.accent}
                />
              ))}
            </section>

            <section className="dashboard-grid">
              <article className="panel panel--trend">
                <div className="panel-head">
                  <div>
                    <span className="panel-kicker">ACTIVITY</span>
                    <h3>竞品动态趋势</h3>
                  </div>
                  <div className="panel-head-actions">
                    <div className="legend"><span className="legend-main" />有效事件 <span className="legend-alert" />高影响</div>
                    <Segmented options={["24 小时", "7 天", "30 天"]} value={range} onChange={(value) => void changeRange(String(value))} size="small" />
                  </div>
                </div>
                <TrendChart trend={dashboard.trend} />
              </article>

              <article className="panel panel--health">
                <div className="panel-head">
                  <div>
                    <span className="panel-kicker">SOURCE HEALTH</span>
                    <h3>数据源健康</h3>
                  </div>
                  <Button type="text" size="small" icon={<MoreOutlined />} aria-label="更多数据源操作" />
                </div>
                <SourceHealthChart score={dashboard.source_health.score} />
                <div className="health-caption">整体健康度</div>
                <div className="health-stats">
                  <div><strong>{dashboard.source_health.normal}</strong><span><i className="status-dot status-dot--good" />正常</span></div>
                  <div><strong>{dashboard.source_health.abnormal}</strong><span><i className="status-dot status-dot--warn" />异常</span></div>
                  <div><strong>{dashboard.source_health.disabled}</strong><span><i className="status-dot status-dot--muted" />停用</span></div>
                </div>
                <button className="panel-footer-link" onClick={() => setActiveNav("operations")}>查看 {dashboard.source_health.total} 个数据源 <span>→</span></button>
              </article>

              <article className="panel panel--insights">
                <div className="panel-head">
                  <div>
                    <span className="panel-kicker">LATEST CHANGES</span>
                    <h3>最新变化</h3>
                  </div>
                  <Button type="text" size="small">查看全部</Button>
                </div>
                <div className="insight-list">
                  {dashboard.insights.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可信变化" />}
                  {dashboard.insights.map((item) => (
                    <button key={item.id} className="insight-row" onClick={() => void openInsight(item)}>
                      <div className={`impact-marker impact-marker--${item.level}`} />
                      <div className="insight-time">{item.time}</div>
                      <div className="insight-body">
                        <div className="insight-tags">
                          <Tag variant="filled" className={`type-tag type-tag--${item.type}`}>{item.type}</Tag>
                          <span>{item.company}</span>
                        </div>
                        <h4>{item.title}</h4>
                        <p>{item.summary}</p>
                        <div className="insight-meta"><LinkOutlined /> {item.sources} 个来源 <span>·</span> 置信度 {item.confidence}%</div>
                      </div>
                      <span className="row-arrow">→</span>
                    </button>
                  ))}
                </div>
              </article>

              <div className="side-stack">
                <article className="panel panel--reviews">
                  <div className="panel-head">
                    <div>
                      <span className="panel-kicker">REVIEW QUEUE</span>
                      <h3>待人工复核</h3>
                    </div>
                    <Badge count={dashboard.review_queue.total} color="#6d7f6b" showZero />
                  </div>
                  <div className="review-list">
                    {dashboard.review_queue.items.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="复核队列已清空" />}
                    {dashboard.review_queue.items.map((item) => (
                      <button key={item.id} className="review-row" onClick={() => void claimReviewItem(item.id, item.field)}>
                        <Avatar size={34} className="company-avatar">{item.company.slice(0, 1)}</Avatar>
                        <div className="review-copy"><strong>{item.field}</strong><span>{item.company} · {item.time}</span></div>
                        <Tag variant="filled" className={`review-tag review-tag--${item.tone}`}>{item.reason}</Tag>
                      </button>
                    ))}
                  </div>
                  <button className="panel-footer-link" onClick={() => messageApi.info("完整复核工作台将在下一阶段接入")}>进入复核队列 <span>→</span></button>
                </article>

                <article className="panel panel--reports">
                  <div className="panel-head">
                    <div>
                      <span className="panel-kicker">DELIVERY</span>
                      <h3>报告交付</h3>
                    </div>
                    <Button type="text" size="small" icon={<MoreOutlined />} aria-label="更多报告操作" />
                  </div>
                  <div className="report-list">
                    {dashboard.reports.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无报告任务" />}
                    {dashboard.reports.map((item) => (
                      <div className="report-row" key={item.id}>
                        <div className="report-icon">
                          {item.state === "已交付" ? <CheckCircleFilled /> : item.state === "生成中" ? <SyncOutlined spin /> : <ClockCircleOutlined />}
                        </div>
                        <div className="report-copy">
                          <div><strong>{item.title}</strong><span>{item.state}</span></div>
                          <small>{item.meta}</small>
                          <Progress percent={item.progress} showInfo={false} size="small" strokeColor={item.state === "待审批" ? "#bd8a60" : "#687c67"} railColor="#eeeae3" />
                        </div>
                      </div>
                    ))}
                  </div>
                </article>
              </div>
            </section>
            </>
            )}
          </div>
        </main>
      </div>

      <Drawer
        title={null}
        size={480}
        open={Boolean(selectedInsight)}
        onClose={() => setSelectedInsight(null)}
        className="evidence-drawer"
      >
        {selectedInsight && (
          <Spin spinning={insightLoading}>
          <div className="drawer-content">
            <div className="drawer-eyebrow">洞察 #{String(selectedInsight.id).padStart(4, "0")}</div>
            <Space size={8} wrap>
              <Tag variant="filled" className={`type-tag type-tag--${selectedInsight.type}`}>{selectedInsight.type}</Tag>
              <Tag variant="filled">{selectedInsight.company}</Tag>
              <Tag variant="filled" color={selectedInsight.level === "high" ? "volcano" : "gold"}>{selectedInsight.level === "high" ? "高影响" : "中影响"}</Tag>
            </Space>
            <h2>{selectedInsight.title}</h2>
            <p className="drawer-summary">{selectedInsight.summary}</p>
            <div className="confidence-box">
              <div><span>结论置信度</span><strong>{selectedInsight.confidence}%</strong></div>
              <Progress percent={selectedInsight.confidence} showInfo={false} strokeColor="#687c67" railColor="#e9e5dd" />
              <small>由 {selectedInsight.sources} 个独立来源交叉验证 · 更新于今天 {selectedInsight.time}</small>
            </div>
            <div className="drawer-section-title">证据链</div>
            <div className="evidence-list">
              {!insightLoading && selectedInsight.evidence.length === 0 && (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可用证据" />
              )}
              {selectedInsight.evidence.map((item) => (
                <article key={item.id}>
                  <div>
                    <span className={`source-favicon${item.source_type === "cross_check" ? " source-favicon--warm" : ""}`}>{item.source_name.slice(0, 1)}</span>
                    <strong>{item.title}</strong>
                    <Tag color={item.source_type === "primary" ? "green" : undefined} variant="filled">{item.source_type === "primary" ? "主来源" : "交叉验证"}</Tag>
                  </div>
                  <p>“{item.excerpt}”</p>
                  <footer>
                    <span>{item.source_name} · {item.published_at}</span>
                    <Button type="link" size="small" icon={<LinkOutlined />} href={item.source_url} target="_blank" rel="noreferrer">打开原文</Button>
                  </footer>
                </article>
              ))}
            </div>
            <div className="drawer-section-title">建议动作</div>
            <div className="action-note"><WarningFilled /> <p>{selectedInsight.recommendation || "正在加载建议…"}</p></div>
            <div className="drawer-actions">
              <Button onClick={() => messageApi.success("已记录为有用反馈")}>标记有用</Button>
              <Button type="primary" onClick={() => messageApi.success("已加入专题报告素材")}>加入专题报告</Button>
            </div>
          </div>
          </Spin>
        )}
      </Drawer>

      <Modal
        title="新建分析项目"
        open={projectModalOpen}
        onCancel={() => setProjectModalOpen(false)}
        onOk={() => void createProject()}
        confirmLoading={creatingProject}
        okText="创建草稿"
        cancelText="取消"
      >
        <div className="project-form">
          <label>项目名称</label>
          <Input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="例如：智能办公软件竞品追踪" autoFocus />
          <label>分析模板</label>
          <Select value={projectTemplate} onChange={(value) => setProjectTemplate(value)} style={{ width: "100%" }} options={[
            { value: "daily", label: "竞品动态日报" },
            { value: "compare", label: "产品能力对比" },
            { value: "strategy", label: "专题战略研究" },
          ]} />
          <label>关注地区</label>
          <Select mode="multiple" value={projectRegions} onChange={(value) => setProjectRegions(value)} style={{ width: "100%" }} options={[
            { value: "cn", label: "中国" }, { value: "global", label: "全球" }, { value: "jp", label: "日本" }, { value: "sea", label: "东南亚" },
          ]} />
        </div>
      </Modal>
    </ConfigProvider>
  );
}
