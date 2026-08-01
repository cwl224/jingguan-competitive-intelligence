"use client";

import {
  AuditOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  FolderAddOutlined,
  FolderOpenOutlined,
  LinkOutlined,
  NodeIndexOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  TagsOutlined,
  WarningFilled,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Descriptions,
  Drawer,
  Dropdown,
  Empty,
  Input,
  Modal,
  Progress,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Timeline,
  Tooltip,
  message,
  type TableProps,
} from "antd";
import { useCallback, useEffect, useState } from "react";

import {
  addKnowledgeItemToCollection,
  createKnowledgeCollection,
  fetchKnowledgeItem,
  fetchKnowledgeOverview,
  removeKnowledgeItemFromCollection,
  reviewKnowledgeItem,
  type KnowledgeCollection,
  type KnowledgeItem,
  type KnowledgeItemDetail,
  type KnowledgeItemType,
  type KnowledgeOverview,
  type KnowledgeReviewStatus,
  type Project,
} from "../lib/api";

type Props = {
  project: Project;
};

const itemTypeMeta: Record<KnowledgeItemType, { label: string; color: string }> = {
  fact: { label: "事实", color: "green" },
  entity: { label: "实体", color: "blue" },
  event: { label: "事件", color: "gold" },
  insight: { label: "洞察", color: "purple" },
};

const reviewMeta: Record<KnowledgeReviewStatus, { label: string; color: string }> = {
  verified: { label: "已核验", color: "success" },
  review_required: { label: "待复核", color: "warning" },
  conflict: { label: "来源冲突", color: "error" },
};

