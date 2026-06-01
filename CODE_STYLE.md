# Markhub 编码规范

> 最近更新：2026-05-28
> 本规范基于当前代码库实际写法整理。新增功能或修改既有文件时请优先遵循这里的约定；如果代码库内出现不一致，请按本文档统一。
>
> 与本规范配套：[docs/BACKEND_FEATURE_STANDARD.md](docs/BACKEND_FEATURE_STANDARD.md)（后端功能模块拆分规则）、[docs/AGENT_HANDOFF.md](docs/AGENT_HANDOFF.md)（项目交接说明）。

## 1. 项目技术栈

| 层 | 技术 |
| --- | --- |
| 前端框架 | React 19 + TypeScript 5.8（[frontend/package.json](frontend/package.json)） |
| 构建 / Dev Server | Vite 6 + Express + tsx ([frontend/server.ts](frontend/server.ts)) |
| 样式 | Tailwind CSS 4（`@theme` 语法）+ Material 3 token 配色（[frontend/src/index.css](frontend/src/index.css)） |
| 动画 | `motion/react` |
| 图标 | `lucide-react` |
| 后端入口 | Python 标准库 `http.server.ThreadingHTTPServer` |
| PDF / 模型 | PyMuPDF (`fitz`) + Pillow + `openai`（[backend/requirements.txt](backend/requirements.txt)） |
| 持久化 | 文件系统 JSON（`backend/datasets/` 下） |
| 启动脚本 | [start.sh](start.sh)（含 `restart` 模式） |
| 验证 | `tsc --noEmit`（前端 lint）+ `py_compile`（后端语法）+ [scripts/test_prompt_management_api.py](scripts/test_prompt_management_api.py)（提示词 CRUD 烟雾测试） |

后端只引入 3 个三方包：`openai / PyMuPDF / Pillow`。除非业务必要，**不要再添加新的依赖**。

## 2. 目录结构与模块职责

```text
Markhub/
├── start.sh                                  # 一键启动脚本
├── README.md / README.zh-CN.md
├── docs/
│   ├── BACKEND_FEATURE_STANDARD.md           # 后端特性目录规范（强制）
│   └── AGENT_HANDOFF.md
├── backend/
│   ├── server.py                             # 薄入口，调用 features.layout_analysis.main
│   ├── requirements.txt
│   └── features/
│       └── layout_analysis/                  # 唯一已实现的标注特性
│           ├── __init__.py                   # 仅 re-export main
│           ├── server.py                     # LayoutAnalyzerHandler + main()
│           ├── service.py                    # 业务流程（PDF 分析、转换、二次标注）
│           ├── storage.py                    # 持久化与路径解析
│           ├── prompts.py                    # 内置 LAYOUT_PROMPT 与只读注册表
│           ├── prompts_store.py              # 提示词 CRUD（prompts.json 真相源）
│           ├── schemas.py                    # dataclass、标签集合、类型枚举
│           ├── paths.py                      # 路径常量
│           └── utils.py                      # 纯函数工具（env IO、字符串处理）
├── frontend/
│   ├── server.ts                             # Express + Vite 中间件，反向代理 /api 与 /jobs
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── App.tsx                           # 顶层视图状态、路由切换
│       ├── main.tsx                          # createRoot 挂载
│       ├── types.ts                          # 共享类型定义
│       ├── index.css                         # Tailwind v4 token + 全局样式
│       ├── lib/
│       │   └── jobs.ts                       # 数据映射与格式化工具
│       └── components/
│           ├── Dashboard.tsx
│           ├── DatasetsPage.tsx
│           ├── Workspace.tsx
│           ├── SecondAnnotationWorkspace.tsx
│           ├── PromptManagementPage.tsx
│           ├── SettingsPage.tsx
│           ├── PromptTemplateManager.tsx
│           └── GlowBackground.tsx
└── scripts/
    ├── convert_markhub_to_msswift.py
    └── test_prompt_management_api.py
```

**模块职责（后端）**：

