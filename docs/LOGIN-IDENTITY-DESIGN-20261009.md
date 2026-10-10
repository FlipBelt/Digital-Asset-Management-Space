# 登录、网站图标与本人头像

2026-10-09 实现，2026-10-10 按用户“执行上线”授权完成测试与正式发布。运行代码为 `4604859361b360975704924a52a37f8c54647bb1`，上一版为 `2d07deb`。遵循资产中心统一设计规范及用户确认的白色、深色文字、荧黄强调。

## 最终行为

- 登录页独立展示品牌与登录操作，钉钉扫码为主，系统账号折叠展示。服务检查、未配置、失败重试、回调会话失败及账号错误继续使用既有认证行为。
- 网站图标为深色底上的荧黄层叠资产符号，表达成果汇聚、归档与积累。SVG 只有几何图形，不依赖字体、脚本或外部资源。原 FlipBelt 完整标志保留。
- 静态加载页与应用异常页复用图标和样式。应用文件失败显示刷新/返回登录页；15 秒未完成显示加载较慢及恢复操作，不将慢加载当作已确认故障。已挂载的业务页不会被此计时器替换。
- 当前会话增加可选 `avatar_url`，从服务端已认证用户对应的既有钉钉资料读取，只接受无账号密码的 HTTPS 地址；不新建身份、不调整认证和权限、不新增迁移。顶部及侧栏复用；缺失、非 HTTPS 或加载失败显示姓名首字。图片请求不附带本站 Referrer。

## 变更文件

- 登录与框架：`frontend/src/pages/LoginPage.vue`、`frontend/src/styles/login.css`、`frontend/src/styles.css`、`frontend/src/App.vue`。
- 加载与图标：`frontend/index.html`、`frontend/public/favicon.svg`、`frontend/public/boot.css`、`frontend/public/boot-recovery.js`、`frontend/src/main.ts`。
- 头像：`backend/app/services/avatar.py`、`backend/app/api/v1/sessions.py`、`backend/app/schemas/auth.py`、`frontend/src/lib/api.ts`、`frontend/src/components/SessionAvatar.vue`。
- 验证：`backend/tests/test_session_avatar.py`、`scripts/test-boot-recovery.mjs`；已有登录回跳和导航验证保持。

## 已执行验证

- 本地回环 `127.0.0.1:55433` 既有隔离库，`test_session_avatar.py`、`test_pm_session_security.py`、`test_dingtalk_web_login.py` 共 68 项通过。涵盖头像空值/危险地址/本人关联、会话安全、OAuth 失败与旧登录兼容。保留既有 Starlette/httpx 弃用警告。
- 定向 Ruff、`git diff --check`；加载恢复断言、登录安全回跳与错误提示断言、11 项工作区导航断言通过。
- `npm run build`（含 Vue 类型检查）及 `/test/` 基路径构建通过。根路径与测试路径的图标、加载脚本、样式和登录链接正确；不改变 API 环境选择规则。
- 内部浏览器本地合成预览：桌面与 390px 无横向溢出；键盘首个焦点到扫码按钮并显示焦点框；登录服务未配置/503重试、错误账号、无会话回调标记、正确回跳目标、应用文件失败恢复可见。
- 头像组件用公开品牌图作为合成成功样例，实测正常加载、失败/缺失/HTTP 回退及地址变化后的恢复。该样例不是真实钉钉头像。
- 图标实际渲染检查 16/24/32/64px 浅深背景，SVG XML检查自包含几何。截图仅在忽略的 `.local/` 目录保留。

实现阶段线上首页正常打开且浏览器无错误记录，用户截图的历史停留原因未被确定。2026-10-10 部署后已验证真实本人头像 CDN 及现有会话兼容；重新扫码、钉钉设备与人工体验仍独立待验收。本地合成验证不等于这些结果。

## 2026-10-09 公司归属只读核验

