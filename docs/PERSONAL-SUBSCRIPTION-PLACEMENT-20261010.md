# 个人订阅仅从平台与账号查看

2026-10-10；任务 01a12369-6876-7eb2-9f77-1088f98dd3df。用户在上一版平台层级发布后明确：个人订阅仍出现在资产库，需要只从平台与账号查看。沿用本会话修复、推送及受控发布授权。

资产清单、分页总数、分类筛选、Excel 导出及管理概览统一排除个人订阅。识别与已有免审规则一致，同时满足 membership-registration 来源及 saas_subscription 类型；资金来源不用于判断。来源为空的公司 SaaS 订阅、其他类型采用同名来源时仍保留。原记录、UUID、免审状态及可见权限不变，无迁移或数据删除。

旧“我的订阅”路由转到“平台与账号”，选择平台后默认打开个人账号页签。侧栏“订阅”作为同一页面的快捷入口；原详情链接仍兼容。修改文件：backend/app/services/account_structure.py、repositories/assets.py、api/v1/hudu.py、api/v1/transfers.py、tests/test_account_hierarchy_lifecycle.py；frontend/src/router.ts、App.vue、pages/AccountsPage.vue；ASSET-CENTER-DESIGN-SYSTEM.md。

66 项隔离 PostgreSQL 定向检查通过，含个人/公司资金来源登记、清单/计数/筛选/导出/管理概览排除、来源空值和其他类型负向路径、平台保留、免审及原权限回归。证据 .local/subscription-verification/fb008a8dfa，集群已正常停止。Vue 类型、根与 /test 双路径 Vite 构建、改动 Ruff（保留既有 E501 基线）及 diff 检查通过。仓库没有 GitHub CI 检查，不报告 CI 通过。

应用提交 6654e4acc889331849077283f4016d969c4fceaf 已推送，沿用 Draft PR6。冻结增量 3396 字节、20 文件、1 块，SHA256 791c2a53dc9019af9fbb78df68966de7f6509ae6a8c246ea1036a8ccea2c90fa；以实际运行的 0541db065e51 为后端及静态基线，文档 HEAD 8cb2e61 不作为运行版本。

测试任务 t-hz06zlqka6fol4w 成功，包含旧代码/静态回退再应用且正式服务保持不变。正式任务 t-hz06zlqzanwqxvk 成功，两环境各 75 张业务表全行指纹保持，schema f13f20261010 不变，无迁移或数据删除。数据库 dump、旧代码和静态分别保留在两环境 backups/6654e4acc889-personal-placement-{test|production}-20261010；正式未执行回退或数据库恢复演练。

2026-10-10 08:53:16 UTC 独立公网回读：两环境前后端均为 6654e4acc889，各 8 冻结资源逐字节、7 SPA 路由、5 匿名读取及离职 POST 401、ready/database 通过。真实已认证管理员只读回读：正式资产库 12 项，个人 Plus 不在清单；OpenAI 下仍有 1 个个人订阅，标识无需审核。旧订阅快捷入口跳转统一平台页面，选择平台保留个人页签。测试库无该个人记录，23 项公司业务资产及公司 SaaS 保留；个人排除/保留与权限核心路径由隔离测试覆盖。两环境浏览器 warn/error 为空，无真实登记、离职、绑定、核验或责任写入。页面技术回读不替代人工业务验收。

证据目录 .deploy-artifacts/personal-subscription-placement/6654e4acc889：PACKAGE.json、DEPLOYMENT.json、test-server-PASS.json、test-public-PASS.json、test-ui-PASS.json、production-server-PASS.json、final-public-PASS.json、production-ui-PASS.json，以及 production-assets-without-personal.png 和 production-personal-subscription-platform.png。
