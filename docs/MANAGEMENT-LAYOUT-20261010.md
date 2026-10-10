# 管理页布局修复与发布记录

日期：2026-10-10。用户在本地查看修复后明确要求“推送上线”；已推送同一分支，先测试再正式发布，独立线上技术回读通过。人工使用验收由用户或指定验收人确认。

工作区：C:/Users/MSI/Documents/Codex/work/asset-center-management-layout

分支：codex/management-layout

PR：[管理页布局修复 #4](https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/4)，Draft，基于 codex/service-catalog-unification。本次沿用既有分支发布流程，未合并其他 PR。

## 结果与修改范围

管理页正文、系统设置全部子页签、导入上传/粘贴区及示例区，与资产库保持相同左右边界。内容填满可用管理区域，保留共享 1440px 上限及响应式边距；账号图标在 36px 容器中水平、垂直居中。

| 文件 | 修改 |
| --- | --- |
| frontend/src/styles/tokens.css | 管理区内全部 page-stack 使用 minmax(0,1fr) 并占满容器；覆盖导入区域独立宽度上限；审计空状态单列，有记录时在表内滚动 |
| frontend/src/styles.css | record-icon 的 grid 居中与零边距规则不再被通用 span 样式覆盖 |
| docs/ASSET-CENTER-DESIGN-SYSTEM.md | 记录共享容器、嵌套设置、导入面板及图标约束 |

初始修复 277fc42 仅检查页面外层；用户补充截图后发现嵌套设置及导入面板仍收窄，bd1f342 补齐这些内部区域。本次不改业务接口、权限或数据库结构。

## 冻结版本

| 项目 | 值 |
| --- | --- |
| 前端应用提交 | bd1f342763b0c63aa25723b0a691c69d03f388bb |
| 源码基线 | afc23867a038dcef121cc42cf820d83e37b2ce1f，保留既有目录整理 |
| 后端应用提交 | cbef316f8ab3ac1e46e78b7aa7cd1d8eae1f7ac3，保持原版本 |
| schema | f13f20261010，未执行迁移 |
| 双环境差量包 | 2249 bytes，16 文件；每个环境还原并验证 8 个完整静态文件 |
| 包 SHA-256 | b6dd4cc10c3ea2795d6aa45f505342275f16dbb91921c744fe307d0298dd46c6 |
| 部署脚本 SHA-256 | ae75f261ef08b4e380fb1e0a34468dc17b7a6929d39337cc74c9cab828ad4e17 |
| 正式 JS | assets/index-NHygNct1.js |
| 测试 JS | assets/index-C1dfDoEd.js |
| 共享 CSS | assets/index-LH32deaz.css |

正式与测试分别按 `/` 和 `/test/` 构建；冻结包基于干净的 bd1f342，发布后补充说明的文档提交不改变运行版本。

## 验证与发布证据

| 检查 | 结果及边界 |
| --- | --- |
| 本地构建 | npm run build 的 Vue 类型检查及 Vite 编译通过；冻结时两种部署路径构建均通过 |
| 初始外层布局 | 10 管理页 × 1920/390px，共 20 项；只证明外层，不代表嵌套面板 |
| 本地补修布局 | 五个设置子页签与导入上传/粘贴 × 两种视口，共 14 项内部边界通过；另有两项合成审计记录检查，窄屏只在表内滚动 |
| 线上基线预检 | 云助手 t-hz06zl329xr73sw；原双环境前后端均 cbef316，schema f13f，服务 active；静态完整字节与冻结基线匹配 |
| 测试发布 | t-hz06zl3lblot6gw，退出 0，2026-10-10T04:30:28Z；75 张业务表前后指纹一致，后端 PID 保持；旧静态回退及重新应用通过，生产未受测试切换影响 |
| 测试真实 UI | 1920×1080 / 390×844 下 14 项设置/导入检查通过；桌面宽度 1440px、窄屏约 342.67px，左右边界偏差及整页横向溢出均 0。加载完成的两个账号图标各视口中心偏差均 0 |
| 测试发布门禁 | test-ui-PASS.json 绑定 bd1f342，记录真实 UI、公开资源字节及测试回执；生产脚本核对后才切换 |
| 正式发布 | t-hz06zl3zr50ivwg，退出 0，2026-10-10T04:34:58Z；75 表指纹一致，后端未重启，数据库无写入，未执行生产回退演练 |
| 发布后独立公开回读 | 2026-10-10T04:35:17Z；双环境各 8 冻结静态文件逐字节一致、7 SPA 路由可达、4 个匿名受保护读取均返回 401；ready/database 正常，前端 bd1f342、后端 cbef316、schema f13f |
| 正式真实 UI | 同样 14 项设置/导入内部边界通过；桌面/窄屏各两个已加载账号图标水平及垂直偏差 0，36×36px、display:grid、margin:0；整页横向溢出 0，warn/error 日志为空。正常窗口外观页截图已实看，临时视口已重置 |
| GitHub 检查 | 仓库未配置 GitHub Actions，PR 未报告 CI 检查；以上构建、脚本及浏览器验证不表述为 CI |

真实管理员页面只进行读取与页签切换，未提交资产、导入或配置。线上技术回读不替代人工使用验收。

## 回退入口与证据位置

服务器受保护目录：`/opt/account-center/releases/management-layout-bd1f342763b0-upload`。保留 test/production-PASS.json、test-ui-PASS.json 和两环境 ROLLBACK.json；上传文件哈希在执行前已核对。

| 环境 | 当前静态目录 | 发布前静态目录 | 发布备份 |
| --- | --- | --- | --- |
| 测试 | /var/www/account-center-test-releases/bd1f342763b0-management-layout-test-20261010 | /var/www/account-center-test-releases/cbef316f8ab3-catalog-test-20261010 | /opt/account-center-test/backups/bd1f342763b0-management-layout-test-20261010 |
| 正式 | /var/www/account-center-prod-releases/bd1f342763b0-management-layout-production-20261010 | /var/www/account-center-prod-releases/cbef316f8ab3-catalog-production-20261010 | /opt/account-center/backups/bd1f342763b0-management-layout-production-20261010 |

当前静态入口分别是 `/var/www/test` 与 `/var/www/account-center`。回退前确认入口仍指向本次 bd1f342 目录，核对 ROLLBACK.json 及旧目录完整性，再按部署脚本中的原子符号链接切换函数恢复旧静态。测试环境已验证该步骤及重新应用；正式环境未执行回退。此回退保留现有后端、schema 和业务数据。

备份保存私有的发布前后 75 表指纹、原静态元数据及后端服务状态；本次只读数据库，没有新增数据库 dump 或执行数据库恢复演练。此前目录发布的数据库备份继续保留。

本地忽略目录 `.deploy-artifacts/management-layout/bd1f342763b0` 保存 PACKAGE/BASELINE/DEPLOYMENT、冻结静态文件、部署及公开回读证据；无凭据写入发布文档或 Git。

正式入口：[系统设置](https://jtzhzt.flipbeltchina.com/manage?tab=settings)、[批量导入](https://jtzhzt.flipbeltchina.com/imports)、[平台与账号](https://jtzhzt.flipbeltchina.com/accounts)。
