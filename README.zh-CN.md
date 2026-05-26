# Markhub

[English README](README.md)

Markhub 是一个本地数据标注平台，用于构建和检查多模态、计算机视觉等场景所需的结构化数据集。平台设计目标是逐步支持多种标注模式，包括文档版面分析、矩形框、多边形分割、关键点和文字转录等。

当前版本已经完成的是文档版面分析标注流程。用户可以上传 PDF，选择提示词模板和模型接口，启动分析任务，然后在工作台中查看页面、识别框、版面块类型、JSON 结果和生成的数据集记录。

## 核心能力

- 提供面向标注项目的仪表盘和数据集视图。
- 已支持完整的 PDF 文档版面分析标注流程。
- 使用 Qwen/OpenAI 兼容视觉模型分析 PDF 页面版面。
- 本地渲染 PDF 页面，并将模型输出的 `0-1000` grounding 坐标映射回预览图像素坐标。
- 识别并展示文档标题、段落标题、正文、表格、图片标题、图片和视觉脚注等版面块。
- 支持在工作台中查看、筛选、删除、绘制和导出标注块。
- 将每次标注任务保存为本地数据集记录，方便后续复查。
- 提供提示词模板编辑能力，为当前版面分析和后续标注类型做准备。

## 产品模块

- **Dashboard**：以项目卡片形式展示真实标注任务。
- **Datasets**：汇总已完成和运行中的标注数据集。
- **Workspace**：当前支持 PDF 版面分析，包括上传、模型配置、分析任务和页面级结果检查。
- **Settings**：管理中文界面偏好和提示词模板。

## 技术栈

- **前端**：React 19、Vite、TypeScript、Tailwind CSS 4、Motion、Lucide icons。
- **前端服务**：Express 开发服务器，代理 `/api` 和 `/jobs` 到后端。
- **后端**：Python HTTP server、PyMuPDF、Pillow、OpenAI Python SDK。
- **本地存储**：数据统一保存在 `backend/datasets/`，并按 `first_annotations/`、`second_annotations/`、`swift_datasets/`、`llamafactory_datasets/` 分组。

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
| `PYTHONPYCACHEPREFIX=/private/tmp/markhub_pycache python3 -m py_compile backend/server.py backend/features/layout_analysis/server.py` | 检查后端 Python 语法，且不把缓存写入仓库。 |
| `python3 scripts/convert_markhub_to_msswift.py` | 将 `backend/datasets/first_annotations/` 中已完成的版面分析标注结果转换为 ms-swift 多模态 SFT 数据。 |

## 数据集转换与二次标注

数据集页面支持多选已完成的版面分析数据集，并在页面内转换为 LLaMA-Factory 或 ms-swift 格式。数据统一保存到：

- `backend/datasets/first_annotations/`：一次标注任务、页面图片和结果 JSON。
- `backend/datasets/second_annotations/`：二次标注草稿和提交版本。
- `backend/datasets/swift_datasets/`：ms-swift 转换结果。
- `backend/datasets/llamafactory_datasets/`：LLaMA-Factory 转换结果。

转换结果包含：

- `train.jsonl` / `val.jsonl` / `test.jsonl`：按转换配置生成。
- `dataset_info.json`：数据集格式说明。
- `convert_config.json`：来源数据集、目标格式、split、输出路径等配置。
- `convert_log.txt`：转换日志和跳过样本数量。

数据集页面也支持进入“二次标注”，可对一次标注结果进行移动、缩放、新增、删除、修改 label 和文本，并支持保存草稿、另存为二次标注版本或覆盖原一次标注。

如需命令行导出 ms-swift 数据，也可以运行：

```bash
python3 scripts/convert_markhub_to_msswift.py
```

脚本默认会输出到 `backend/datasets/swift_datasets/markhub_layout_msswift_export/`：

- `markhub_layout_msswift.jsonl`：ms-swift 标准 `messages` 数据，每页一条多模态 SFT 样本。
- `images/`：脚本复制出的页面检查图。默认使用 `model_pages`，对应输出中的 `0-1000` bbox 坐标。

常用参数：

```bash
python3 scripts/convert_markhub_to_msswift.py \
  --jobs-dir backend/datasets/first_annotations \
  --output-dir backend/datasets/swift_datasets/my_export \
  --dataset-name markhub_layout_msswift \
  --format jsonl
```

训练时直接指定导出的数据文件：

```bash
swift sft \
  --model Qwen/Qwen2.5-VL-7B-Instruct \
  --train_type lora \
  --dataset /path/to/export/markhub_layout_msswift.jsonl
```

脚本默认在 `images` 字段中写入复制后图片的绝对路径，符合 ms-swift 多模态数据集对图片路径的推荐用法。

## 架构概览

```text
Markhub/
  backend/
    server.py              # 后端统一启动入口
    features/
      layout_analysis/     # 已完成的 PDF 版面分析标注服务
    static/index.html      # 旧版独立预览页面
    datasets/              # 生成的一次/二次标注和转换数据集，已被 Git 忽略
  frontend/
    server.ts              # Express/Vite 服务和后端代理
    src/App.tsx            # 应用外壳、仪表盘路由、设置页
    src/components/        # 仪表盘、数据集页面、标注工作台
    src/types.ts           # 前端共享类型
  start.sh                 # 一键本地启动脚本
```

前端当前没有引入 React Router。顶层视图状态主要由 `frontend/src/App.tsx` 管理，已完成的版面分析标注工作流主要集中在 `frontend/src/components/Workspace.tsx`。

后端功能模块遵循 `docs/BACKEND_FEATURE_STANDARD.md` 中的规范：每一种标注能力都应放在 `backend/features/` 下自己的功能目录中。

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
| `GET` | `/jobs/...` | 访问 `backend/datasets/first_annotations/` 下生成的页面图片和任务资源。 |

## 当前状态

Markhub 的目标是成为更完整的数据标注平台。当前阶段已经完成的是 PDF 文档版面分析标注流程。Bounding Box、Polygon、Keypoints 和 Text Transcription 已作为未来标注类型入口出现在界面中，但还没有实现完整工作流。

更多交接信息和已知注意事项见 `AGENT_HANDOFF.md`。
