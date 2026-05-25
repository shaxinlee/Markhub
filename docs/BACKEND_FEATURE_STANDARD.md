# Markhub 后端功能模块开发规范

Markhub 的目标是成为完整的数据标注平台。后端新增能力时，必须按“一个标注功能一个目录”的方式组织，避免把所有业务继续堆在统一入口文件里。

## 目录原则

后端根目录只放应用入口、共享配置、运行时资源和跨功能公共代码。具体标注能力统一放在 `backend/features/` 下。

```text
backend/
  server.py                    # 后端统一启动入口，只做应用装配
  features/
    layout_analysis/           # PDF 文档版面分析标注功能
      __init__.py
      server.py                # 当前版面分析 API、任务处理、模型调用
    <feature_name>/            # 后续新增标注功能
      __init__.py
      ...
  jobs/                        # 运行时任务结果，忽略提交
  static/                      # 后端静态资源
  .env                         # 本地配置和密钥，禁止提交
```

当前已经完成并迁入功能目录的是 `layout_analysis`。根目录的 `backend/server.py` 保持为薄入口，负责调用已启用的功能模块。

## 新功能命名

功能目录名使用小写 snake_case，并与前端标注类型保持一致。

| 标注能力 | 推荐目录 |
| --- | --- |
| 版面分析 | `layout_analysis` |
| 矩形框标注 | `bounding_box` |
| 多边形分割 | `polygon_segment` |
| 关键点标注 | `keypoints` |
| 文本转录 | `text_transcription` |

## 功能目录职责

每个功能目录必须自包含该功能的后端业务逻辑。推荐结构如下：

```text
backend/features/<feature_name>/
  __init__.py                  # 对外暴露该功能的入口
  server.py                    # HTTP 路由或 handler 装配
  service.py                   # 核心业务流程
  schemas.py                   # 请求、响应、任务结构定义
  storage.py                   # 任务文件、资源路径和持久化
  prompts.py                   # 模型提示词和模板默认值
  README.md                    # 可选：该功能的局部说明
```

如果功能还很小，可以先少建文件，但不能把业务写回 `backend/server.py`。当单个文件明显变大时，应优先拆分到上面的职责文件中。

## API 约定

新增功能优先使用功能名前缀，避免不同标注能力互相污染。

```text
/api/<feature_name>/...
```

例如后续矩形框标注可以使用：

```text
POST /api/bounding-box/jobs
GET  /api/bounding-box/jobs/{job_id}
```

当前版面分析为了兼容已有前端，仍保留历史接口：

```text
POST /api/analyze
GET  /api/jobs
GET  /api/jobs/{job_id}/result
```

如果未来迁移这些接口，应先增加新接口并保持旧接口兼容，再更新前端调用。

## 配置和密钥

- 真实密钥只能放在 `backend/.env`，不能写入代码、README 示例或提交记录。
- 新功能的环境变量应带功能前缀，例如 `BOUNDING_BOX_*`、`TEXT_TRANSCRIPTION_*`。
- 跨功能共享的大模型基础配置可以继续使用 `LLM_*`。
- `.env.example` 只允许出现空值或安全占位值。

## 任务存储

- 运行时结果放在 `backend/jobs/`，并保持被 Git 忽略。
- 新功能应优先使用功能隔离路径，例如 `backend/jobs/<feature_name>/<job_id>/`。
- 版面分析当前仍使用历史路径 `backend/jobs/{model_dir}/{job_id}`，这是为了兼容已有结果；后续如需迁移，要保留旧路径读取逻辑。

每个任务结果至少应包含：

- `job_id`
- `feature`
- `filename` 或输入资源标识
- `status`
- `created_at` 或 `updated_at`
- 可供前端直接消费的结构化结果
- `errors` 和 `warnings`

## 提示词模板

- 每个标注功能维护自己的默认提示词和模板分类。
- 模板 `category` 应与功能目录或前端 `AnnotationFeature` 对齐。
- 保存模板时继续写入后端本地模板文件，但不要把用户运行时生成的模板文件作为默认提交内容，除非它是产品内置模板。

## 前端对接

新增标注功能时，后端接口、前端类型和页面入口需要一起对齐：

- 后端功能目录：`backend/features/<feature_name>/`
- 前端标注类型：`frontend/src/types.ts` 中的 `AnnotationFeature`
- 工作台入口：`Dashboard.tsx` 或后续功能路由
- 提示词分类：后端模板 category 与前端模板 category 保持一致

如果功能还没完成，只能以明确的“未上线”状态展示，不能让入口看起来已经可用。

## 验证要求

后端功能改动后至少运行：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/markhub_pycache python3 -m py_compile backend/server.py backend/features/layout_analysis/server.py
```

涉及前端联动时还要运行：

```bash
cd frontend
npm run lint
npm run build
```

涉及接口行为变化时，应启动服务后验证：

```bash
curl -s http://127.0.0.1:8787/api/config
curl -s http://127.0.0.1:8787/api/jobs
```

## 变更纪律

- 每次只实现一个功能模块或一个清晰的重构目标。
- 不要把无关 UI、模型提示词、运行配置和存储迁移混在同一次变更里。
- 新功能默认以可回滚的小步提交推进。
- 删除或迁移旧接口前，先确认前端和已有任务结果不会被破坏。