- `paths.py`：只放路径常量。不能写 IO 或副作用。
- `schemas.py`：`@dataclass` + 标签 / 状态枚举 + 内置常量。**禁止**导入兄弟模块（最底层）。
- `utils.py`：纯函数工具（env 解析、字符串清洗、路径白名单）。**只**依赖 `paths` 与 `schemas`。
- `prompts.py`：`LAYOUT_PROMPT` 长字符串 + 只读 `PROMPT_TEMPLATES` 注册表。**禁止**写入。
- `storage.py`：所有 disk-touching 操作（job/dataset/convert_task 持久化）。不能 import `service.py / server.py / prompts_store.py`。
- `prompts_store.py`：`prompts.json` 的 CRUD 与 bootstrap 迁移。
- `service.py`：业务流程。可以 import `storage / prompts / prompts_store / schemas / utils`，**不能** import `server`。
- `server.py`：`LayoutAnalyzerHandler` 路由 + `main()` + import 自 service/storage/prompts_store 的 re-export。

**依赖方向是单向的**：`paths → schemas → utils → (storage, prompts) → prompts_store → service → server`。新增模块前先确认不会引入反向 import。

## 3. 文件命名约定

| 类别 | 约定 | 示例 |
| --- | --- | --- |
| Python 模块 / 目录 | `lower_snake_case` | `layout_analysis/`, `prompts_store.py` |
| Python 测试脚本 | `test_<feature>.py` 放在 `scripts/` | `test_prompt_management_api.py` |
| TypeScript 工具 | `camelCase.ts` | `lib/jobs.ts` |
| React 组件 | `PascalCase.tsx`，文件名 = 默认导出组件名 | `Workspace.tsx`, `DatasetsPage.tsx` |
| 样式 | `kebab-case.css` | `index.css` |
| 文档 | `UPPER_SNAKE_CASE.md` 或 `README.md` | `BACKEND_FEATURE_STANDARD.md`, `CODE_STYLE.md` |
| 数据文件 | 路径写成 `datasets/...`，永不写入绝对路径 | `backend/datasets/first_annotations/<job_id>/result.json` |

新增后端特性目录时，目录名必须与前端 `AnnotationFeature` 类型字面量保持一致（如 `bounding_box / polygon / keypoints / text_transcription`），见 [docs/BACKEND_FEATURE_STANDARD.md](docs/BACKEND_FEATURE_STANDARD.md)。

## 4. 命名约定

### 4.1 Python

```python
# 常量：UPPER_SNAKE_CASE，集合/字典字面量直接定义在模块顶层
BLOCK_TYPES = {"doc_title", "paragraph_title", ...}
DEFAULT_PROMPT_TEMPLATE_ID = "default_template_1"
RESIZE_PRESETS = {"speed": (1216, 1728), "default": (1536, 2176), ...}

# 函数：snake_case，动词开头
def normalize_prompt_template_id(value: Any) -> str: ...
def write_job_result(job_id: str, payload: Dict[str, Any]) -> None: ...

# 类：PascalCase
class LayoutAnalyzerHandler(BaseHTTPRequestHandler): ...

# Dataclass：PascalCase，字段 snake_case
@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str
    timeout: int

# 内部函数：单下划线前缀，仅给同模块用
def _migrate_legacy_template_file(...) -> None: ...
def _upgrade_builtin_default_prompt() -> None: ...
```

**原则**：
- 布尔参数显式命名，避免裸 True/False（`include_prompt: bool = True`、`is_new: bool = False`）。
- 全局可变状态尽量少，确实需要时用大写命名并放在模块顶层（`CONVERT_TASKS: Dict[str, Dict[str, Any]] = {}`）。
- 不要使用单字母变量名，除非是循环变量（`i / j / x / y`）或公认的数学符号（`x1, y1, x2, y2` 描述 bbox）。

### 4.2 TypeScript / React

