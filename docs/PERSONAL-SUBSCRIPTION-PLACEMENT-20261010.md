# 个人订阅仅从平台与账号查看

2026-10-10；任务 01a12369-6876-7eb2-9f77-1088f98dd3df。用户在上一版平台层级发布后明确：个人订阅仍出现在资产库，需要只从平台与账号查看。沿用本会话修复、推送及受控发布授权。

资产清单、分页总数、分类筛选、Excel 导出及管理概览统一排除个人订阅。识别与已有免审规则一致，同时满足 membership-registration 来源及 saas_subscription 类型；资金来源不用于判断。来源为空的公司 SaaS 订阅、其他类型采用同名来源时仍保留。原记录、UUID、免审状态及可见权限不变，无迁移或数据删除。

旧“我的订阅”路由转到“平台与账号”，选择平台后默认打开个人账号页签。侧栏“订阅”作为同一页面的快捷入口；原详情链接仍兼容。修改文件：backend/app/services/account_structure.py、repositories/assets.py、api/v1/hudu.py、api/v1/transfers.py、tests/test_account_hierarchy_lifecycle.py；frontend/src/router.ts、App.vue、pages/AccountsPage.vue；ASSET-CENTER-DESIGN-SYSTEM.md。

66 项隔离 PostgreSQL 定向检查通过，含个人/公司资金来源登记、清单/计数/筛选/导出/管理概览排除、来源空值和其他类型负向路径、平台保留、免审及原权限回归。证据 .local/subscription-verification/fb008a8dfa，集群已正常停止。根路径 Vue 类型与 Vite 构建、改动 Ruff（保留既有 E501 基线）及 diff 检查通过；/test 构建与受控测试/正式发布证据待追加。自动检查与人工业务验收分别记录。
