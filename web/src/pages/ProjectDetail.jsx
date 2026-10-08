import {
  ApartmentOutlined,
  DatabaseOutlined,
  InfoCircleOutlined,
  RobotOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Button, Card, Col, Row, Spin, Steps, Tabs, Tooltip } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import TestCaseMindmap from '../components/TestCaseMindmap';
import { getGenerations, getProject, getProjectStage, getTestcases } from '../services/api';
import { getStageAction, getStageIndex, STAGE_META } from '../utils/projectAction';

const TYPE_META = [
  { key: 'functional', label: '功能', color: 'var(--type-functional)' },
  { key: 'boundary', label: '边界', color: 'var(--type-boundary)' },
  { key: 'exception', label: '异常', color: 'var(--type-exception)' },
];
const PRIORITY_META = [
  { key: 'P0', label: 'P0', color: 'var(--priority-p0)' },
  { key: 'P1', label: 'P1', color: 'var(--priority-p1)' },
  { key: 'P2', label: 'P2', color: 'var(--priority-p2)' },
];

function hasRealDescription(desc) {
  const text = desc?.trim();
  return text && text.length > 2 && !/^\d+$/.test(text);
}

/** 越高越好的指标：>= good 绿，>= mid 橙，否则红 */
function rateColor(value, [good, mid]) {
  if (value >= good) return '#16a34a';
  if (value >= mid) return '#ea580c';
  return '#dc2626';
}

/** 越低越好的指标：<= good 绿，<= mid 橙，否则红 */
function rateColorInverse(value, [good, mid]) {
  if (value <= good) return '#16a34a';
  if (value <= mid) return '#ea580c';
  return '#dc2626';
}

function MetricItem({ icon, label, value, color }) {
  return (
    <div className="metric-item">
      <div className="metric-icon" style={{ background: `${color}18`, color }}>
        {icon}
      </div>
      <div>
        <div className="metric-value">{value}</div>
        <div className="metric-label">{label}</div>
      </div>
    </div>
  );
}

function DistRow({ label, segments, total }) {
  return (
    <div className="dist-row">
      <div className="dist-head">
        <span className="dist-label">{label}</span>
      </div>
      <div className="dist-bar">
        {total === 0 ? (
          <div className="dist-seg dist-seg-empty" style={{ width: '100%' }} />
        ) : (
          segments.map((s) => s.value > 0 && (
            <div
              key={s.label}
              className="dist-seg"
              style={{ width: `${(s.value / total) * 100}%`, background: s.color }}
              title={`${s.label} ${s.value}`}
            />
          ))
        )}
      </div>
      <div className="dist-legend">
        {segments.map((s) => (
          <span key={s.label} className="dist-legend-item">
            <i className="dist-dot" style={{ background: s.color }} />
            {s.label} <strong>{s.value}</strong>
          </span>
        ))}
      </div>
    </div>
  );
}

function StageWorkbench({ projectId, stage }) {
  const navigate = useNavigate();
  if (!stage) return null;

  const stageIndex = getStageIndex(stage.stage);
  const stageMeta = STAGE_META[stageIndex];
  const action = getStageAction(projectId, stage);
  const hint = [
    action?.hint,
    stage.document_title ? `需求文档《${stage.document_title}》` : '',
  ].filter(Boolean).join(' · ');

  return (
    <section className="workbench-hero">
      <div className="workbench-steps">
        <Steps
          size="small"
          current={stageIndex}
          items={STAGE_META.map((s) => ({
            // 阶段说明收进悬浮提示；步骤下方只展示真实进度信息（待评审条数、文档名等）
            title: s.key === stage.stage
              ? <Tooltip title={stageMeta.desc}><span>{s.label}</span></Tooltip>
              : s.label,
            ...(s.key === stage.stage && hint
              ? { description: <span className="workbench-step-hint">{hint}</span> }
              : {}),
          }))}
          responsive
        />
      </div>
      <div className="workbench-actions">
        {action && (
          <Button
            type="primary"
            icon={action.kind === 'generate' ? <ThunderboltOutlined /> : undefined}
            onClick={() => navigate(action.path)}
          >
            {action.label}
          </Button>
        )}
        {stage.stage === 'done' && (
          <Button onClick={() => navigate(`/projects/${projectId}/generate`)}>
            新一轮生成
          </Button>
        )}
      </div>
    </section>
  );
}