```ts
// 常量：UPPER_SNAKE_CASE
const BLOCK_TYPES: BackendBlockType[] = ['doc_title', ...];
const DEFAULT_VISIBLE_TYPES: Record<BackendBlockType, boolean> = { ... };

// 函数 / 变量：camelCase
function mapJobToProject(job: BackendJobSummary): Project { ... }
const handleStartAnalysis = async () => { ... };

// React 组件：PascalCase，文件默认导出
export default function Workspace({ project, onGoBack }: WorkspaceProps) { ... }

// Props 接口：组件名 + Props
interface WorkspaceProps { project: Project; onGoBack: () => void; }

// Type 联合：用 type；对象形状：用 interface
export type AnnotationFeature = 'bounding_box' | 'polygon' | 'layout' | 'keypoints' | 'text_transcription';
export interface Project { id: string; ... }

// 事件回调：props 用 on 前缀，组件内部用 handle 前缀
<Component onSelectProject={handleSelectProject} />
```

**避免**：
- ❌ `function MyComponent(props: any)` — 不要用 `any` 替代 props 类型。
- ❌ `interface IProps` — 不要用匈牙利前缀。
- ❌ `const x = ...` — 不要用单字母名。

## 5. 代码组织与分层原则

### 5.1 后端分层

```text
HTTP Handler (server.py)
        ↓
Business Service (service.py / prompts_store.py)
        ↓
Persistence (storage.py)
        ↓
Pure helpers (utils.py) + Schemas (schemas.py) + Paths (paths.py)
```

- **Handler 不直接读写文件**：路由从 storage / service 拿数据，handler 只做参数校验、JSON 序列化、HTTP 状态码。
- **Service 不直接调 HTTP**：业务函数返回纯 `Dict / List`，由 handler 包装。
- **Storage 不调业务**：[storage.py](backend/features/layout_analysis/storage.py) 里有一处例外（`normalize_job_payload` 用了延迟 `from .prompts import PROMPT_TEMPLATES`），这是为了避免循环 import。**新增类似交叉引用时优先把共享内容下沉到 schemas.py 或 utils.py**，不要继续依赖延迟 import。

### 5.2 前端分层

