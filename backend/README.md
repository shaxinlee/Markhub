# PDF 版面分析预览系统

本目录是 Markhub 的 Python 后端服务。Markhub 后端按功能模块组织，当前已经完成并接入的是 `features/layout_analysis/` 中的 PDF 版面分析标注服务：

- 上传 PDF
- 后端用 PyMuPDF 将 PDF 页面渲染为 PNG
- 将页面图等比放入 Qwen3-VL 标准检查图尺寸，默认 `1536 × 2176`
- 后台逐页调用 OpenAI-compatible 视觉大模型
- 可在分析前选择提示词模板，当前内置 `默认模板 1`
- 规范化模型 JSON
- 将 Qwen3-VL `0-1000` grounding 坐标映射回原始预览图坐标
- 前端在每页完成时立即叠加 bbox 识别框
- 展示已分析文件列表，并标记每个结果由哪个模型生成；旧结果缺少模型信息时显示 `未知`

## 功能模块结构

```text
backend/
  server.py                  # 统一启动入口
  features/
    layout_analysis/         # PDF 版面分析标注服务
      __init__.py
      server.py              # API、PDF 渲染、模型调用、任务结果处理
```

后续新增标注能力时，必须在 `backend/features/` 下新增独立功能目录。具体规范见 `../docs/BACKEND_FEATURE_STANDARD.md`。

## 启动

建议使用当前机器的 conda Python：

```bash
cd backend
python server.py --port 8787
```

打开：

```text
http://127.0.0.1:8787
```

## 可选环境变量

- `LLM_BASE_URL`：页面模型配置的默认接口地址，默认 `http://localhost:5222/v1`
- `LLM_API_KEY`：页面模型配置的默认 API Key；若未设置会回退到 `OPENAI_API_KEY`
- `LLM_MODEL`：页面模型配置的默认视觉大模型名称
- `LLM_TIMEOUT`：单页模型调用超时秒数，默认 `180`
- `LAYOUT_RENDER_DPI`：PDF 渲染 DPI，默认 `180`
- `LAYOUT_MAX_PAGES`：单次最多分析页数，默认 `50`
- `QWEN_RESIZE_PRESET`：页面检查图默认档位，`speed/default/high/custom`，默认 `default`
- `QWEN_IMAGE_PROFILE`：模型图像规格；`qwen2_5` 使用 28 倍数动态分辨率和像素坐标，`qwen3`、`qwen3_5` 使用 32 倍数动态分辨率和 `0-1000` 坐标，`qwen3_6` 保持固定画布和 `0-1000` 坐标
- `QWEN_RESIZED_WIDTH`：自定义检查图宽度，默认 `1536`
- `QWEN_RESIZED_HEIGHT`：自定义检查图高度，默认 `2176`

模型配置也可以直接在页面左侧填写：

- `Base URL`
- `Model`
- `API Key`
- `超时秒数`

页面填写的值会随本次上传请求提交到后端，优先生效。API Key 只用于后端调用模型，不会写入返回 JSON。
成功提交分析任务后，页面中的模型配置、渲染参数和 Qwen 检查图尺寸会保存到本地 `.env` 文件；`.env` 已被 Git 忽略，适合保存 API Key 等本机配置。

Qwen 图像缩放设置也在页面左侧：

- `速度优先`：`1216 × 1728`
- `推荐默认`：`1536 × 2176`
- `高精度`：`2048 × 2912`
- `自定义`：宽高会自动对齐到 32 的倍数

后端会将 PDF 页面等比缩放后居中放入标准白底检查图，不拉伸页面比例。调用 Qwen3-VL 时会在 image 同级设置 `resized_width`、`resized_height`、`min_pixels` 和 `max_pixels`，且 `min_pixels = max_pixels = width × height`。模型提示词要求 bbox 输出 `0-1000` 相对坐标；后端先映射到标准检查图，再扣除白边并映射回 PDF 预览页面的原始像素坐标。

Qwen3-VL 原生使用 `0-1000` 归一化 bbox；Qwen2.5-VL 原生输出缩放后图像的绝对像素坐标。页面中的模型版本选择会同时控制图像预处理、提示词坐标要求和结果解析。无论模型原始输出是哪种坐标，保存结果时都会生成统一的 `bbox_1000` 供导出与训练使用。

提示词模板也在页面左侧选择。当前内置模板名为 `默认模板 1`，内容为原有版面分析提示词；每次分析结果会记录本次使用的模板名称。

## 返回结构

接口 `POST /api/analyze` 会立即创建后台任务并返回：

```json
{
  "job_id": "...",
  "filename": "...pdf",
  "status": "running",
  "page_count": 1,
  "completed_pages": 0,
  "pages": [
    {
      "page_id": 0,
      "image_url": "/jobs/.../pages/page_000.png",
      "width": 1488,
      "height": 2105,
      "status": "pending",
      "blocks": []
    }
  ],
  "result": {
    "image_path": "",
    "blocks": []
  }
}
```

其中 `result.blocks[*].bbox_1000` 保留 Qwen 返回的 `0-1000` 坐标，`result.blocks[*].model_bbox` 是标准检查图像素坐标，`result.blocks[*].bbox` 是映射后的页面 PNG 原始像素坐标，前端按页面显示尺寸自动缩放叠加。

每页完成后还会在任务目录下同步写入两个 JSONL 文件：

- `Q&A.jsonl`：一行一个页面，包含模型图相对路径、system 提示词、user 提示词和模型完整回复。
- `layout.jsonl`：一行一个页面，包含原 PDF 页面图相对路径、页面尺寸、模型图信息和版面 blocks；前端展示框与 label 时使用同一套 layout 结构。

二次标注提交后，修正后的 `layout.jsonl` 会保存到 `backend/datasets/second_annotations/{dataset_id}/annotation_v2_*/layout.jsonl`，同时回写原任务目录下 `Q&A.jsonl` 的 assistant 内容。训练数据转换（Swift / LLaMAFactory）从 `Q&A.jsonl` 构建样本。

前端会轮询：

```text
GET /api/jobs/{job_id}/result
```

每页完成后，`pages[n].status` 会变成 `done` 或 `error`，对应页面会立刻更新。

历史列表接口：

```text
GET /api/jobs
```

返回所有已分析文件的摘要，包括 `filename`、`model`、`status`、页数和版面块数量。

删除历史处理结果：

```text
DELETE /api/jobs/{job_id}
```

页面左侧“已分析文件”中每条记录都有删除按钮，删除后会移除该任务目录及其中的页面图、标准检查图和结果 JSON。
