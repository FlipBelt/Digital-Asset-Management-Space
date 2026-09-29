# V1.3 资产中心融合与本地迁移记录

日期：2026-09-28。正式工程：Digital-Asset-Management-Space。远端基线：dffe81b59272a0e968c092d68452ee33994c0915。

本次按用户授权迁入正式 Vue / FastAPI / PostgreSQL 工程，并先在本地隔离数据库演练。交付通过功能分支 `codex/asset-center-v13-fusion` 和 Draft PR 审查；部署须等用户查看前端。未操作现有数据库、服务器数据库或生产服务。

## 实现与数据边界

- 我的空间直接提供首页、我创建的、我负责的、我的订阅、我使用的、我的草稿、我的收藏、我的 AI 能力和我的贡献。
- 资产发现与团队空间提供成果资产 / 工作流视图；工作流成果复用 Asset，未重建或改写历史分类，孵化过程仍独立。
- 管理侧栏只有一个管理入口，具体功能放在管理概览。员工没有激励规则入口；系统管理员查看的是尚未发布的规则草案。
- 收藏、订阅和实践证据使用真实 API 持久化。AI 探索必须关联本人自费订阅；公司购买、免费和试用不能提交为自费探索。
- 登记使用服务端员工身份。新草稿默认私有、待审核；创建者核对服务端返回的版本快照、附件和共享范围后明确确认。
- 确认凭据绑定用户、版本、摘要和时效；草稿、附件、关系或订阅事实变化使旧确认失效。并发 / 重复确认只形成一个版本和一条确认审计；取消与确认按同一资产锁串行，不能同时成功。
- 新登记资产归档后恢复为草稿，需重新确认；原历史资产恢复行为保留。
- 权限每次从有效身份、部门成员关系、角色和授权查询；个人记录 / 附件隔离，过期、撤销授权及无关联身份有负向验证。部门主管只按明确部门范围读取团队共享记录。
- 原底库、账号、组织、服务用量、流程风险、导入导出、Hudu、连接器及审计的路由继续保留。导出和关联详情也按资产可见性过滤。
- 不把登记状态解释为使用批准，不按记录数产生能力评分，不自动确认贡献价值或奖励。

资产来源字段增加 source_system / source_agent / source_reference / development_method；ServiceInstance 增加 funding_source / payer_person_id / usage_frequency / primary_purpose。Asset 增加 nullable sharing_scope；历史 null 保持原有共享 / 个人保密策略，不推断历史订阅由谁出资。

增量表：asset_bookmarks、asset_evidence、asset_confirmations。资产仍由现有 Asset 唯一承载。

## 本地预览

