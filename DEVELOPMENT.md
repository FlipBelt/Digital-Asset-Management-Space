# 开发者上手指南

这份指南用于让新的开发者在本地启动“集团账号管理中台”并安全地接入功能。仓库只包含代码、迁移和经过筛选的设计资料；不会包含生产数据库、真实账号密码、API Secret、备份或内部原始导入文件。

## 1. 运行前提

- Windows、macOS 或 Linux
- Python 3.11–3.13
- [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ 和 npm
- PostgreSQL 14+

生产/服务器环境还需要由部署管理员提供钉钉应用配置、数据库连接和外部服务配置。不要把这些值提交到 Git。

## 2. 获取代码

```powershell
git clone https://github.com/FlipBelt/Digital-Asset-Management-Space.git
cd Digital-Asset-Management-Space
```

如果仓库为私有仓库，先让仓库管理员把你的 GitHub 账号加入仓库，再执行 clone。

## 3. 配置后端

```powershell
Copy-Item backend\.env.example backend\.env
cd backend
uv sync --extra dev
```

编辑 `backend/.env`，至少填写本地 PostgreSQL 的 `DATABASE_URL` 和应用需要的会话配置。`.env` 已被 Git 忽略，只能在本机保存。

创建一个空的本地数据库后执行迁移和演示数据种子：

```powershell
python -m alembic upgrade head
python -m app.cli.seed
```

种子数据仅用于开发验证，不是生产数据的副本。

## 4. 配置前端

```powershell
cd ..\frontend
npm ci
npm run build
```

开发时可使用 Vite：

```powershell
npm run dev
```

默认后端文档为 <http://127.0.0.1:8100/docs>，前端开发服务通常为 <http://127.0.0.1:5173>。前端需要后端和数据库同时运行，否则页面可能只有空状态或出现接口错误。

## 5. 使用仓库脚本

完成依赖和数据库准备后，可在项目根目录运行：

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend-background.ps1
.\scripts\status.ps1
.\scripts\verify.ps1
```

`start-all.ps1` 还会尝试启动项目附带的本地 PostgreSQL 运行时；该运行时位于被忽略的 `.runtime/`，新克隆环境没有它时请改用系统 PostgreSQL 或 Docker，并手动设置 `DATABASE_URL`。

## 6. 接入新功能的边界

- 先阅读 `docs/` 中的产品、架构和权限文档，再修改 API 或页面。
- 数据结构变更必须新增 Alembic migration，并补充后端测试。
- 权限判断以服务端会话和 RBAC 为准，不能只依赖前端隐藏按钮。
- 资产、平台、账号、人员、服务实例和关系等对象要复用现有模型，不要在前端另造一套并行数据。
- 连接器只能保存安全引用和同步状态，不提交密码、完整 Token、私钥或恢复码。

## 7. 提交与协作

```powershell
git checkout -b codex/<topic>
git status
git diff --check
git add <files>
git commit -m "feat: <描述>"
git push -u origin codex/<topic>
```

通过 Pull Request 合并到 `main`。生产发布前先在隔离测试环境完成迁移、接口回归和前端打开耗时验证。