- **App.tsx**：只管 `activeScreen / activeHeaderTab / selectedProject` 三个游标和顶层数据获取。
- **components/**：每个组件文件 ≤ 1000 行；超过就拆。当前 [Workspace.tsx](frontend/src/components/Workspace.tsx) ~940 行处于上限。
- **lib/jobs.ts**：跨组件复用的数据映射 / 格式化函数集中在这里。新增工具优先放进 `lib/`，不要分散在 App.tsx 末尾。
- **types.ts**：所有后端契约类型（`BackendBlock / BackendJob / PromptRecord` 等）的唯一来源。组件内不要重复定义 backend 形状。

### 5.3 何时拆分文件

| 信号 | 应该拆 |
| --- | --- |
| 单文件 > 800 行 | 是（[backend/features/layout_analysis/server.py](backend/features/layout_analysis/server.py) 目标 < 800） |
| 一个文件包含 2 个以上 React 组件 + 工具函数 | 是 |
| handler 路由超过 30 个分支 | 抽路由表 |
| 同一类型在 2 处定义 | 是，移到 [types.ts](frontend/src/types.ts) |

## 6. 前端组件开发规范

### 6.1 文件结构

```tsx
/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

// 1. React + 第三方
import React, { useEffect, useState } from 'react';
import { ArrowLeft, Save } from 'lucide-react';
import { motion } from 'motion/react';

// 2. 共享类型
import { Project, BackendJob } from '../types';

// 3. 本地工具
import { mapJobToProject } from '../lib/jobs';

// 4. 子组件
import PromptTemplateManager from './PromptTemplateManager';

// 5. 模块顶层常量
const BLOCK_TYPES: BackendBlockType[] = [...];
const DEFAULT_VISIBLE_TYPES: Record<BackendBlockType, boolean> = {...};

// 6. Props 接口
interface WorkspaceProps {
  project: Project;
  onGoBack: () => void;
}

// 7. 组件
export default function Workspace({ project, onGoBack }: WorkspaceProps) {
  // 7a. 状态钩子
  const [scale, setScale] = useState(0.9);
  // 7b. useEffect
  useEffect(() => { ... }, [project]);
  // 7c. 衍生值（useMemo）
  const currentPageSegments = useMemo(() => ..., [segments]);
  // 7d. 事件处理
  const handleSave = async () => { ... };
  // 7e. 渲染
  return <div>...</div>;
}

// 8. 同文件辅助组件 / 函数（如有）
function ToolbarButton(...) { ... }
```

### 6.2 状态命名

用判别联合（`'idle' | 'loading' | 'error' | 'success'`）代替多个独立 boolean：

```tsx
// ✅ 推荐
const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

// ❌ 反例
const [isSaving, setIsSaving] = useState(false);
const [isSaved, setIsSaved] = useState(false);
const [hasError, setHasError] = useState(false);
```

### 6.3 异步处理标准模板

```tsx
const handleSave = async () => {
  if (!selectedTemplate || saveState === 'saving') return;  // 早期返回
  setSaveState('saving');
  setErrorMessage('');
  try {
    await onSavePromptTemplate({...});
    setSaveState('saved');
  } catch (error) {
    setSaveState('error');
    setErrorMessage(error instanceof Error ? error.message : String(error));
  }
};
```

### 6.4 Props 设计

- 事件回调用 `on` 前缀：`onGoBack / onSelectProject / onRefreshDatasets`。
- 可选 prop 加 `?` 显式标记：`backendJobId?: string`。
- 不要把 setter 直接作为 prop 传下去；总是包装成业务语义函数。

```tsx
// ✅ 推荐
<Dashboard onSelectProject={handleSelectProject} />

// ❌ 反例
<Dashboard setSelectedProject={setSelectedProject} setActiveScreen={setActiveScreen} />
```

### 6.5 useEffect 依赖

- 依赖数组**必须**列全；使用 lint (`tsc --noEmit`) 验证。
- 轮询用 `setInterval` 时务必返回清理函数：

```tsx
useEffect(() => {
  if (!analysisJob?.job_id || analysisJob.status === 'complete') return;
  const timer = window.setInterval(async () => { ... }, 1200);
  return () => window.clearInterval(timer);
}, [analysisJob?.job_id, analysisJob?.status]);
```

## 7. 后端 API 开发规范

### 7.1 URL 风格

- 兼容旧前端的接口保持原样：`/api/analyze /api/jobs /api/jobs/{id}/result /api/prompt-templates`。
- 新增接口加 feature 前缀：`/api/<feature_name>/...`（如未来 `/api/bounding-box/jobs`）。
- 资源路径名词复数：`/api/datasets /api/prompts`。子动作用动词：`/api/prompts/{id}/copy`。

### 7.2 Handler 写法

```python
def do_GET(self) -> None:
    parsed = urlparse(self.path)
    path = unquote(parsed.path)

    if path == "/api/config":
        self.write_json({"config": env_config(), "prompt_templates": prompt_template_options()})
        return

    annotation_match = re.fullmatch(r"/api/datasets/([A-Za-z0-9_-]+)/annotations", path)
    if annotation_match:
        try:
            self.write_json(read_annotation_payload(annotation_match.group(1)))
        except FileNotFoundError:
            self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
        return
```

规则：
- 路径用 `re.fullmatch` 而非 `startswith`，避免误匹配。
- 每个分支单独 `try/except`，匹配后立即 `return`。
- `FileNotFoundError → 404`，`ValueError / 其他 → 400`，避免把"找不到"和"参数非法"混成同一种响应。
- HTTP 状态码用 `http.HTTPStatus` 枚举而非裸数字。

### 7.3 JSON 序列化

```python
def write_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Cache-Control", "no-store")
    self.send_header("Content-Length", str(len(data)))
    self.end_headers()
    self.wfile.write(data)
```

- 始终 `ensure_ascii=False`（中文字符直接输出）。
- API 响应统一 `Cache-Control: no-store`，避免缓存导致状态不一致。

### 7.4 文件落盘（原子写）

```python
# storage.py::write_json_file —— 标准模式
def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp_path.write_text(sanitize_saved_text(json.dumps(payload, ensure_ascii=False, indent=2)), encoding="utf-8")
    tmp_path.replace(path)
```

- 所有写盘都走 `write_json_file`（原子 rename + 路径清洗）。
- **永远不要**把绝对路径写入 JSON / JSONL；用 `portable_path_ref` / `sanitize_saved_text` 转成 `datasets/...` 相对路径。

### 7.5 后台任务

异步处理统一用 `threading.Thread(target=..., daemon=True).start()`，并把任务状态落盘以便重启恢复（见 [storage.py:write_convert_task](backend/features/layout_analysis/storage.py)）。

```python
# ✅ 任务可恢复
worker = threading.Thread(target=process_job_pages, args=(...), daemon=True)
worker.start()
# read_convert_task 在重启时把残留 converting 自动置 failed

# ❌ 仅内存字典，重启丢失
TASKS[task_id] = {...}
```

### 7.6 输入校验

```python
# 数值用 clamp_int 收敛区间
dpi = clamp_int(fields.get("dpi"), default=180, minimum=72, maximum=300)

# 字符串用 clean_text 处理 None / 空白
model = clean_text(fields.get("model"), env_config()["model"])

# 文件大小阈值
if len(file_bytes) > max_pdf_bytes():
    raise ValueError(f"PDF 文件过大：{len(file_bytes)} bytes，当前上限 ...")
```

- 错误信息要"可操作"：告诉用户改什么环境变量、传什么参数。

## 8. 数据模型与类型定义

### 8.1 后端 dataclass

放在 [schemas.py](backend/features/layout_analysis/schemas.py)：

```python
@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str
    timeout: int

@dataclass(frozen=True)
class PromptTemplate:
    template_id: str
    name: str
    prompt: str
    category: str
```

- 不可变值用 `frozen=True`。
- 字段名 `snake_case`，与 JSON 序列化字段一致。

### 8.2 前端类型

**全部** backend 契约写在 [types.ts](frontend/src/types.ts)，组件不重复定义：

```ts
export interface BackendJob {
  job_id: string;
  filename: string;
  status: string;
  page_count: number;
  pages: BackendPage[];
  result?: { blocks?: BackendBlock[]; [key: string]: unknown };
  warnings?: string[];
  errors?: string[];
}
```

注意：因为后端是 `snake_case`，前端契约**保留 snake_case**（不要在 mapping 时改名，除非有显式 UI 字段转换需要——见 `mapJobToProject`）。

### 8.3 命名一致性

| 概念 | 后端字段 | 前端字段 |
| --- | --- | --- |
| 任务 ID | `job_id` | `job_id`（契约层） / `id`（UI 层 Project） |
| 文件名 | `filename` | `filename` / `name`（UI 层） |
| 分类 | `category` | `category: AnnotationFeature` |
| 标签 | `block_type` | `block_type: BackendBlockType` |

跨层的转换都收敛到 [lib/jobs.ts](frontend/src/lib/jobs.ts) 的 `mapJobToProject`。

## 9. 错误处理与日志

### 9.1 后端错误响应

```python
try:
    result = start_analysis_job(...)
    self.write_json(result)
except Exception as exc:
    traceback.print_exc()  # 控制台打印完整栈
    self.write_json(
        {"error": f"{type(exc).__name__}: {exc}"},
        status=HTTPStatus.BAD_REQUEST,
    )
```

- 错误体统一形状：`{"error": "<ExceptionType>: <message>"}`。
- 控制台用 `traceback.print_exc()`，便于本地排查。
- **不要**返回 200 但 body 里写 `"success": false`——HTTP 状态码必须反映真实结果。

### 9.2 前端错误展示

```ts
async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.error) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload as T;
}
```

- 调用层用 `error instanceof Error ? error.message : String(error)` 显示。
- UI 用专门的 `errorMessage / saveState='error'` 状态而非 `alert()`。
- 用户可恢复的错误（"PDF 太大"）原样展示后端文案；不要二次翻译。

### 9.3 日志

- 后端用 `print(..., file=sys.stderr)` 输出 startup 信息（如 `Layout Analyzer running at ...`、`LLM_BASE_URL=...`）。
- handler 内部用 `traceback.print_exc()`，不要自己做 `logging` 配置除非真有需要。
- **绝对不要**把 API key、`backend/.env` 内容打印到日志。

## 10. 注释与文档

### 10.1 Python 模块 docstring

每个模块顶部写明用途、依赖、约束：

```python
"""Prompt CRUD store backed by ``backend/datasets/prompt_templates/prompts.json``.

This is the **single source of truth** for prompt templates. The legacy
``backend/prompt_templates.json`` is read once during ``bootstrap_prompt_store``
to migrate older deployments, but is never written from runtime code paths.

Naming: ``prompts.py`` already owns ``LAYOUT_PROMPT`` and the read-only
``PROMPT_TEMPLATES`` constant registry. ``prompts_store.py`` owns the dynamic
JSON store, mirroring how ``storage.py`` sits beside ``schemas.py``.
"""
```

包含：(a) 模块负责什么，(b) 它依赖谁、被谁依赖，(c) 重要约束（如 "never written from runtime code paths"）。

### 10.2 函数注释

- **不要**写"WHAT"型注释（变量名已经说明的）。
- 只写"WHY"型注释：为什么用这个值、为什么不用看起来更优的方案。

```python
# ✅ 推荐：解释为什么
# Older dataset_state files may predate explicit annotation stages.
# A completed layout-analysis result is the first annotation version.
if str(payload.get("status") or "").lower() in {"complete", "completed", "done"} and ...:
    state["annotation_status"] = "first_annotated"

# ✅ 推荐：风险标注
# 覆盖保存会写回原始 Completed 标注结果，这是高风险操作，前端已做二次确认。
write_job_result(job_id, payload)

# ❌ 反例：WHAT 型废话
# 把 status 设置为 'first_annotated'
state["annotation_status"] = "first_annotated"
```

### 10.3 React 组件注释

- 复杂业务流程在组件顶部 docstring（JSDoc）或 README 里写。
- 内联注释只在算法 / hack / 兼容性处加。
- 不要在 JSX 中写整段中文说明文字解释结构。

### 10.4 提示词

`LAYOUT_PROMPT` 中所有规则都是模型行为的硬约束，修改时**必须**同时更新 [schemas.py](backend/features/layout_analysis/schemas.py) 里 `BUILTIN_LAYOUT_PROMPT_REVISION` 的版本号，并在 commit message 中说明原因（见近期 `layout_prompt_v20260528_toc_strict_watermark`）。

## 11. 样式与 UI 实现

### 11.1 双套设计语言（**当前现状**，不要再引入第三套）

- **暗色工业风**：Dashboard / Workspace / Settings / PromptManagement —— `bg-[#0c0c0c]`、`text-white/60`、`font-serif italic` 标题、方角无圆。
- **亮色 Tokenized**：DatasetsPage —— `bg-surface-container-low`、`text-primary`、`rounded-[1.5rem]`、Material 3 token。

新增页面如果属于"数据/列表浏览"加入亮色 token 体系；如果属于"工作台/编辑器"沿用暗色风。

### 11.2 Tailwind v4 token 定义

[frontend/src/index.css](frontend/src/index.css) 顶部 `@theme { ... }` 块定义所有 token。新增颜色必须先在这里定义，不要在组件里硬编码。

```css
@theme {
  --color-primary: #000000;
  --color-surface-container-low: #f3f3f5;
  /* ... */
}
```

### 11.3 字体栈

```
Noto Sans SC, PingFang SC, Microsoft YaHei, Inter, system-ui, sans-serif
```

中文界面默认 Noto Sans SC；标题大字号用 `font-serif italic`（Playfair Display）；等宽用 JetBrains Mono。

### 11.4 图标 / 动画

- 图标统一用 `lucide-react`，不混用其他图标库。
- 动画统一用 `motion/react` 的 `motion.div` + `AnimatePresence`。

### 11.5 真按钮 vs div

可点击元素必须用 `<button>` 而非裸 `<div onClick>`：

```tsx
// ✅ 推荐
<button type="button" onClick={handleClick} className="...">
  保存
