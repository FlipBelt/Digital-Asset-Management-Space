# 管理员删除与资产回收站

日期：2026-10-09。用户要求移除配色中台登记，并在管理页面支持删除现有资产。

## 行为与边界

- 管理首页 → 公司资产台账 → 搜索资产 → 删除 → 核对名称、编号、版本 → 确认删除。
- 管理首页 → 资产回收站，可查询和恢复已删除资产。
- 仅系统管理员或拥有 asset.write 的资产管理员可删除、查看回收站及恢复删除项；部门负责人、普通员工和受限 Agent 无此权限。
- 使用现有 status=deleted 与 archived_at 保存删除状态，无数据库迁移或物理级联删除；不删除仓库或注销外部资源。保留资料、附件、引用和审计。
- 普通台账（含已归档）、个人空间、发现及登记器查询不展示删除项。归档与删除分别呈现。
- 行锁与版本检查阻止旧版本删除；重复 DELETE 返回当前删除结果，不重复增加版本或审计。恢复后再用旧版本删除会失败。
- 恢复 AI 成果为待核验草稿，清除确认、重置审核；必须重新确认与审核。重新登记使用新的 request_id 和资产编号，旧请求的幂等回执不代表新登记。
- 管理台增加服务器分页和名称、编号、平台标识搜索；删除确认有忙碌/失败/取消状态及键盘焦点循环、Esc 关闭和焦点返回。

## 验证

T3。隔离 PostgreSQL 127.0.0.1:55433，dam_v13_tests_registrar_* 合成数据库；不使用生产测试。

- 新增 4 项集成场景：管理员权限、部门权限、CSRF、版本冲突、重复删除、查询隔离、审计、保留标识、恢复与新登记、旧确认失效及状态字段绕过保护。
- 资产空间、会话安全、可见性 36 项原回归通过；修正重复删除问题后，4 项删除及 22 项登记器回归共 26 项通过。
- 前端新增 4 项状态场景，结合原 10 项人员/附件/分类检查共 14 项通过；Vue 类型检查和 Vite 构建通过。
- 定向 Ruff 通过；assets.py 原有 3 处长行不在本轮修改范围，针对该文件忽略 E501，其余规则通过。diff 检查通过。
- 本地浏览器使用合成资产完成删除、取消、回收站、恢复；窄屏复核发现旧台账筛选与页头操作横向溢出，补充单列与换行规则；Shift+Tab 循环、Esc 取消和焦点返回通过。
- 没有 GitHub Actions 工作流，不将本地检查表述为 CI。

命令（工程根目录）：

```powershell
$env:PYTHONUTF8='1'
backend/.venv/Scripts/python.exe .local/rerun.py tests/test_asset_deletion.py tests/test_agent_connector.py
```

前端目录：

```powershell
node --test --test-concurrency=1 tests/assetDeletion.test.mjs tests/assetUsability.test.mjs
npm run build
```

## 发布与实际删除

- 实现提交 d038e5a；最终代码 df31b595271800e50f5fee3cb68f02ae2a6a388d 已推送 PR3 所在分支。没有合并 PR。
- 已按测试、正式顺序发布最终代码；双环境各 13 项公网状态、静态 JS/CSS 字节核对通过。匿名回收站、审核、登记器和个人空间接口保持 401；服务健康正常。
- 测试环境真实演练旧代码/静态页回退后重新应用候选；生产保留可用旧代码与静态目录。无数据库迁移、认证配置或 Nginx 配置变更。
- 最终包 SHA-256：7fb98b0f8340c5ac49bcf09ab2ccaa8debb343c4eb6b3bf4bda8b887261332ca。重建时逐文件核对基线与目标 SHA，避免应用到其他版本。
- 测试进程 1705498，正式进程 1705549。schema 均 f13d20261008。服务启动前后 assets、asset_attachments、asset_identifiers、asset_responsibilities、asset_relations、asset_confirmations 六张表内容指纹一致；该范围不等于全库审计。
- 正式删除通过管理员网页执行，仅目标 1d17eb78-85d6-5d90-90fd-adeb0bac85a1、系统-001。删除前重新读取 v12，删除后 v13/status=deleted；一条 asset.delete 审计，服务端操作身份与连接器用户一致。
- 删除后五张关联资料表内容指纹保持，物理资产行数仍 322；页面回收站显示目标与恢复按钮。登记器 search_assets 返回空列表，get_asset 返回不存在。
- 没有执行再次登记或恢复正式目标，也没有删除仓库、注销外部资源、指派责任人、确认成果或代替审核。
- 本地合成资产验证完整删除/恢复；服务器测试环境以现有管理员会话只读核对管理页、回收站与空搜索。正式目标的实际删除已核验；其他真实使用场景的人工 UAT 不因此完成。

### 证据与回退

- 本机：.deploy-artifacts/asset-deletion/df31b5952718/，含最终静态包、增量清单、部署/公网核验脚本与 PUBLIC-test.md、PUBLIC-production.md。
- 正式操作截图：.local/asset-deleted-production-20261009.jpg，1505×1244；SHA-256 a32bda59f24ddc648983aa969b3ae5d65dd891ab316fe252bb492d77b01fee61。
- 服务器：/opt/account-center/releases/deletion-df31b5952718-upload/，test-PASS.json、production-PASS.json、test-ui-PASS.json、DELETION-PASS.json 与对应 *-ROLLBACK.json。
- 正式旧代码：/opt/account-center/backups/df31b5952718-deletion-production-20261009/backend-old；数据库 dump 同目录，已核对 pg_restore 列表。旧静态目录：/var/www/account-center-prod-releases/255b32d3824d-usability-production-20261009。
- 如需恢复资产，使用管理页面“资产回收站”的恢复操作。代码回滚不恢复删除项；应用回滚按 ROLLBACK.json 停服务、切回旧 backend 与静态符号链接，再启动并检查 ready。本次未演练生产回滚或数据库恢复。

## 修改文件

- 后端：app/api/v1/assets.py、app/repositories/assets.py、app/schemas/assets.py、app/services/assets.py；tests/test_asset_deletion.py。
- 前端：src/pages/AssetsPage.vue、src/pages/AssetManagePage.vue、src/components/ModalPanel.vue、src/lib/api.ts、src/lib/labels.ts；tests/assetDeletion.test.mjs。
- 本说明文件。
