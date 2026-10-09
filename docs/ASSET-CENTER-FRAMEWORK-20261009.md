# 资产管理统一框架：2026-10-09 本地候选

## 需求与结果

用户要求移除原资产工作区及旧版设计残留，由 UI/UX Studio 制定统一规范；最终确认白色侧栏、荧黄选中态。随后要求页面不再使用“台账”，资产库增加分类页签，重构截图中的冗余布局。

本次以 [统一设计规范](ASSET-CENTER-DESIGN-SYSTEM.md) 为当前界面依据。管理区使用同一导航、字体、间距、控件与响应式规则。资产库按“分类页签 → 筛选 → 列表”组织：名称与编号合并；归属展示部门及范围；保留状态、到期和有权限的操作。辅助视图通过小型视图选择器进入。

分类来自服务端真实字典，按排序字段呈现，不写死分类名称。`category_id` 与类型、部门、状态、搜索及回收站过滤同时作用于服务端列表和总数；只匹配该分类下的类型，不隐式展开子分类。切换分类重置页码，清除不兼容的类型筛选，保留其他条件；分类/类型/视图/回收站由 URL 恢复，过期响应不能覆盖最新选择。

可见文案统一使用“资产”；“平台账号”仍是有效业务名词。历史业务资料及历史文档未批量改写。

## 旧入口与兼容边界

- 删除旧 Hudu、旧首页/部门列表、失效图谱页面和图谱组件；删除未使用的 `@antv/g6` 依赖及旧主题样式。
- `/hudu` 跳到 `/assets`；旧 Hudu 资产详情保留对应资产 ID；旧接入、到期入口分别进入当前导入和跟进页面；旧首页/部门入口也有兼容跳转。
- 保留后端 Hudu 聚合读取接口，当前详情和跟进仍依赖它们。旧外观配置接口保留兼容；前端只使用当前统一设计，不再读取旧框架选择。
- 管理导航依据当前角色显示，员工保留个人与 AI 资产入口。导航隐藏不替代服务端授权；本轮未扩大任何权限。
- 原删除/恢复、负责人、登记身份、成果版本、确认和审核业务契约保持。未操作实际资产，未增加数据库迁移。
- 分类查询参数为可选，旧客户端兼容；发布新前端时须同时发布新增分类查询的后端文件。

## 验证结果

风险：分类查询和多页面导航为 T2；退役页面、主题、文案与表单可访问性随同检查。未涉及认证逻辑或生产数据改写。

| 检查 | 实际结果与边界 |
| --- | --- |
| 前端目标回归 | 26/26 通过；覆盖分类、URL 恢复、异步竞态、角色导航、选择登记类别、跟进、删除及成果版本 |
| 后端分类集成 | 13/13 通过；精确分类/分页/组合过滤、员工可见性、归档/回收站权限、非法 UUID |
| 导航辅助检查 | 11 项断言通过 |
| 最终生产构建 | `vue-tsc --noEmit && vite build` 通过；CSS `index-1OSwRM-w.css`，JS `index-DKVi9tNX.js` |
| 变更格式 | `git diff --check` 通过；只有现有 Git 换行转换提醒 |
| 独立源码复核 | 未发现功能阻断；合法员工可读部门/分类字典；小字号分区标题改用已有 `--muted` 颜色 |
| 浏览器展示 | 管理首页、资产分类/搜索/清空、旧链接跳转、外观设置、登记类别取消/切换、员工无管理权限提示已观察 |
| 窄屏 | 390px 视口下文档宽度 375px；分类页签及宽表格分别滚动，整页未横向溢出；设置与登记表单未挤压成窄列 |

前端命令（在 `frontend` 执行）：

```powershell
node --test --test-concurrency=1 tests/managementFramework.test.mjs tests/assetUsability.test.mjs tests/assetDeletion.test.mjs tests/outcomeVersions.test.mjs
npm run build
```

在工程根目录执行：

```powershell
node scripts/test-workspace-navigation.mjs
git diff --check
```

