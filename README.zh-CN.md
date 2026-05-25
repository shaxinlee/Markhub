# Markhub

[English README](README.md)

Markhub 是一个本地文档版面标注与分析工作台。它面向 PDF 文档处理流程：先在本地渲染页面，再调用 OpenAI 兼容的视觉模型进行版面识别，最后把模型输出归一化为可检查、可编辑、可导出的结构化标注数据。

当前版本聚焦在 PDF 版面分析：用户可以上传 PDF，选择提示词模板和模型接口，启动分析任务，然后在工作台中查看页面、识别框、版面块类型、JSON 结果和生成的数据集记录。

## 核心能力

- 使用 Qwen/OpenAI 兼容视觉模型分析 PDF 页面版面。
- 本地渲染 PDF 页面，并将模型输出的 `0-1000` grounding 坐标映射回预览图像素坐标。
- 识别并展示文档标题、段落标题、正文、表格、图片标题、图片和视觉脚注等版面块。
- 支持在工作台中查看、筛选、删除、绘制和导出标注块。
- 将每次分析任务保存为本地数据集记录，方便后续复查。
- 提供提示词模板编辑能力，为当前版面分析和后续标注类型做准备。

## 产品模块

- **Dashboard**：以项目卡片形式展示真实后端分析任务。
- **Datasets**：汇总 PDF 版面数据集，包括完成中、运行中和错误状态。
- **Workspace**：上传 PDF、配置模型参数、运行分析任务并检查页面级标注结果。
- **Settings**：管理中文界面偏好和提示词模板。

## 技术栈

- **前端**：React 19、Vite、TypeScript、Tailwind CSS 4、Motion、Lucide icons。
- **前端服务**：Express 开发服务器，代理 `/api` 和 `/jobs` 到后端。
- **后端**：Python HTTP server、PyMuPDF、Pillow、OpenAI Python SDK。
- **本地存储**：分析任务的页面图片和结果 JSON 存放在 `backend/jobs/`。

## 快速开始

在项目根目录运行：

```bash
./start.sh
```

打开：

```text
http://127.0.0.1:3000
```

启动脚本会同时拉起两个服务：

- 前端：`http://127.0.0.1:3000`
- 后端：`http://127.0.0.1:8787`

修改后端代码后，建议使用重启模式：

```bash
./start.sh restart
```

## 配置

后端模型与渲染参数可以通过 `backend/.env` 或工作台界面配置。

常用变量：

```bash
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT=180
LAYOUT_RENDER_DPI=180
LAYOUT_MAX_PAGES=50
QWEN_RESIZE_PRESET=default
QWEN_RESIZED_WIDTH=1536
QWEN_RESIZED_HEIGHT=2176
```

不要提交真实 `.env` 文件或 API Key。可以用 `backend/.env.example` 作为配置模板。

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `./start.sh` | 同时启动后端和前端。 |
| `./start.sh restart` | 停止已有 Markhub 监听进程并重新启动服务。 |
| `cd frontend && npm run lint` | 运行 TypeScript 检查。 |
| `cd frontend && npm run build` | 构建前端和服务端 bundle。 |
| `PYTHONPYCACHEPREFIX=/private/tmp/markhub_pycache python3 -m py_compile backend/server.py` | 检查后端 Python 语法，且不把缓存写入仓库。 |

## 架构概览

```text
Markhub/
  backend/
    server.py              # API 路由、PDF 渲染、模型调用、任务存储
    static/index.html      # 旧版独立预览页面
    jobs/                  # 运行时生成结果，已被 Git 忽略
  frontend/
    server.ts              # Express/Vite 服务和后端代理
    src/App.tsx            # 应用外壳、仪表盘路由、设置页
    src/components/        # 仪表盘、数据集页面、标注工作台
    src/types.ts           # 前端共享类型
  start.sh                 # 一键本地启动脚本
```

前端当前没有引入 React Router。顶层视图状态主要由 `frontend/src/App.tsx` 管理，标注工作流主要集中在 `frontend/src/components/Workspace.tsx`。

## API 概览

Python 后端提供一组本地 API：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/config` | 获取运行配置和提示词模板。 |
| `GET` | `/api/prompt-templates` | 获取提示词模板列表。 |
| `POST` | `/api/prompt-templates/{id}` | 更新已有提示词模板。 |
| `POST` | `/api/analyze` | 上传 PDF 并启动分析任务。 |
| `GET` | `/api/jobs` | 获取分析任务列表。 |
| `GET` | `/api/jobs/{job_id}/result` | 获取完整任务结果。 |
| `DELETE` | `/api/jobs/{job_id}` | 删除本地任务。 |
| `GET` | `/jobs/...` | 访问生成的页面图片和任务资源。 |

## 当前状态

版面分析是当前已经接通的核心标注流程。Bounding Box、Polygon、Keypoints 和 Text Transcription 已作为未来标注类型入口出现在界面中，但还没有实现完整工作流。

更多交接信息和已知注意事项见 `AGENT_HANDOFF.md`。
