# Markhub

Markhub 现在按前后端分离结构组织：

- `frontend/`：React/Vite 前端页面，来自 `markhub-annotation-dashboard`。
- `backend/`：Python PDF 版面分析服务，包含模型调用、任务记录、旧版静态预览页和本地配置。
- `.tools/`：工程辅助资料和本地开发工具。

## 目录结构

```text
Markhub/
  frontend/   # 前端应用
  backend/    # 后端服务
  .tools/     # 开发辅助文件
```

## 一键启动

```bash
./start.sh
```

脚本会同时启动后端和前端：

- 后端：`http://127.0.0.1:8787`
- 前端：`http://127.0.0.1:3000`

如果前后端已经在运行，脚本会自动复用已有服务，不会再次占用同一个端口。

按 `Ctrl+C` 会同时停止两个服务。

如需自定义端口或 Python 路径：

```bash
BACKEND_PORT=8788 PORT=3001 PYTHON_BIN=/path/to/python ./start.sh
```

## 单独启动后端

```bash
cd backend
python server.py --port 8787
```

后端说明见 `backend/README.md`。

## 单独启动前端

```bash
cd frontend
npm install
npm run dev
```

前端说明见 `frontend/README.md`。