后端目标为 `backend/tests/test_asset_category_filter.py`。使用本机 `127.0.0.1:55433` 上新建的隔离测试数据库 `dam_v13_tests_category_2160a4b751`，关闭 `.env` 自动载入及外部连接器，采用本地测试配置；没有连接测试站或生产数据库。该测试要求遵守已有隔离环境门禁，不直接使用默认数据库运行。

浏览器预览为 `http://127.0.0.1:4184/assets`，使用忽略目录内的只读合成样例，API 写入全部拒绝。该预览不能证明真实业务持久化或用户验收。当前角色恢复为本地演示管理员，临时窄屏覆盖已重置。

截图仅保存在本机 `.local/`，不上传到 Git：

- `asset-library-unified-local-20261009.jpg`：最终桌面资产库；SHA-256 `e92488e3c2fcc766840b9d3810e6b10261e0e9a46bccf48002b784ec5edeaa2b`。
- `management-unified-local-20261009.jpg`：最终管理首页；SHA-256 `e35138de77a236d1b7a4bc6c6fb2c1cae00ed07529154fe0a14e99a4cd926697`。
- `asset-library-unified-narrow-local-20261009.jpg`：390px 资产库。

## 修改文件

| 范围 | 文件 |
| --- | --- |
| 当前规范与说明 | `README.md`、`docs/README.md`、`docs/ASSET-CENTER-DESIGN-SYSTEM.md`、本记录 |
| 分类读取与错误文案 | `backend/app/api/v1/assets.py`、`backend/app/repositories/assets.py`、`backend/app/services/assets.py`、`backend/tests/test_asset_category_filter.py` |
| 共享框架与路由 | `frontend/src/App.vue`、`frontend/src/router.ts`、`frontend/src/main.ts`、`frontend/src/components/ManagementNav.vue`、`frontend/src/lib/managementWorkspace.ts`、`frontend/src/lib/workspaceNavigation.ts`、`frontend/src/lib/aiDiscovery.ts`、`frontend/src/composables/useTheme.ts` |
| 当前页面 | `frontend/src/pages/AssetsPage.vue`、`AssetManagePage.vue`、`AssetFollowupPage.vue`、`IntakePage.vue`、`AdminPage.vue`、`AssetOverviewPage.vue`、`AssetDetailPage.vue`、`DirectoryDetailPage.vue`、`ImportWorkbenchPage.vue`、`OrganizationPage.vue`、`ScenarioWorkspacePage.vue` |
| 引导、设置与样式 | `frontend/src/components/AssetStructureGuide.vue`、`CatalogRulesPanel.vue`、`frontend/src/styles.css`、`frontend/src/styles/tokens.css` |
| 回归与依赖 | `frontend/tests/managementFramework.test.mjs`、`assetDeletion.test.mjs`、`assetUsability.test.mjs`、`scripts/test-workspace-navigation.mjs`、`frontend/package.json`、`frontend/package-lock.json` |
| 删除的旧页面 | `frontend/src/pages/HuduWorkspacePage.vue`、`HuduAssetDetailPage.vue`、`HuduExpirationsPage.vue`、`HuduIntakePage.vue`、`DashboardPage.vue`、`DepartmentAssetsPage.vue`、`AssetMapPage.vue`、`MyUsagePage.vue` |
| 删除的旧组件 | `frontend/src/components/AssetGraphCanvas.vue`、`ParticleGraphCanvas.vue` |

## 发布状态

当前为本地验证候选，分支 `codex/asset-center-registrar-completion`，基线 `58c0a36fe705dfb557d275a93ab6662e5654e03d`。本轮未推送、未部署、未改生产；此前获批上线的 `0263120` 不等于本候选的发布授权。

待用户批准确切候选后，先隔离测试再正式发布，并分别记录公网、实际登录页面和用户业务验收。代码/静态回退到本轮之前的发布，不涉及 schema 降级；仍须保留当前数据库和附件，不能用旧备份覆盖新业务资料。