- 已在内部浏览器打开钉钉后台，用户本人登录。后台当前组织为杭州飞途行远企业管理有限公司，与资产中心组织名称一致。
- 钉钉首页显示 63 名企业成员、4 名未进入组织；资产中心显示 67 当前成员、24 部门、17 公司来源项。统计口径不同，不能把差值直接当作缺失、离职或错误归属。
- 钉钉成员基础资料可见：廿一-孙伟强，部门运营中心-产品设计，“主体（社保公司）”为杭州创简品牌管理有限公司。资产中心对应成员显示“尚未核对公司字段”，公司视图显示 67 名待核验。
- 该字段只证明当前钉钉资料中的主体归属；不证明法定代表人、股权或劳动合同。下级组织共享成员与社保公司、法定代表人继续分开核验。
- 只读取和搜索，没有保存钉钉成员、点击资产中心同步/核对按钮、更新公司字段、修改角色或业务资产。未逐人核对全部成员。后续需在授权范围内刷新字段并回读，再逐人核对差异，保留未知与冲突。

## 发布与回退

已先测试再正式发布，静态资源包含 `favicon.svg`、`boot.css`、`boot-recovery.js`，测试使用 `/test/` 与 `/test-api`，正式使用 `/`。无 schema 变更；代码/静态资源可回到上一版，回退仍须保留当前数据库、附件和身份资料。

## 2026-10-10 上线证据

- 分支 `codex/asset-center-registrar-completion` 已推送，既有 Draft PR #3 远端头为 4604859；没有 GitHub 检查，不把本地验证称为 CI。后续文档提交不改变运行代码。
- 只读预检 `t-hz06zkkl1z855og`，exit 0：双环境上一版 2d07deb，服务 active，schema `f13e20261009`，各 75 张业务表。
- 冻结双环境差量包 19 文件、71931 bytes、3 分片，SHA-256 `e531cd123169b682e399023e37d42f94ee7be8ce932195fd801044c8a5c30a92`；部署脚本实际字节 SHA-256 `146334e390e1f8f4c5d9c0e32deef0099cecc153879ddc12da3fc2f53e773f6f`。服务端校验旧源码基线、包、重建后的源码与全部静态文件。
- 测试 `t-hz06zkkqjknh6gw`，exit 0：75 张业务表完整内容指纹一致，schema 不变，代码/静态回退并重新部署通过，正式服务 PID 与发布元数据未改变。
- 正式 `t-hz06zkkunbfs2dc`，exit 0：75 张业务表完整内容指纹一致，schema 不变，服务 active。未迁移数据库、升级依赖、修改 Nginx、同步人员或操作实际资产。
- 双环境各 22 项独立公网检查通过：元数据、ready、6 个匿名受保护接口 401、9 个 SPA 入口（含登录）、JS/CSS 及三份公共资源与冻结文件字节一致。正式 JS `index-BsCi7Wjx.js`，测试 JS `index-CDakdcH_.js`，CSS `index-DO9IhJm_.css`。
- 内部浏览器已观察两环境新登录页、扫码入口可用及无页面错误；既有本人管理员会话刷新后，顶部/侧栏真实头像均从 HTTPS 成功加载（384px、no-referrer），正式首页成果 V1 保持。桌面整页无横向溢出。没有重新扫码或代用户确认手机登录。

| 环境 | 备份目录 | 数据库转储 SHA-256 |
| --- | --- | --- |
| 测试 | `/opt/account-center-test/backups/4604859361b3-login-test-20261010` | `a0ce403e257dda139cf3eefb8d38776c644bca0451b65899ead0e5bfa7307e6c` |
| 正式 | `/opt/account-center/backups/4604859361b3-login-production-20261010` | `666afd3acd956c18fe31ebfcb8a7c4d0b6cd968169c7fd33fd5da3c0db428708` |

旧代码/静态、配置、当前数据库转储及回退说明保留。转储完成且 `pg_restore --list` 可读；没有完整数据库恢复演练。测试演练仅回退代码/静态，保留 schema 和业务数据。服务器回执目录 `/opt/account-center/releases/login-4604859361b3-upload`；本机冻结包 `.deploy-artifacts/login-identity/4604859361b3/`。

正式截图仅保存在本机忽略目录：`.local/login-production-release-20261010.jpg`（SHA-256 `f47b0be74fdeabb0be176e853012d2a1d1226cbaae33532b0922ff3dc4925ec4`）、`.local/avatar-production-release-20261010.jpg`（`b042b36ac6f2f9c95b7e1f5dbdc43263354d942e9e84dc41b3622803257e0c38`）。真实重新扫码、手机钉钉及人工体验仍独立开放；公司资料核验继续按原待办处理。
