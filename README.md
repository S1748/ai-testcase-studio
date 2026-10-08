# AITC

**AITC**（AI Test Case）是基于 AI 的测试用例生成与管理平台，聚焦「需求结构化 → 功能清单 → RAG 知识增强 → 用例生成 → 质量评测 → 评审入库 → 导出交付」闭环。

## 功能概览

### 已实现

| 模块 | 能力 |
|------|------|
| **项目管理** | 创建/编辑项目，首页「继续上次工作」快捷入口 |
| **需求导入** | 粘贴文本、上传 Word（`.docx`）/ Markdown（`.md`），或导入 FeatureList（`.xlsx` / `.md`） |
| **FeatureList** | AI 解析 PRD 为功能点；确认页可编辑、展开验收标准/约束；支持导出/导入 Excel 与 Markdown |
| **测试范围** | 功能点表上方「不测范围 / 风险」卡片，支持 AI 生成与手动保存 |
| **用例生成** | 一套 `case_writer` Skill，策略「完整用例 / 快速冒烟」；可选专项 Skill（安全、接口） |
| **知识库 / RAG** | 项目级知识库；Markdown 分块、Embedding 向量化、ChromaDB 检索；按功能点召回业务规则并注入生成 Prompt |
| **冒烟标签** | 完整用例中核心主路径自动标 `is_smoke`，结果页与测试用例可按「全部 / 冒烟」筛选 |
| **质检与评审** | 规则质检、重复检测、AI Judge、覆盖率统计；人工采纳 / 编辑 / 驳回 / 一键全选 |
| **覆盖矩阵** | 功能点 × 功能/边界/异常 矩阵视图（评审页切换，辅助查漏） |
| **全局测试用例** | 按项目 / 模块 / 功能点浏览；列表与脑图双视图；用例与目录可编辑；脑图全屏 + 缩放 |
| **用例导出** | 生成任务支持导出 Excel / Markdown，可仅导出冒烟用例 |
| **AI 评测** | 评测样本与回归运行；统计生成成功率、可用率、场景召回率、重复率、幻觉数、Token 与耗时；支持运行对比 |
| **设置** | 生成模型、评测模型、Embedding 模型独立配置；API Key 掩码；Mock 模式 |
| **自动化测试** | pytest + requests 接口自动化，pytest + Playwright + POM UI 自动化，支持隔离环境和离线 Mock |

### 后续演进方向

- 将人工驳回、编辑和线上缺陷自动沉淀为 badcase / 回归知识
- 增加关键词 + 向量的混合检索、Rerank 与检索质量评测
- 为评测运行保存模型、Prompt、Embedding、RAG 开关等完整配置快照
- 对接 Jira、禅道、TestRail 等外部项目与用例管理系统

## 六步工作流

产品目标流程（默认短路径，专业能力按需展开）：

```
① 需求导入 → ② FeatureList → ③ 用例生成 → ④ 评审入库 → ⑤ 导出 → ⑥ 复盘沉淀
```

| 步骤 | 产物 | 状态 |
|------|------|------|
| ① 需求导入 | RequirementDocument | ✅ |
| ② FeatureList | 功能点表 + 测试范围卡片 + 清单导入导出 | ✅ |
| ③ 用例生成 | RAG 引用 + 用例草稿 + 规则质检 + AI Judge + 覆盖矩阵 | ✅ |
| ④ 评审入库 | 采纳后的 TestCase | ✅ |
| ⑤ 导出 | 可交付的 Excel / Markdown（支持冒烟筛选） | ✅ |
| ⑥ 复盘沉淀 | 项目知识库 + RAG 检索增强 | ✅ 基础链路 |

向导页当前包含 **四个操作步骤 + 完成页**（导入需求 → 确认功能点 → 选择策略 → 评审采纳 → 完成），与上述产品闭环在逻辑上对齐。知识库和 AI 评测作为独立页面提供。

## 技术栈

- **后端**：FastAPI + SQLAlchemy + SQLite（开发）
- **前端**：React + Vite + Ant Design
- **AI**：OpenAI 兼容 Chat / Embeddings API（DeepSeek、通义、OpenAI 等），`httpx` 直连，无 LangChain 依赖
- **向量检索**：ChromaDB（项目与 Embedding 模型隔离）
- **文档与导出**：`python-docx` + `openpyxl`
- **自动化测试**：pytest + requests + Playwright + pytest-html

