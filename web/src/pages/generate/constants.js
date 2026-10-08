// GenerateFlow 向导共享的常量与纯函数（无 React 依赖）

export const QUALITY_COLOR = { pass: 'green', warning: 'orange', fail: 'red' };
export const REVIEW_COLOR = { pending: 'default', to_confirm: 'orange', adopted: 'green', rejected: 'red', edited: 'blue' };
export const QUALITY_LABEL = { pass: '通过', warning: '警告', fail: '不合格' };
export const REVIEW_LABEL = { pending: '待评审', to_confirm: '待确认', adopted: '已采纳', rejected: '已驳回', edited: '已编辑' };
export const TYPE_LABEL = { functional: '功能', boundary: '边界', exception: '异常' };
export const STATUS_LABEL = {
  pending: '等待中', generating: '生成中', completed: '已完成', failed: '失败',
};

const STRATEGY_ICONS = { full: '📋', quick: '💨' };

const DEFAULT_STRATEGIES = [
  {
    key: 'full',
    title: '完整用例',
    description: '覆盖功能、边界与异常，并自动标记其中的冒烟用例，适合上线前回归',
    min_cases_per_feature: 5,
    max_cases_per_feature: 12,
    recommended: true,
  },
  {
    key: 'quick',
    title: '快速冒烟',
    description: '只生成核心主路径冒烟用例，每个功能点 2～4 条，省时省成本',
    min_cases_per_feature: 2,
    max_cases_per_feature: 4,
    recommended: false,
  },
];

export const STRATEGY_LABEL = {
  full: '完整用例',
  quick: '快速冒烟',
  detailed: '完整用例',
  standard: '完整用例',
  smoke: '快速冒烟',
  functional_only: '快速冒烟',
};

export const SKILL_LABEL = {
  case_writer: '综合用例',
  comprehensive: '综合用例',
  security: '安全 / 权限',
  api_test: '接口测试',
  api: '接口测试',
  requirement_parser: '需求解析',
};

export const PRIORITY_OPTIONS = [
  { label: 'P0', value: 'P0' },
  { label: 'P1', value: 'P1' },
  { label: 'P2', value: 'P2' },
];

export const CASE_TYPE_OPTIONS = [
  { label: '功能', value: 'functional' },
  { label: '边界', value: 'boundary' },
  { label: '异常', value: 'exception' },
];

export const REJECT_REASONS = ['重复场景', '步骤不可执行', '业务规则错误', '与需求无关', '其他'];

export function parseJudgeIssues(raw) {
  if (!raw) return null;
  try {
    const d = JSON.parse(raw);
    return typeof d === 'object' && d !== null ? d : null;
  } catch {
    return null;
  }
}

export function judgeScoreColor(score) {
  if (score >= 4) return 'var(--success)';
  if (score >= 3) return 'var(--warning)';
  return 'var(--error)';
}

export function mapStrategies(catalog) {
  const list = catalog?.strategies?.length ? catalog.strategies : DEFAULT_STRATEGIES;
  return list.map(s => ({
    key: s.key,
    title: s.title,
    desc: s.description,
    icon: STRATEGY_ICONS[s.key] || '⚡',
    minCasesPerFeature: s.min_cases_per_feature,
    maxCasesPerFeature: s.max_cases_per_feature,
    recommended: s.recommended,
  }));
}

export function mapSpecialists(catalog) {
  if (catalog?.specialist?.length) {
    return catalog.specialist.map(s => ({
      key: s.name,
      label: s.title,
      desc: s.description,
    }));
  }
  return [
    { key: 'security', label: '安全 / 权限', desc: '越权、注入、会话等专项用例' },
    { key: 'api_test', label: '接口测试', desc: '参数校验、响应格式、状态码、幂等等接口专项用例' },
  ];
}

export function moduleLabel(module) {
  return module?.trim() || '未分类';
}

export function groupItemsByModule(items) {
  const groups = {};
  items.forEach((item) => {
    const mod = moduleLabel(item.module);
    if (!groups[mod]) groups[mod] = [];
    groups[mod].push(item);
  });
  return groups;
}

export function calcGenerationEstimate(confirmedItems, strategyKey, specialistSkills, strategies) {
  const list = strategies?.length ? strategies : mapStrategies(null);
  const strategy = list.find(s => s.key === strategyKey) || list[1] || list[0];
  const featureCount = confirmedItems.length;
  const callsPerFeature = 1 + specialistSkills.length;
  const skillCalls = featureCount * callsPerFeature;
  const minCases = featureCount * strategy.minCasesPerFeature + featureCount * specialistSkills.length * 2;
  const maxCases = featureCount * strategy.maxCasesPerFeature + featureCount * specialistSkills.length * 5;
  return {
    featureCount,
    moduleCount: new Set(confirmedItems.map(i => moduleLabel(i.module))).size,
    skillCalls,
    minCases,
    maxCases,
  };
}

export function stepsToText(steps) {
  if (!steps) return '';
  try {
    const parsed = JSON.parse(steps);
    if (Array.isArray(parsed)) return parsed.join('\n');
  } catch { /* keep raw */ }
  return steps;
}

export function textToSteps(text) {
  const lines = text.split('\n').map(s => s.trim()).filter(Boolean);
  return JSON.stringify(lines);
}

export function parseScope(raw) {
  if (!raw) return { in_scope: [], out_scope: [], risks: [] };
  try {
    const d = JSON.parse(raw);
    return {
      in_scope: d.in_scope || [],
      out_scope: d.out_scope || [],
      risks: d.risks || [],
    };
  } catch {
    return { in_scope: [], out_scope: [], risks: [] };
  }
}

export function scopeToForm(raw) {
  const s = parseScope(raw);
  return {
    in_scope: (s.in_scope || []).join('\n'),
    out_scope: (s.out_scope || []).join('\n'),
    risks: (s.risks || []).join('\n'),
  };
}

export function formToScopeJson(form) {
  const toArr = (t) => (t || '').split('\n').map(s => s.trim()).filter(Boolean);
  return JSON.stringify({
    in_scope: toArr(form.in_scope),
    out_scope: toArr(form.out_scope),
    risks: toArr(form.risks),
  });
}
