# 登记器补充资料、截图与成果审核候选

日期：2026-10-08。状态：本地实现与定向验证完成，未推送、未部署。
正式工程：Digital-Asset-Management-Space。
候选目录：C:/Users/MSI/Documents/Codex/work/asset-center-registrar-completion。
分支：codex/asset-center-registrar-completion；起点：ae853598529aa35016baa096ef980958c3adddee。

## 使用结果

- 登记器可读取真实类型字段、接管资料、外部标识和人员候选，并补充本人成果。没有字段模板时不创建模板；未知部署、备份或平台编号不猜填。
- 成果附件支持 PNG、JPG/JPEG、WebP 与原有 ZIP，每份上限20MB。图片验证实际格式、尺寸和内容，通过有权限的接口预览/下载；不接受SVG或伪装扩展名。
- 登记器仅建议本公司在职负责人/协同人。管理员在“资产详情 → 责任与使用”核对、采用建议并确认，候选不会直接赋予权限。
- 审核入口：管理区 → 公司资产管理 → 成果审核，路由 /manage/reviews；待审资产详情提供“审核此成果”。管理员/资产管理员和授权部门负责人/组长在服务端范围内审核；普通员工、审计只读角色与机器令牌不能审核。
- 审核支持通过当前版本、填写原因退回、已通过/已退回列表、分页和单资产直达。退回原因进入证据与历史，并在创建人详情显示。负责人确认与成果审核分开，原公司资源发现流程继续保留。

## 版本与权限

| 操作 | 结果 |
|---|---|
| 登记器补充本人已登记成果/新增附件 | 私有草稿、待审核、版本加一；本人需重新预览确认 |
| 本人网页确认草稿 | 登记为在用；审核仍待人工处理 |
| 管理员确认AI成果责任配置 | 责任关系生效、版本加一、待审核；不代本人确认草稿 |
| 审核当前待审版本 | 通过/退回、版本加一、记录操作者与原因 |
| 版本过期/重复审核 | 409，要求刷新核对 |
| 同附件重复上传 | 返回已有附件，不重复创建或额外改版 |

机器读写限服务端核验身份的本人成果，即便用户是管理员也不继承管理区全量写权限。所有新增机器写入绑定原request_id、目标与内容摘要。仅补部分候选角色时保留未提供的角色；显式null/空数组才清除对应建议。
本人确认摘要包含接管资料、字段标签与值、外部标识、候选姓名和附件；预览不暴露存储路径。

## 接口与适配器

新增受限API：GET /agent/people；GET/PUT /agent/assets/{id}/details；POST /agent/assets/{id}/attachments（实际API统一前缀沿用既有路由）。
新增网页API：GET /asset-reviews；POST /asset-reviews/{id}，依赖既有认证与CSRF检查。
MCP新增 get_asset_details、search_people、save_asset_details、upload_asset_attachment，目录共16项。
operation_status 支持 details.save / attachment.upload，以原UUID恢复未知结果。
新增能力回执 structured_details=true、attachments=true、attachment_formats 和 responsibility=proposal_web_governance；relations仍为false，confirmation仍为web_only。

资料示意（真实ID由先读字典/人员返回，不自行生成）：

```json
{"profile":{"repository_url":"https://github.com/example/repository","tech_stack":"已核实的技术栈"},"fields":[],"identifiers":[]}
```

适配器只读取用户指定的绝对附件路径，限支持的扩展名和有界读取；不枚举目录、不回传文件内容。
Skill 0.2.1在项目源和C:/Users/MSI/.agents/skills共享目录同步，实际工具目录与能力回执双重门禁；旧服务不会被当作支持新增写入。0.1.7本地登记协议未修改。

## 文件范围

- 后端：agent_connector API/Schema；registrar_details/outcome_attachments 服务；asset_confirmation；资产资料/责任/附件接口；新增 asset_reviews 与路由；Pillow依赖及锁文件。
- 前端：AssetAttachments、AssetConfirmationPanel；AssetReviewPage；管理入口、概览和台账详情；API、审核文案与路由。
- 适配器：connector/src/flipbelt_connector/server.py 及目标测试。
- 部署配置：两份Nginx模板上传请求上限10m→30m，容纳20MB附件的base64封装。本次未安装配置或执行线上nginx -t。
- 新后端目标测试：backend/tests/test_registrar_completion.py。

## 实际验证

1. 隔离回环PostgreSQL，显式设置本地测试环境；候选backend/.env不存在，不读取生产配置。最终定向回归104项通过，0失败/错误/跳过，XML在忽略目录 .local/target-results.xml。
2. 新增测试34项覆盖：本人边界、跨公司/离职人员、候选部分更新、字段校验、内部编号保护、过期版本、旧确认失效、三类图片/ZIP、伪装及超限拒绝、授权下载、重复附件、权限/CSRF/部门隔离与审核审计。
3. MCP目标检查13项通过；官方stdio发现16工具通过。四套Skill官方结构检查通过，项目源与共享目录的四个修改文件逐个SHA-256一致；两种独立只读前向演练通过，演练不代表实际写入或业务UAT。
4. 前端 npm run build（vue-tsc与Vite）通过；最终资源 index-BUTJW-xk.js / index-CmMzF46-.css。后端改动定向Ruff与git diff --check通过。
5. 本地浏览器合成账号实际检查：管理卡片与资产直达审核；候选显示“待管理员确认”、实际负责人“待配置”；PNG上传并640×240解码预览；补充回私有草稿v2；预览显示资料/候选/附件后合成确认为v3；空原因退回被阻止，有原因退回v4；创建人可读原因；中文已退回列表与截图预览正常。没有使用实际产品资产完成这些合成操作。

最终后端命令：

```powershell
backend/.venv/Scripts/python.exe .local/rerun.py tests/test_registrar_completion.py tests/test_agent_connector.py tests/test_asset_center_integration.py tests/test_asset_visibility.py tests/test_pm_session_security.py tests/test_asset_space.py tests/test_discovery_intake.py::test_employee_discovery_flow --junitxml=../.local/target-results.xml
```

.local/rerun.py 是本机隔离环境包装器，强制测试库前缀及回环地址。其他环境请先提供专用测试库，不直接沿用生产环境变量。

扩展旧导入检查有两项失败，均在原始ae853基线复现：
- test_full_legacy_html_data_is_staged_without_payment_secrets：Git快照缺少本地旧版*v4(1).html，StopIteration。
- test_boss_pilot_import_is_private_and_reviewable：补齐合成公司前置后，created_internal_system_assets实际0、预期1。
证据在 .local/BASELINE-TEST-RESULT.txt / .local/BASELINE-IMPORT-RESULT.txt。未修复这两个无关旧问题，不声称全量测试全绿。

## 上线与回退待办

本次没有新数据库迁移，继续使用f13d20261008现有表；没有修改实际产品资产、职责、审核或成果附件。页面截图来自空表单，仅作需求依据，未被上传为产品成果。

上线须用户另行明确授权这份候选：重新核对当前远端/生产基线，备份代码、静态、配置和数据库；先隔离/test/再生产发布匹配前后端与Pillow锁定依赖；核验Nginx请求上限与nginx -t；同步本机适配器并刷新实际16工具发现和能力回执。发布过程不得代本人配对/确认或审核实际成果。

回退匹配的后端/前端/适配器和Nginx配置，保留数据库记录和附件文件，不整库恢复覆盖新记录。旧版本不提供新增截图预览/工具，但数据保留。新旧客户端靠能力门禁兼容。
真实管理员/创建人业务验收、Qoder-CN实际发现及钉钉窄屏体验尚未执行；自动验证与本地合成检查不关闭这些事项。