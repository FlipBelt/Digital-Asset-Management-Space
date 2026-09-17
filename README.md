# 集团账号管理中台

以账号为重要入口的公司账号与数字资产统一底库。当前本地版本已经具备真实数据保存、查询、编辑、归档、关系、责任、服务指标、Excel导入导出、流程风险、审计、连接器预留和统一的 FlipBelt v4 视觉主题。

## 直接使用

本地入口：<http://127.0.0.1:5173>
后端接口文档：<http://127.0.0.1:8100/docs>

服务器隔离测试环境：<https://jtzhzt.flipbeltchina.com/test/>
测试后端健康检查：<https://jtzhzt.flipbeltchina.com/test-api/api/v1/health/ready>

启动全部服务：

```powershell
.\scripts\start-all.ps1
```

停止全部服务：

```powershell
.\scripts\stop-all.ps1
```

查看状态：

```powershell
.\scripts\status.ps1
```

## 已实现模块

- 工作台：我的/部门/公司视角入口、实时指标、类型和状态看板、最近更新。
- 资产中心：统一资产CRUD、搜索筛选、四种分组视角、归档恢复、责任、关系和变更历史。
- 平台与账号：供应商、平台、企业租户、平台账号、MFA状态及外部密码库安全引用。
- 组织与人员：公司主体、部门层级和人员档案。
- 服务与用量：服务产品、购买实例、余额、额度、调用量、Token和费用历史。
- 流程与风险：固定申请状态流转、资产风险扫描及处理。
- 管理员控制台：分类与自定义类型、主题、功能配置、连接器、模拟同步和审计。
- 数据交换：Excel模板、上传预览校验、批次导入及Excel导出。
- 外部自动化：阿里云、DeepSeek和通用模拟连接器的数据结构及接口契约。

系统不保存平台密码、API Secret、私钥或恢复码，只保存外部密码库条目引用。

## 维护

### 隔离测试环境

服务器测试环境使用独立的 `account_center_test` 数据库、`account-center-test.service`（回环端口 `8200`）和 `/var/www/account-center-test` 静态目录。生产仍使用 `/` 与 `/api/`，测试只通过 `/test/` 与 `/test-api/` 访问。进入任一环境后，顶部“生产环境 / 测试环境”按钮可在同一个钉钉应用内切换；两套环境使用不同会话 Cookie，互不串会话。测试库首次创建前的生产快照保存在服务器备份目录，后续新方案、新迁移和版本升级先在测试环境验证，再安排生产发布。

测试环境部署单元见 [`deploy/account-center-test.service`](./deploy/account-center-test.service)，Nginx 路由见 [`deploy/account-center.https.nginx.conf`](./deploy/account-center.https.nginx.conf)。测试环境沿用现有钉钉登录配置；在普通浏览器中打开时，若出现“请从钉钉打开”属于预期行为。测试服务的 `APP_ENV=test` 会在完成身份认证后授予全量测试操作权限，便于自由探索；该授权分支只存在于隔离测试服务，生产服务仍按正式 RBAC 校验。

完整校验：

```powershell
.\scripts\verify.ps1
```

数据库备份（本地保留最近7份）：

```powershell
.\scripts\backup.ps1
```

首次重建隔离环境可执行：

```powershell
.\scripts\bootstrap-local.ps1
```

PostgreSQL Windows运行时位于项目`.runtime`目录，Python依赖位于`backend/.venv`，数据库、日志和备份位于`.local`。启动脚本使用`Q:`临时映射解决PostgreSQL对中文目录的兼容问题，真实文件仍在当前项目目录。

仓库同时包含经过筛选的产品/架构文档和交互原型，方便其他开发者理解系统边界并接入新功能。真实生产数据、数据库导出、备份、临时构建产物、会议汇报材料和密钥仍保留在本地，不纳入 Git。

新开发者请先阅读 [`DEVELOPMENT.md`](./DEVELOPMENT.md)。