## 前端开发约定

- 本项目定位为桌面端后台管理系统，默认以宽度不低于 `1280px` 的桌面浏览器作为设计和验收基准。
- 后续新增或调整页面无需兼顾手机模式，不要求补充移动端布局、抽屉导航或小屏响应式断点。
- 现有移动端样式暂时保留，但不属于后续功能开发和回归验收范围。

## 快速开始

### 1. 环境

```bash
cp .env.example .env
# 编辑 .env：至少配置生成模型；评测模型与 Embedding 模型按需独立配置
# 未配置 LLM_API_KEY 或 LLM_MOCK_MODE=true 时，生成/评分/向量化均可使用 Mock 链路
```

### 2. 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. 前端

```bash
cd web
npm install
npm run dev
```

### 4. 一键重启（可选）

```bash
./restart.sh
```

Windows 首次安装可运行 `setup.bat`，之后使用 `start.bat` 启动。

### 5. 访问

| 地址 | 说明 |
|------|------|
| http://localhost:5173 | 前端 |
| http://localhost:8000 | 后端 API |
| http://localhost:8000/docs | Swagger 文档 |

前端 `/api` 代理至 `http://localhost:8000`（见 `web/vite.config.js`）。

## 生成流程

```
上传需求 / 导入清单
    → AI 拆功能点（或跳过 AI 直接导入 FeatureList）
    → 确认功能点 + 测试范围
    → 选择策略（完整 / 快速冒烟 + 可选专项 Skill + RAG）
    → 按功能点检索知识 → 生成候选用例
    → 规则质检 → 重复检测 → AI Judge → 质量报告
    → 评审页：列表 / 覆盖矩阵 → 采纳 / 编辑 / 驳回
    → 入库至全局测试用例 / 导出 Excel 或 Markdown
```

**策略说明**

- **完整用例**（`full`）：每功能点 5～12 条，覆盖功能、边界、异常；核心主路径标为冒烟
- **快速冒烟**（`quick`）：每功能点 2～4 条，仅核心主路径，省时省成本
- **专项 Skill**（可选）：`security`（安全/权限）、`api_test`（接口测试），按功能点追加生成
- **RAG**（可选）：使用「模块 + 功能点 + 描述」构造查询，从当前项目知识库召回相关内容并注入生成上下文

## 知识库与 RAG

每个项目拥有独立知识库，支持业务文档、历史用例和缺陷记录等来源。核心链路：

```
文档录入 / 上传
    → 按 Markdown 标题分块（超长内容按句切分）
    → Embedding 向量化
    → 写入 ChromaDB，同时在 SQLite 保存文本与溯源信息
    → 按功能点检索 Top-K 相关知识
    → 将知识片段注入 case_writer / specialist Skill
```

- 默认检索 Top 5，并过滤低于相似度阈值的结果
- Collection 按「项目 + Embedding 模型」隔离，避免跨项目污染和向量维度冲突
- 检索失败不会阻断生成任务，而是自动降级为无知识生成
- 生成任务保存 `knowledge_refs`，可追踪命中的文档、标题路径和相似度

## 质量保障与 AI 评测

生成结果通过四层质量保障：

1. **Prompt 约束**：限定输出结构、字段与测试范围。
2. **规则质检**：标准化步骤，过滤空用例和无意义用例，检查标题、步骤与预期结果。
3. **AI Judge**：从相关性、可执行性、可验证性等维度评分，并标记疑似幻觉。
4. **人工评审**：测试人员采纳、编辑或驳回候选用例，采纳后才进入正式测试用例。

离线评测使用「PRD 原文 + 人工标准测试点」批量执行完整生成链路，主要指标包括：

| 指标 | 口径 |
|------|------|
| 生成成功率 | 评测任务成功且产出用例的样本占比 |
| 可用率 | AI Judge 综合分 ≥ 4 的用例占比 |
| 场景召回率 | 人工标准测试点中被生成用例覆盖的比例 |
| 重复率 | 重复用例数占生成用例总数的比例 |
| 幻觉数 | AI Judge 标记为疑似虚构业务规则的用例数 |
| Token / 耗时 | 评估生成成本和执行性能 |