const collectionColors = ["#687c67", "#8c6f56", "#796b91", "#557487", "#a36b61"];

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

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function reviewTag(status: KnowledgeReviewStatus) {
  const meta = reviewMeta[status];
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

export default function KnowledgeStorage({ project }: Props) {
  const [overview, setOverview] = useState<KnowledgeOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [itemType, setItemType] = useState<KnowledgeItemType | "all">("all");
  const [reviewStatus, setReviewStatus] = useState<KnowledgeReviewStatus | "all">("all");
  const [collectionId, setCollectionId] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<KnowledgeItemDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [collectionModalOpen, setCollectionModalOpen] = useState(false);
  const [collectionName, setCollectionName] = useState("");
  const [collectionDescription, setCollectionDescription] = useState("");
  const [collectionColor, setCollectionColor] = useState(collectionColors[0]);
  const [creatingCollection, setCreatingCollection] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchKnowledgeOverview(project.id, {
        query: appliedQuery || undefined,
        itemType: itemType === "all" ? undefined : itemType,
        reviewStatus: reviewStatus === "all" ? undefined : reviewStatus,
        collectionId: collectionId ?? undefined,
      });
      setOverview(data);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "情报库加载失败");
    } finally {
      setLoading(false);
    }
  }, [appliedQuery, collectionId, itemType, messageApi, project.id, reviewStatus]);

  useEffect(() => {
    const timeout = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timeout);
  }, [load]);

  const openDetail = async (item: KnowledgeItem) => {
    setDetailLoading(true);
    try {
      setSelectedItem(await fetchKnowledgeItem(item.id));
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "知识条目加载失败");
    } finally {
      setDetailLoading(false);
    }
  };

  const updateReview = async (status: KnowledgeReviewStatus) => {
    if (!selectedItem) return;
    setReviewBusy(true);
    try {
      const detail = await reviewKnowledgeItem(
        selectedItem.id,
        status,
        status === "verified" ? "已在情报库详情中核对来源、证据和时间" : "由分析师调整复核状态",
      );
      setSelectedItem(detail);
      await load();
      messageApi.success(`已更新为“${reviewMeta[status].label}”`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "复核状态更新失败");
    } finally {
      setReviewBusy(false);
    }
  };

  const createCollection = async () => {
    if (!collectionName.trim()) {
      messageApi.warning("请填写专题集合名称");
      return;
    }
    setCreatingCollection(true);
    try {
      const created = await createKnowledgeCollection({
        project_id: project.id,
        name: collectionName.trim(),
        description: collectionDescription.trim(),
        color: collectionColor,
      });
      setCollectionModalOpen(false);
      setCollectionName("");
      setCollectionDescription("");
      setCollectionColor(collectionColors[0]);
      setCollectionId(created.id);
      await load();
      messageApi.success(`专题“${created.name}”已创建`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "专题集合创建失败");
    } finally {
      setCreatingCollection(false);
    }
  };

  const addToCollection = async (itemId: string, collection: KnowledgeCollection) => {
    try {
      await addKnowledgeItemToCollection(collection.id, itemId);
      await load();
      if (selectedItem?.id === itemId) {
        setSelectedItem(await fetchKnowledgeItem(itemId));
      }
      messageApi.success(`已加入“${collection.name}”`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "加入专题失败");
    }
  };

  const removeFromCollection = async (itemId: string, collection: KnowledgeCollection) => {
    try {
      await removeKnowledgeItemFromCollection(collection.id, itemId);
      await load();
      setSelectedItem(await fetchKnowledgeItem(itemId));
      messageApi.success(`已从“${collection.name}”移除`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "移出专题失败");
    }
  };

  const collectionMenuItems = (overview?.collections ?? []).map((collection) => ({
    key: collection.id,
    label: collection.name,
    onClick: () => selectedItem && void addToCollection(selectedItem.id, collection),
  }));

  const columns: TableProps<KnowledgeItem>["columns"] = [
    {
      title: "知识条目",
      dataIndex: "title",
      width: 360,
      render: (_, item) => (
        <button className="knowledge-item-link" onClick={() => void openDetail(item)}>
          <span><Tag color={itemTypeMeta[item.item_type].color}>{itemTypeMeta[item.item_type].label}</Tag>{item.subject && <em>{item.subject}</em>}</span>
          <strong>{item.title}</strong>
          <small>{item.summary}</small>
        </button>
      ),
    },
    {
      title: "证据与来源",
      key: "source",
      width: 230,
      render: (_, item) => (
        <div className="knowledge-source-cell">
          <strong><LinkOutlined /> {item.source_name}</strong>
          <span>{item.source_count} 个来源 · {item.extraction_method}</span>
          <small>{item.evidence_excerpt}</small>
        </div>
      ),
    },
    {
      title: "可信度",
      key: "confidence",
      width: 142,
      render: (_, item) => (
        <div className="knowledge-confidence-cell">
          <Progress
            percent={item.confidence}
            showInfo={false}
            strokeColor={item.confidence >= 85 ? "#687c67" : item.confidence >= 70 ? "#ba885e" : "#ad5c51"}
            railColor="#ebe7df"
            size="small"
          />
          <span>{item.confidence}% · 质量 {item.quality_score}</span>
        </div>
      ),
    },
    {
      title: "状态",
      key: "status",
      width: 132,
      render: (_, item) => (
        <Space orientation="vertical" size={3}>
          {reviewTag(item.review_status)}
          {item.validity_status === "at_risk" && <Tag color="volcano">来源风险</Tag>}
          {item.validity_status === "expired" && <Tag>已失效</Tag>}
        </Space>
      ),
    },
    {
      title: "更新 / 专题",
      key: "updated",
      width: 142,
      render: (_, item) => (
        <div className="knowledge-updated-cell">
          <span>{formatTime(item.updated_at)}</span>
          <small><FolderOpenOutlined /> {item.collection_count} 个专题</small>
          <Button type="link" size="small" onClick={() => void openDetail(item)}>查看证据链</Button>
        </div>
      ),
    },
  ];

  const summary = overview?.summary;
  const storage = overview?.storage;
  const activeCollection = overview?.collections.find((item) => item.id === collectionId);

  return (
    <div className="knowledge-storage">
      {contextHolder}
      <section className="knowledge-page-heading">
        <div>
          <div className="eyebrow">INTELLIGENCE LIBRARY · {project.name}</div>
          <h1>数据与知识存储</h1>
          <p>原始快照只读留存，处理结果独立版本化；每条事实、实体、事件与洞察都可下钻到来源和证据位置。</p>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新</Button>
          <Button type="primary" icon={<FolderAddOutlined />} onClick={() => setCollectionModalOpen(true)}>新建专题</Button>
        </Space>
      </section>

      <section className="knowledge-summary-grid" aria-label="存储与知识概览">
        <article>
          <span className="knowledge-summary-icon"><DatabaseOutlined /></span>
          <div><small>原始材料</small><strong>{storage?.raw_documents ?? 0}</strong><p>{storage?.document_versions ?? 0} 个不可变版本 · {formatBytes(storage?.storage_bytes ?? 0)}</p></div>
        </article>
        <article>
          <span className="knowledge-summary-icon knowledge-summary-icon--items"><NodeIndexOutlined /></span>
          <div><small>知识条目</small><strong>{summary?.knowledge_items ?? 0}</strong><p>{overview?.type_counts.entity ?? 0} 实体 · {overview?.type_counts.event ?? 0} 事件</p></div>
        </article>
        <article>
          <span className="knowledge-summary-icon knowledge-summary-icon--evidence"><SafetyCertificateOutlined /></span>
          <div><small>证据覆盖</small><strong>{summary?.evidence_coverage ?? 0}<em>%</em></strong><p>{summary?.verified ?? 0} 条已通过质量门禁</p></div>
        </article>
        <article className={(summary?.review_required ?? 0) + (summary?.conflicts ?? 0) > 0 ? "knowledge-summary-card--alert" : ""}>
          <span className="knowledge-summary-icon knowledge-summary-icon--review"><WarningFilled /></span>
          <div><small>治理队列</small><strong>{(summary?.review_required ?? 0) + (summary?.conflicts ?? 0)}</strong><p>{summary?.review_required ?? 0} 待复核 · {summary?.conflicts ?? 0} 条冲突</p></div>
        </article>
      </section>

      <section className="knowledge-layer-panel">
        <div className="knowledge-layer-head">
          <div><span className="panel-kicker">IMMUTABLE → TRACEABLE → REUSABLE</span><h2>分层存储与证据链</h2></div>
          <span>最近更新 · {formatTime(summary?.latest_update ?? null)}</span>
        </div>
        <div className="knowledge-layer-flow">
          <article><span><DatabaseOutlined /></span><div><small>01 · RAW</small><strong>原始快照层</strong><p>响应、文件、哈希与版本链只读保存</p></div><b>{storage?.document_versions ?? 0}</b></article>
          <i>→</i>
          <article><span><FileTextOutlined /></span><div><small>02 · PROCESSED</small><strong>处理结果层</strong><p>正文、结构化字段与处理版本独立更新</p></div><b>{storage?.processed_documents ?? 0}</b></article>
          <i>→</i>
          <article><span><NodeIndexOutlined /></span><div><small>03 · KNOWLEDGE</small><strong>知识索引层</strong><p>事实、实体、事件和洞察统一检索</p></div><b>{summary?.knowledge_items ?? 0}</b></article>
        </div>
      </section>

      <section className="knowledge-library-shell">
        <aside className="knowledge-collections">
          <div className="knowledge-collections__head"><div><span className="panel-kicker">COLLECTIONS</span><h2>专题集合</h2></div><Tooltip title="新建专题"><Button type="text" shape="circle" icon={<PlusOutlined />} onClick={() => setCollectionModalOpen(true)} /></Tooltip></div>
          <button className={!collectionId ? "knowledge-collection--active" : ""} onClick={() => setCollectionId(null)}>
            <span className="knowledge-collection-dot knowledge-collection-dot--all"><DatabaseOutlined /></span>
            <span><strong>全部知识</strong><small>跨来源统一索引</small></span>
            <b>{summary?.knowledge_items ?? 0}</b>
          </button>
          {(overview?.collections ?? []).map((collection) => (
            <button key={collection.id} className={collectionId === collection.id ? "knowledge-collection--active" : ""} onClick={() => setCollectionId(collection.id)}>
              <span className="knowledge-collection-dot" style={{ background: collection.color }} />
              <span><strong>{collection.name}</strong><small>{collection.description || "暂无说明"}</small></span>
              <b>{collection.item_count}</b>
            </button>
          ))}
        </aside>

        <div className="knowledge-table-panel">
          <div className="knowledge-table-title">
            <div><span className="panel-kicker">KNOWLEDGE INDEX</span><h2>{activeCollection?.name ?? "全部知识条目"}</h2><p>{activeCollection?.description ?? "按类型、状态和关键词组合检索；缺失证据的条目不会自动进入报告。"}</p></div>
            <span>{overview?.items.length ?? 0} 条结果</span>
          </div>
          <div className="knowledge-table-toolbar">
            <Input.Search
              value={query}
              allowClear
              prefix={<FileSearchOutlined />}
              placeholder="搜索事实、实体、事件、标签或正文"
              onChange={(event) => setQuery(event.target.value)}
              onSearch={(value) => setAppliedQuery(value.trim())}
            />
            <Select
              value={itemType}
              onChange={setItemType}
              options={[
                { value: "all", label: "全部类型" },
                ...Object.entries(itemTypeMeta).map(([value, meta]) => ({ value, label: meta.label })),
              ]}
            />
            <Select
              value={reviewStatus}
              onChange={setReviewStatus}
              options={[
                { value: "all", label: "全部状态" },
                ...Object.entries(reviewMeta).map(([value, meta]) => ({ value, label: meta.label })),
              ]}
            />
          </div>
          <Table<KnowledgeItem>
            rowKey="id"
            loading={loading}
            dataSource={overview?.items ?? []}
            columns={columns}
            pagination={{ pageSize: 8, showSizeChanger: false, showTotal: (total) => `共 ${total} 条` }}
            scroll={{ x: 1000 }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配的知识条目" /> }}
          />
        </div>
      </section>

      <Drawer
        title="知识条目与证据链"
        size={680}
        open={Boolean(selectedItem)}
        onClose={() => setSelectedItem(null)}
        className="knowledge-detail-drawer"
        extra={selectedItem && (
          <Dropdown
            menu={{ items: collectionMenuItems.length ? collectionMenuItems : [{ key: "empty", label: "请先新建专题", disabled: true }] }}
          >
            <Button icon={<FolderAddOutlined />}>加入专题</Button>
          </Dropdown>
        )}
      >
        <Spin spinning={detailLoading}>
          {selectedItem && (
            <>
              <div className="knowledge-detail-hero">
                <div><Space wrap><Tag color={itemTypeMeta[selectedItem.item_type].color}>{itemTypeMeta[selectedItem.item_type].label}</Tag>{reviewTag(selectedItem.review_status)}{selectedItem.validity_status === "at_risk" && <Tag color="volcano">来源风险</Tag>}</Space><h3>{selectedItem.title}</h3><p>{selectedItem.summary}</p></div>
                <strong>{selectedItem.confidence}<small>% 可信度</small></strong>
              </div>

              {selectedItem.validity_status === "at_risk" && <Alert type="warning" showIcon message="关联来源存在风险" description="来源失效、授权变化或新鲜度下降时，知识条目保留但不得无提示进入报告。" />}

              <div className="knowledge-evidence-card">
                <div><span><AuditOutlined /> 原文证据</span><small>{selectedItem.evidence.start ?? "—"}–{selectedItem.evidence.end ?? "—"} · {selectedItem.evidence.extraction_method}</small></div>
                <blockquote>“{selectedItem.evidence.excerpt}”</blockquote>
              </div>

              <h4 className="knowledge-drawer-title">追溯链</h4>
              <div className="knowledge-trace-chain">
                <article><span><LinkOutlined /></span><div><small>来源</small><strong>{selectedItem.source.name}</strong><p>{selectedItem.source.authorization_status ? `授权 ${selectedItem.source.authorization_status}` : "来源记录已移除"} · 保留 {selectedItem.source.retention_days ?? "—"} 天</p></div>{selectedItem.source.url && <a href={selectedItem.source.url} target="_blank" rel="noreferrer">打开</a>}</article>
                <i>↓</i>
                <article><span><FileTextOutlined /></span><div><small>材料版本</small><strong>{selectedItem.document ? `${selectedItem.document.title} · v${selectedItem.document.version}` : "历史证据记录"}</strong><p>{selectedItem.document ? `采集 ${formatTime(selectedItem.document.collected_at)} · ${selectedItem.document.parser_version}` : "该演示条目由已有洞察证据迁移，后续采集将自动绑定文档哈希"}</p></div></article>
                <i>↓</i>
                <article><span><NodeIndexOutlined /></span><div><small>知识条目</small><strong>{itemTypeMeta[selectedItem.item_type].label} · {selectedItem.category}</strong><p>{selectedItem.extraction_method} · 质量 {selectedItem.quality_score}/100</p></div></article>
              </div>

              <Descriptions size="small" column={2} bordered className="knowledge-descriptions" items={[
                { key: "subject", label: "主体", children: selectedItem.subject ?? "—" },
                { key: "language", label: "语言", children: selectedItem.language?.toUpperCase() ?? "—" },
                { key: "sources", label: "来源数量", children: `${selectedItem.source_count} 个` },
                { key: "updated", label: "最后更新", children: formatTime(selectedItem.updated_at) },
              ]} />

              <div className="knowledge-detail-tags"><strong><TagsOutlined /> 标签</strong><Space wrap>{selectedItem.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space></div>

              <div className="knowledge-review-actions">
                <div><strong>人工复核</strong><p>状态变更会保留操作者、时间、前值与备注，不会改写原始快照。</p></div>
                <Space wrap>
                  <Button loading={reviewBusy} icon={<CheckCircleFilled />} onClick={() => void updateReview("verified")}>确认有效</Button>
                  <Button loading={reviewBusy} icon={<ClockCircleOutlined />} onClick={() => void updateReview("review_required")}>待复核</Button>
                  <Button danger loading={reviewBusy} icon={<WarningFilled />} onClick={() => void updateReview("conflict")}>标记冲突</Button>
                </Space>
              </div>

              <h4 className="knowledge-drawer-title">所属专题</h4>
              <div className="knowledge-detail-collections">
                {selectedItem.collections.length ? selectedItem.collections.map((collection) => (
                  <Tag key={collection.id} closable onClose={(event) => { event.preventDefault(); void removeFromCollection(selectedItem.id, collection); }} color={collection.color}>
                    {collection.name}
                  </Tag>
                )) : <span>尚未加入专题集合</span>}
              </div>

              <h4 className="knowledge-drawer-title">版本与复核记录</h4>
              <Timeline items={selectedItem.revisions.map((revision) => ({
                color: revision.action === "created" ? "green" : "blue",
                content: <div className="knowledge-revision"><div><strong>v{revision.version} · {revision.action === "created" ? "创建" : "状态更新"}</strong><span>{formatTime(revision.created_at)}</span></div><p>{revision.note || "未填写备注"}{revision.changed_by ? ` · ${revision.changed_by}` : ""}</p></div>,
              }))} />
            </>
          )}
        </Spin>
      </Drawer>

      <Modal
        title="新建专题集合"
        open={collectionModalOpen}
        okText="创建专题"
        cancelText="取消"
        confirmLoading={creatingCollection}
        onOk={() => void createCollection()}
        onCancel={() => setCollectionModalOpen(false)}
      >
        <div className="knowledge-collection-form">
          <label><span>专题名称</span><Input value={collectionName} maxLength={80} placeholder="例如：Q3 企业治理对比" onChange={(event) => setCollectionName(event.target.value)} /></label>
          <label><span>说明</span><Input.TextArea value={collectionDescription} maxLength={300} rows={3} placeholder="说明纳入范围和报告用途" onChange={(event) => setCollectionDescription(event.target.value)} /></label>
          <label><span>标识色</span><div className="knowledge-color-options">{collectionColors.map((color) => <button key={color} className={collectionColor === color ? "knowledge-color--active" : ""} style={{ background: color }} onClick={() => setCollectionColor(color)} aria-label={`选择颜色 ${color}`} />)}</div></label>
        </div>
      </Modal>
    </div>
  );
}