export default function ProjectDetail() {
  const { projectId } = useParams();
  const [searchParams] = useSearchParams();
  const [project, setProject] = useState(null);
  const [stage, setStage] = useState(null);
  const [cases, setCases] = useState([]);
  const [generations, setGenerations] = useState([]);
  const [stats, setStats] = useState({ testcases: 0, generations: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [p, st, tc, gen] = await Promise.all([
          getProject(projectId),
          getProjectStage(projectId).catch(() => null),
          getTestcases(projectId),
          getGenerations(projectId),
        ]);
        setProject(p);
        setStage(st);
        setCases(tc);
        setGenerations(gen);
        setStats({ testcases: tc.length, generations: gen.length });
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId]);

  // 汇总所有已评审任务的信号：采纳率 / 编辑率 / 驳回率
  const reviewSummary = useMemo(() => {
    const reviewed = generations.filter((g) => g.review_stats?.reviewed);
    if (!reviewed.length) return null;
    const sum = reviewed.reduce(
      (acc, g) => {
        acc.total += g.review_stats.total;
        acc.adopted += g.review_stats.adopted;
        acc.rejected += g.review_stats.rejected;
        acc.editedAdopted += g.review_stats.edited_adopted;
        return acc;
      },
      { total: 0, adopted: 0, rejected: 0, editedAdopted: 0 },
    );
    const rate = (part, whole) => (whole ? Math.round((part / whole) * 1000) / 10 : 0);
    return {
      taskCount: reviewed.length,
      total: sum.total,
      adopted: sum.adopted,
      adoptionRate: rate(sum.adopted, sum.total),
      editRate: rate(sum.editedAdopted, sum.adopted),
      rejectionRate: rate(sum.rejected, sum.total),
    };
  }, [generations]);

  const composition = useMemo(() => {
    const byType = { functional: 0, boundary: 0, exception: 0 };
    const byPriority = { P0: 0, P1: 0, P2: 0 };
    let ai = 0;
    cases.forEach((c) => {
      if (byType[c.case_type] !== undefined) byType[c.case_type] += 1;
      if (byPriority[c.priority] !== undefined) byPriority[c.priority] += 1;
      if (c.source === 'ai_generated') ai += 1;
    });
    const total = cases.length;
    return {
      typeSegments: TYPE_META.map((m) => ({ label: m.label, color: m.color, value: byType[m.key] })),
      prioritySegments: PRIORITY_META.map((m) => ({ label: m.label, color: m.color, value: byPriority[m.key] })),
      aiRatio: total ? Math.round((ai / total) * 100) : 0,
      total,
    };
  }, [cases]);

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>;
  }

  if (!project) return null;

  return (
    <div>
      <PageHeader
        title={project.name}
        description={hasRealDescription(project.description) ? project.description : undefined}
      />

      <StageWorkbench projectId={projectId} stage={stage} />

      <Tabs
        defaultActiveKey={searchParams.get('tab') || 'overview'}
        items={[
          {
            key: 'overview',
            label: '数据概览',
            children: (
              <>
                <Card className="surface-card" styles={{ body: { padding: '18px 24px' } }} style={{ marginBottom: 24 }}>
                  <div className="metric-strip">
                    <MetricItem
                      icon={<DatabaseOutlined />}
                      label="用例总数"
                      value={stats.testcases}
                      color="#5798F5"
                    />
                    <div className="metric-divider" />
                    <MetricItem
                      icon={<ThunderboltOutlined />}
                      label="生成任务"
                      value={stats.generations}
                      color="#06b6d4"
                    />
                    <div className="metric-divider" />
                    <MetricItem
                      icon={<RobotOutlined />}
                      label="AI 生成占比"
                      value={`${composition.aiRatio}%`}
                      color="#22A3A6"
                    />
                  </div>
                </Card>

                <Row gutter={[16, 16]}>
                  {reviewSummary && (
                    <Col xs={24} lg={12}>
                      <Card
                        className="surface-card"
                        style={{ height: '100%' }}
                        title={(
                          <span className="page-title-row">
                            AI 生成质量
                            <Tooltip title={`基于 ${reviewSummary.taskCount} 次已评审的生成任务汇总，反映 AI 生成用例的实际可用程度`}>
                              <InfoCircleOutlined className="page-title-hint" />
                            </Tooltip>
                          </span>
                        )}
                      >
                        <Row gutter={[16, 16]}>
                          <Col xs={8}>
                            <div className="review-metric">
                              <div className="review-metric-value" style={{ color: rateColor(reviewSummary.adoptionRate, [70, 40]) }}>
                                {reviewSummary.adoptionRate}%
                              </div>
                              <div className="review-metric-label">采纳率</div>
                              <div className="review-metric-sub">{reviewSummary.adopted} / {reviewSummary.total} 条被采纳</div>
                            </div>
                          </Col>
                          <Col xs={8}>
                            <div className="review-metric">
                              <div className="review-metric-value" style={{ color: rateColorInverse(reviewSummary.editRate, [20, 50]) }}>
                                {reviewSummary.editRate}%
                              </div>
                              <div className="review-metric-label">编辑率</div>
                              <div className="review-metric-sub">采纳前需人工修改的比例</div>
                            </div>
                          </Col>
                          <Col xs={8}>
                            <div className="review-metric">
                              <div className="review-metric-value" style={{ color: rateColorInverse(reviewSummary.rejectionRate, [10, 30]) }}>
                                {reviewSummary.rejectionRate}%
                              </div>
                              <div className="review-metric-label">驳回率</div>
                              <div className="review-metric-sub">完全不可用的比例</div>
                            </div>
                          </Col>
                        </Row>
                      </Card>
                    </Col>
                  )}
                  <Col xs={24} lg={reviewSummary ? 12 : 24}>
                    <Card className="surface-card" title="用例构成" style={{ height: '100%' }}>
                      {composition.total === 0 ? (
                        <div className="dist-empty">
                          暂无用例，<Link to={`/projects/${projectId}/generate`}>去 AI 生成</Link> 并采纳后展示构成
                        </div>
                      ) : (
                        <>
                          <DistRow label="按类型" segments={composition.typeSegments} total={composition.total} />
                          <DistRow label="按优先级" segments={composition.prioritySegments} total={composition.total} />
                        </>
                      )}
                    </Card>
                  </Col>
                </Row>
              </>
            ),
          },
          {
            key: 'mindmap',
            label: <span><ApartmentOutlined /> 用例脑图</span>,
            children: <TestCaseMindmap cases={cases} projectName={project.name} />,
          },
        ]}
      />
    </div>
  );
}