- 正式前端：[我的空间](http://127.0.0.1:4184/my)。
- 初次打开或切换员工演示会话：[员工预览](http://127.0.0.1:4184/api/__preview__/employee)。
- 管理演示会话：[管理员预览](http://127.0.0.1:4184/api/__preview__/admin)，进入侧栏“管理”。
- API：127.0.0.1:8113；专用 PostgreSQL：127.0.0.1:55433。
- 数据均为明确标注的【演示】内容，不是生产数据、真实购买、真实员工贡献或业务验收。
- 本地会话夹具只存在被 Git 忽略的 .local/replacement/preview_app.py。它创建真实数据库会话，通过正常 RBAC 和 Cookie / CSRF 处理请求，不进入正式部署代码。
- 预览启动文件：.local/replacement/start-preview.ps1；日志 / PID 也位于该忽略目录。原静态预览 4183 保留。

## 数据库演练证据

本次使用全新回环 PostgreSQL 17.11 集群，数据目录为 .local/replacement/pgdata；Docker 守护进程不可用，因此没有跳过数据库演练。

迁移链：b8c4d2e6f901 → f13a20260924 → f13b20260928。

| 检查 | 结果 |
| --- | --- |
| 空库 upgrade head | 通过 |
| 基线结构 + 合成资产 / 关系 / 订阅升级 | 通过 |
| 历史资产、编号、状态、版本及关系指纹 | 升级前后一致 |
| 旧订阅资金来源、付款人和用途 | 保留 null，未错误回填 |
| 已写入新事实时 downgrade | 拒绝执行，未删除事实 |
| pg_dump + pg_restore 至另一个新库 | 通过；历史指纹、新事实及 revision 保留 |

本次结果：.local/replacement/rehearsal/18f1953877/RESULT.md。
测试库：dam_v13_tests_18f1953877；预览库：dam_v13_preview_18f1953877。
升级 / 恢复对照库分别为 dam_v13_upgrade_18f1953877 / dam_v13_restore_18f1953877。
备份：同一演练目录内 synthetic-upgraded.dump，全部为合成数据且不提交 Git。

可重复演练命令（先启动专用 55433 集群；脚本固定回环地址、专用端口并创建全新随机库，不使用应用配置中的既有数据库）：

```powershell
& .\backend\.venv\Scripts\python.exe .\scripts\rehearse-asset-center.py --pg-bin .\.runtime\replacement-postgres\pgsql\bin
```

## 自动与浏览器验证

- `npm run build`：vue-tsc 与 Vite 构建通过。原 G6 图表块仍有大于 500 KB 的提示，未将此次融合扩大为性能重构。
- 新增与关键改动 Python 文件定向 Ruff：通过。
- 最终受影响功能回归：41 项通过，包含资产 / 工作台 / Hudu 旧流程、Cookie / PM 会话、CSRF、个人隔离、部门范围、撤权、附件、幂等、并发及确认版本失效。
- 完整回归曾运行：54 项通过、2 项失败。两个旧测试依赖 / 预期边界已核对，不计为通过：
  - test_full_legacy_html_data_is_staged_without_payment_secrets 依赖未纳入 Git 的 *v4(1).html 私有资料，当前克隆没有该文件。
  - test_boss_pilot_import_is_private_and_reviewable 没有传 include_internal_apps=true，却预期创建 1 项内部系统；基线 schema 的默认值已是 false。相关旧 API、schema 和测试未在本次修改。
- 浏览器已检查：我的空间、订阅 → 关联实践、草稿预览 → 取消 → 重新预览 → 确认、收藏后刷新保留、员工无管理入口、管理员单一管理入口、资产地图原页面加载。
- 390×844 窄屏检查：页面内容宽度不大于视口，菜单可打开 / 选导航关闭，Escape 可关闭；关闭抽屉后链接不可见 / 不可聚焦。
- 图中合成内容没有平台归属，因此原平台总览地图显示“无符合的平台”；真实公司的资产地图内容和规范有效性需要业务验收。
- 截图保存于 .local/replacement/screenshots/。没有把自动验证等同于真实业务或人工体验验收。

最终定向回归复现（在 backend 工作目录，显式选择隔离测试库）：

```powershell
$env:DATABASE_URL='postgresql+psycopg://preflight@127.0.0.1:55433/dam_v13_tests_18f1953877'
$env:APP_ENV='local'
$env:DINGTALK_ENABLED='false'
$env:ASSET_CENTER_ISOLATED_TESTS='1'
& .\.venv\Scripts\python.exe -m pytest tests/test_asset_visibility.py tests/test_asset_space.py tests/test_asset_center_integration.py tests/test_product_flow.py tests/test_workspace_flow.py tests/test_hudu_workspace.py tests/test_pm_session_security.py tests/test_test_environment_access.py -q
```

## 部署与回退门槛

用户先查看预览并确认导航 / 登记体验；真实员工、部门主管与管理员的钉钉登录、/test/ 挂载、真实资产与订阅数据、导入资料及人工业务验收尚未执行。不能把本地 APP_ENV=local 合成会话检查当成真实 IdP 或服务器验收。

生产替换仍需对应环境的确切版本、备份 / 恢复和迁移授权。优先回退前端与应用版本并保留新增事实；两个迁移在已有相关新事实时拒绝破坏性降级，必要时用经核对的备份恢复至另一个库，再安排受控切换。

本次不实现完整 Agent Connector、自动孵化过程持久化、激励审核与发放；这些继续按接受的产品计划独立推进。

## 2026-09-28 导航与 UX 优化及隔离测试发布准备

用户查看正式本地预览后授权提交、推送及部署，并明确选择现有服务器隔离测试环境 /test/。此范围不包含 main 合并或生产服务 / 数据库更新；AI 机会保持待开放。

本轮前端修改：

- 侧栏按我的空间 / 团队与资产 / 探索与成长 / 管理区重组；个人入口使用短标签与不同图标，工作流为统一资产发现页的类别快捷入口。
- 服务端身份与角色继续决定管理入口，身份信息移到侧栏底部；员工不展示激励规则。
- 详情保留来源列表，关键词、类型、团队与页码通过 URL 保存；关联资产继承来源，刷新可恢复条件。
- 订阅只列服务实例及实际 / 已选类型；收藏成功反馈以 API 保存结果为准，零结果支持清空筛选，越界页恢复到有效页。
- 统一类型卡片、详情按钮、表单及状态；窄屏导航增加背景 inert、Tab 循环、Esc 关闭及焦点返回。

改动位置为 frontend/src/App.vue、components/AssetCard.vue、pages/AssetSpacePage.vue、pages/AssetOverviewPage.vue、pages/AssetRegisterPage.vue、pages/AssetEvidencePage.vue、lib/assetNavigation.ts 与 styles/tokens.css。

验证：

- /test/ 专用构建设置 VITE_BASE_PATH=/test/、VITE_API_BASE=/test-api，vue-tsc 与 Vite 构建通过。产物置于独立忽略目录，不覆盖 4184 本地预览。
- 本次重新执行前述 8 个测试文件，41 项核心 / 权限 / 兼容回归通过，仅使用 55433 专用隔离测试库。
- 导航辅助函数 25 项返回地址与页码边界断言通过；源码仍为同一份已验证实现。git diff --check 通过。
- 本地浏览器验证了搜索 / 类型 → 详情 → 返回 → 刷新、零结果恢复、收藏保存与刷新、订阅关联实践往返、员工 / 管理员入口和图标唯一性。
- 320 × 844 CSS 视口 clientWidth=scrollWidth=305，抽屉焦点循环 / Esc 返回通过。以上为隔离演示检查，真实钉钉与业务 UAT 不计为完成。

发布目标：https://jtzhzt.flipbeltchina.com/test/；测试服务 account-center-test、独立测试数据库与 /test-api/ 挂载复用原配置。发布需先核验现有测试环境、备份与恢复、当前 migration revision，再应用增量迁移并核对接口、匿名边界、静态版本与原生产健康状态。产物绑定确切 Git 提交，不携带 .local 预览会话、数据库、凭据或备份。

本节记录准备与本地验证，不表示服务器已发布；服务器结果应以实际发布记录、版本和检查回执为准。


## 2026-09-29 发现分类与管理入口重组

按用户本轮反馈，分类发现和管理首页已重组；地图跳转发现，星图不再加载，测试环境不展示原工作区，系统设置合并管理入口，员工申请独立为本人流程。统一 Asset、私有草稿、确切确认和类型配置继续保留。实现、兼容性及本轮验证见 [资产发现与管理入口重组](ASSET-DISCOVERY-MANAGEMENT-REFACTOR.md)。本轮无数据库迁移或目录数据重写，实际测试发布结果另以回执更新。