## AI Skill 架构

Skill 采用 **manifest + handler + prompt** 插件结构，由 `SkillRegistry` 统一发现与调度。

```
backend/app/skills/
├── registry.py / loader.py / base.py   # 注册表
├── shared/                             # LLM、解析、Mock
├── requirement_parser/                 # 需求 → 功能点
├── test_proposal/                      # 测试范围 / 风险建议
├── case_writer/                        # 综合用例（full / quick）
├── security/                           # 专项：安全 / 权限
├── api_test/                           # 专项：接口测试
└── case_judge/                         # AI Judge 评分 / 幻觉判断
```

每个 Skill 目录：

| 文件 | 作用 |
|------|------|
| `skill.yaml` | 元数据：name、category、inputs/outputs、策略等 |
| `prompt.md` 或 `prompts/*.md` | Prompt 正文 |
| `handler.py` | `async def run(inputs, context) -> dict` |

**API**: `GET /api/skills` — 返回 core / specialist / strategies，前端策略页动态渲染。

**新增 Skill**: 复制 specialist 目录 → 编辑 `skill.yaml`（`category: specialist`, `ui.selectable: true`）→ 编写 prompt + handler → 重启后端即可，无需改前端硬编码。

## 目录结构

```
ai-testcase-studio/
├── backend/
│   └── app/
│       ├── api/              # REST 接口
│       ├── models/           # SQLAlchemy 模型
│       ├── schemas/          # Pydantic 模型
│       ├── services/         # 业务逻辑（生成、质检、知识库、评测等）
│       └── skills/           # AI Skill 模块
├── web/
│   └── src/
│       ├── components/       # 通用组件（脑图、编辑弹窗、覆盖矩阵等）
│       ├── layouts/          # 布局
│       ├── pages/            # 页面
│       ├── services/         # API 客户端
│       └── utils/            # 工具函数
├── docs/                     # 开发问题与维护文档
├── democase/                 # 示例需求与清单
├── autotest/                 # 接口自动化、UI 自动化、报告与运行脚本
├── restart.sh                # 一键重启前后端
├── setup.bat / start.bat     # Windows 安装与启动脚本
└── .env.example
```

## 自动化测试

测试工程位于 `autotest/`，使用临时 SQLite / Chroma 目录与 Mock 模式运行，不污染开发数据。

```bash
cd autotest
./run_tests.sh api     # 接口自动化
./run_tests.sh ui      # UI 自动化
./run_tests.sh smoke   # 冒烟用例
./run_tests.sh all     # 全量测试，报告输出到 reports/
```

Windows 使用 `run_tests.bat`，参数与上面一致。详细说明见 [`autotest/README.md`](autotest/README.md)。

## 相关文档

- [`docs/PRD.md`](docs/PRD.md)：产品需求与功能边界
- [`docs/环境准备.md`](docs/环境准备.md)：本地环境配置
- [`docs/接口文档.md`](docs/接口文档.md)：主要 API 说明
- [`docs/评测数据/`](docs/评测数据/)：示例评测样本
- [`docs/Bug记录.md`](docs/Bug记录.md)：开发与测试发现的问题


## 项目亮点

- **FeatureList 中间层**：不是将整篇 PRD 一次性直出用例，而是先结构化、人工确认，再按功能点生成，全链路可追溯。
- **策略 + Skill 分层**：完整/冒烟控制生成深度，安全/接口专项 Skill 控制测试视角，插件可独立扩展。
- **RAG 业务增强**：按项目隔离知识库，将业务规则、历史用例和缺陷经验检索后注入生成上下文。
- **多层质量闭环**：Prompt 约束、规则质检、重复检测、AI Judge、人工评审与离线评测共同保障质量。
- **生成 / 评测 / 向量模型解耦**：三套配置职责分离，评测模型可独立设置以降低自评偏差。
- **可测试、可演示**：完整 AI 路径均支持 Mock，接口和 UI 自动化使用隔离环境离线运行。
