# AI 发现与员工登记修正：隔离测试部署

- 日期：2026-09-30；目标：`https://jtzhzt.flipbeltchina.com/test/`，ECS `i-bp1ghxzf20sidk0m18t1`。
- 源码：`f78407110117610b4d236e6d5cf8229f637ed46b`，已推送 `codex/asset-center-v13-fusion`；Draft PR #1 保持开放，未合并 `main`。
- 发布标识：`f784071-ai-discovery-20260930`；前端按 `/test/` 和 `/test-api` 单独构建，后端仅更新 `app/api/v1/asset_space.py`。未修改 Schema、身份配置、生产环境或业务数据。

## 本次行为

员工发现与团队空间按“知识与方法、工具与助手、应用与自动化、业务工作流”展示符合 AI 条件的成果；普通平台、账号和基础设施在管理员公司资产管理中处理。员工 AI 成果登记与订阅登记分离，工作流有独立的“全部工作流／我创建的／我的收藏”视图。既有 Asset 类型、UUID、草稿确认、共享范围和历史事实未迁移或重写。前端分类不构成新增服务端权限策略。

## 发布及验证证据

- 本地：`node scripts/test-ai-discovery.mjs`、`node scripts/test-workspace-navigation.mjs`、正式前端 `npm run build` 和 `/test/` 专用构建通过；`pytest tests/test_asset_space.py` 11 项通过，Ruff 与 diff 检查通过。未启用的隔离集成测试不能计为本轮通过。
- 包：本地忽略目录 `.deploy-artifacts/ai-discovery-f784071/` 内的 manifest、operator、八分段经独立重组及 SHA-256 校验，载荷 179882 字节，SHA-256 `f97a85aea27061f2f52a587fb0e81a092ce659fa8c66520be64a69abc960c04e`。服务器预检复核 operator、manifest、八分段及载荷哈希。
- 发布前：测试静态目录仍为 `0c176a8-discovery-management-20260929`，Schema `f13c20260928`；目标后端源码、生产首页哈希及生产 PID 与清单基线一致。服务器约有 1.53 GB 可用空间。发布预检记录 35 张业务表指纹和 84 项活跃资产。
- 发布：阿里云 ECS 云助手命令 `t-hz06yl3nmaox8n4` 退出码 0，返回 `phase=deployed`、`environment=test`、确切提交 `f784071...`、测试 ready 200、四个匿名业务接口 401。部署后 35 张业务表指纹、测试配置、生产 PID 与生产首页哈希均未变；数据库未迁移。
- 公网：`/test/` 的 `index.html`、`logo.svg`、`release-meta.json`、CSS、JS 五个文件均 HTTP 200 且 SHA-256 与 manifest 一致；`/test-api/api/v1/health/ready` 为 200，匿名业务接口为 401，`/test-api/api/__preview__/admin` 为 404。
- 真实浏览器：已登录的测试系统管理员会话可打开 `/test/manage`；六个公司基础资料登记入口可见。`/test/workflows` 显示独立工作流页签及空状态，浏览器 error 日志为空。当前测试库在 AI 发现和工作流中均无可见记录；此观察不等于成果登记业务 UAT。

## 恢复与剩余验收

发布前后端源码备份和静态版本保存在 `/opt/account-center-test/releases/f784071-ai-discovery-20260930/` 与 `/var/www/account-center-test-releases/f784071-ai-discovery-20260930/`。如需精确回退，先复核当前生产/测试基线，再执行：

```sh
/opt/account-center-test/.venv/bin/python /opt/account-center-test/releases/f784071-ai-discovery-20260930/operator.py rollback
```

回退命令已准备，**未执行**；本次无数据库迁移，未做数据库恢复。真实员工、主管、组长及钉钉设备上的登记、订阅、申请和贡献流程仍需人工验收；自动检查与管理员浏览不替代该结论。