</button>

// ❌ 反例
<div onClick={handleClick} className="cursor-pointer ...">保存</div>
```

旧代码遗留的 `<div onClick>` 已经在逐步替换；新增控件不要再走这条路。

### 11.6 二次确认

危险操作（覆盖保存、批量删除）必须用 `window.confirm`：

```ts
if (!window.confirm('该操作将覆盖原始 Completed 标注结果，是否继续？')) return;
```

## 12. 测试规范

### 12.1 后端

- 主要回归脚本：[scripts/test_prompt_management_api.py](scripts/test_prompt_management_api.py)。
- 写新测试时同样的模式：
  1. `tempfile.TemporaryDirectory()` 隔离状态；
  2. patch `PROMPTS_STORE_FILE` 等模块级常量到临时路径（同时 patch `server` 和 `prompts_store` 命名空间！）；
  3. 自定义 `assert_true(cond, message)`；
  4. 最后打印一行 `xxx_checks_ok`。

```python
with tempfile.TemporaryDirectory() as tmp:
    store_path = Path(tmp) / "prompts.json"
    s.PROMPTS_STORE_FILE = store_path
    ps.PROMPTS_STORE_FILE = store_path
    # ... 测试逻辑
print("prompt_management_checks_ok")
```

### 12.2 前端

- 暂无独立单元测试。最小验证：`npm run lint`（= `tsc --noEmit`）必须通过。
- UI 变化必须用 `./start.sh restart` 启动后手动跑 golden path（上传 PDF → 分析 → 二次标注 → 转换）。

### 12.3 端到端验证命令

```bash
# 后端语法
PYTHONPYCACHEPREFIX=/private/tmp/markhub_pycache python3 -m py_compile \
  backend/server.py backend/features/layout_analysis/*.py

# 后端业务
PYTHONPYCACHEPREFIX=/private/tmp/markhub_pycache /Users/lishixin/miniconda3/bin/python \
  scripts/test_prompt_management_api.py

# 前端类型
cd frontend && npm run lint

# 端到端
./start.sh restart
curl -s http://127.0.0.1:8787/api/config | head
```

## 13. 提交前 checklist

提交代码前过一遍：

- [ ] **后端**：`py_compile` 通过；`scripts/test_prompt_management_api.py` 输出 `prompt_management_checks_ok`。
- [ ] **前端**：`npm run lint` 通过，无 implicit-any / unused-import。
- [ ] 没有新增 `from .X import *`、`import *`、相对 import 跨越多层（`from ...features`）。
- [ ] 没有写入绝对路径到 JSON / JSONL / 日志。
- [ ] 没有在 `*.py` 模块导入时执行 IO（IO 应在 `main()` 里发起；唯一例外是 `load_dotenv()`）。
- [ ] 没有新增三方依赖（除非有充分理由并同步更新 [backend/requirements.txt](backend/requirements.txt) / [frontend/package.json](frontend/package.json)）。
- [ ] 危险操作（覆盖保存、批量删除、写 `.env`）都加了二次确认或 dry-run 选项。
- [ ] 新接口加了 feature 前缀；旧接口保留兼容。
- [ ] 修改 `LAYOUT_PROMPT` 时同步更新 `BUILTIN_LAYOUT_PROMPT_REVISION`。
- [ ] 没有暴露 API key / `.env` 到日志或前端响应。
- [ ] 文件大小：新增 React 组件 < 1000 行；新增后端模块 < 800 行；handler 总文件 < 800 行。
- [ ] 没有把组件 / 工具函数 / 类型定义混在 App.tsx 里——抽到 `components/` 或 `lib/`。
- [ ] 没有重复定义后端契约类型，统一从 [types.ts](frontend/src/types.ts) 导入。

## 14. 推荐示例与反模式

### 14.1 错误处理

```python
# ✅ 推荐：分层异常
try:
    self.write_json(read_dataset_state(records_match.group(1)))
except FileNotFoundError:
    self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
except ValueError as exc:
    self.write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
except Exception as exc:
    traceback.print_exc()
    self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

# ❌ 反例：全部当成 400
try:
    ...
except Exception as exc:
    self.write_json({"error": str(exc)}, status=400)
```

### 14.2 类型复用

```tsx
// ✅ 推荐：从 types.ts 导入
import { BackendJob, BackendBlock, PromptTemplateOption } from '../types';

// ❌ 反例：组件内重复定义
interface BackendJob { job_id: string; ... }  // 已在 types.ts 定义过
```

### 14.3 状态管理

```tsx
// ✅ 推荐：判别联合
const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

// ❌ 反例：多个 boolean
const [isSaving, setIsSaving] = useState(false);
const [isSaved, setIsSaved] = useState(false);
const [hasError, setHasError] = useState(false);  // 状态空间爆炸
```

### 14.4 模块依赖方向

```python
# ✅ 推荐：单向依赖
# storage.py
from .paths import JOBS_DIR
from .schemas import LLMConfig
from .utils import sanitize_saved_text

# service.py
from .storage import read_job_result, write_job_result

# ❌ 反例：反向依赖
# storage.py
from .service import process_job_pages  # 让 storage 变得不可独立测试
```

### 14.5 路径处理

```python
# ✅ 推荐：写盘前 sanitize
write_json_file(path, payload)  # 内部会自动 sanitize_saved_text

# ✅ 推荐：导出时用 portable_path_ref
config["output_path"] = portable_path_ref(output_dir)

# ❌ 反例：把绝对路径写到 JSON
data["image_path"] = str(source_image.absolute())  # 移动到其他机器就失效
```

### 14.6 import 顺序

```python
# ✅ 推荐
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI

from .paths import JOBS_DIR
from .schemas import LLMConfig

# ❌ 反例：混乱顺序
from .schemas import LLMConfig
import json
from openai import OpenAI
import os
```

### 14.7 React 事件命名

```tsx
// ✅ 推荐
<Dashboard
  onSelectProject={handleSelectProject}
  onCreateProject={handleCreateProject}
  onRefreshDatasets={loadRealDatasets}
/>

// ❌ 反例：暴露 setter / 混用前缀
<Dashboard
  setSelectedProject={setSelectedProject}      // 暴露内部状态
  createProject={handleCreate}                  // 缺少 on 前缀
  doRefresh={refresh}                           // 自创前缀
/>
```

### 14.8 提示词修改

```python
# ✅ 推荐：版本号 + commit 描述变更原因
# schemas.py
BUILTIN_LAYOUT_PROMPT_REVISION = "layout_prompt_v20260528_toc_strict_watermark"

# ❌ 反例：偷偷改 prompts.py 不动版本号
# 用户的 prompts.json 不会被 upgrade，新规则不生效
```

---

## 附录：当前代码库已知不一致点

下列模式已在代码库内出现，**新代码不要继续使用**：

1. **`backend/jobs/` 历史路径**：[storage.py:job_storage_roots](backend/features/layout_analysis/storage.py) 仍兼容读取，但新写入只能进 `backend/datasets/first_annotations/`。
2. **`backend/prompt_templates.json` 旧文件**：仅用于首次启动一次性迁移（[prompts_store._migrate_legacy_template_file](backend/features/layout_analysis/prompts_store.py)），运行时**不再写入**。
3. **App.tsx 顶部 4 位协作者 unsplash 头像**：远程 URL，离线环境会失败。新增静态资源用本地 assets。
4. **Dashboard 标题英文 / 其他页面中文**：当前混排。新增页面统一中文。
5. **handler 路由 `if-elif` 链**：长但能用。新增大量端点时考虑抽路由表。
6. **同步 `setInterval` 轮询**：[Workspace.tsx](frontend/src/components/Workspace.tsx) / [DatasetsPage.tsx](frontend/src/components/DatasetsPage.tsx) 各自实现。计划合并到 `usePolling` Hook。
7. **错误状态码混用 400/404**：handler 多数地方 `Exception → 400`。新代码请按 §9.1 分级。

## 附录：参考链接

- [docs/BACKEND_FEATURE_STANDARD.md](docs/BACKEND_FEATURE_STANDARD.md) — 后端特性目录规范
- [docs/AGENT_HANDOFF.md](docs/AGENT_HANDOFF.md) — Agent 交接说明
- [README.md](README.md) / [README.zh-CN.md](README.zh-CN.md) — 产品概览
- [review.md](review.md) — 代码审查与重构记录
