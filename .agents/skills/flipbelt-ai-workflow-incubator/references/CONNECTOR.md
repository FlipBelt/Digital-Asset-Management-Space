# 正式连接器模式 · 0.2.3-pilot

用户明确要求连接正式资产中心、组织保存或正式登记时读取本文件。本地试用仍读取 PILOT.md；该协议的禁用生产操作规则仅适用于本地模式。工具未安装、服务未启用或授权未完成时，保留本地成果并说明状态，不能假称组织保存。

## 连接与最小权限

先查看宿主实际工具目录，识别远程 OAuth 与 Windows 本机旧版。安装插件、工具发现、本人授权和组织保存分别核实；没有当前可调用工具时保留本地模式，不根据配置文件自报已连接。不索取、读取或输出 Cookie、令牌、客户端秘密或凭据文件，不通过 HTTP 脚本、浏览器会话或数据库绕过连接器。

### 远程 OAuth

远程连接由宿主处理 OAuth 发现、动态客户端注册（DCR）、PKCE S256 和本人网页同意。需要授权时引导本人使用宿主连接/重新连接入口；不得代替本人批准。远程没有 start_connection、complete_connection 或 disconnect，不调用本机设备码工具，不在聊天中索取 OAuth code 或 token。撤销通过宿主连接设置或本人“AI 助手连接授权”页面完成。

候选远程实现共有13种业务工具：get_capabilities、search_assets、get_asset、create_asset_draft、update_asset_draft、get_my_incubations、get_incubation、save_snapshot、operation_status、get_asset_details、save_asset_details、search_people、upload_asset_attachment。可见目录按 scope 过滤；名称可能带宿主 MCP 前缀，以实际目录为准。有 get_capabilities 时先读本人身份、真实类型、scopes 和支持字段；缺少此工具时不能伪造调用或扩大权限。工具目录与能力回读均支持时才调用；不能臆造 save_workflow、确认或审核工具。

远程附件用用户授权材料的 file_name 和 content_base64，连同 asset_id、version、request_id 提交，解码最大1,000,000字节；以实际工具 schema 为准。不得传 file_path、服务器路径或要求服务读取任意文件。没有读取和编码用户选定文件的权限或工具时保留附件入口，不编造上传结果。远程 save_asset_details 的 profile、fields、identifiers、责任候选字段位于工具参数顶层，不使用旧本机 details 包装。

当前候选入口 https://jtzhzt.flipbeltchina.com/mcp 尚未部署验证；代码、候选包或声明存在不代表服务可用。千问企业需要连接器开放策略和逐人 OAuth；ChatGPT 团队 App 绑定需要真实已注册 App 标识。缺少实际远程工具或服务时按本地模式交付，不声称组织登记成功。

### Windows 本机旧版

仅在宿主实际提供 Windows Python stdio MCP 及设备工具时，先 get_capabilities；未连接则 start_connection，向本人展示 verification_uri 和8位 user_code，由本人登录网页输入并批准，至少五秒后 complete_connection。pending 是待授权；授权期限以回执为准。该旧版共有上述13种业务工具加 start_connection、complete_connection、disconnect，共16个工具；不能将其数量或授权方式套用到远程。

旧版凭据由 Windows DPAPI 保管，只适用于实际运行端能访问的本机文件；本机 upload_asset_attachment 接受用户明确选定的绝对 file_path，每份最大20MB，save_asset_details 使用 details 包装。云端/Linux不能直接运行此 Windows 适配器，普通 HTTPS REST 地址也不是远程 MCP。安装说明与源码不会自动下载依赖、授予业务权限或完成本人授权。需要人工配置时提供套件 CONNECTORS.md，不读取凭据文件。已有同名服务时复用。

## 孵化器

沿用现有需求挖掘与方案深度，不重新访谈已知信息。用户要求组织保存、暂停续接或跨会话恢复后，只保存必要的 workflow_summary、opportunity_summary、blueprint_summary、next_step；不上传完整聊天、隐藏推理、整个仓库或秘密。资料中未经确认的内容继续明确标为候选。

save_snapshot 新记录 version=0；回执返回 id、version。续存先 get_incubation，再带当前 id、version 和新的 request_id 保存。恢复先 get_my_incubations；多项难以辨认时用少量选项定位，再读取该项。记录仅本人可见，孵化阶段 ready 仅是摘要阶段，不表示验收或发布。已有真实成果可用 asset_id 关联本人资产；孵化记录不另伪造 Asset。

## 登记器

1. 先主动读取当前授权成果与已有过程材料，形成同样的一页简卡。不要要求用户重复填组织字段。
2. search_assets 查当前可见 AI 成果；零结果只能说“当前可见范围未发现”，不声称组织内无重复。
3. 从 get_capabilities 的真实 asset_types 选择类型；没有恰当类型则保留原始形态及本地稿，说明需补字典，不把 Prompt、Template、MCP 或 Composite 硬映射为 Skill。requires_ai_development 类型必须注明实际 vibe_coding 或 mixed 开发方式，不能为通过校验编造。
4. 用户明确要求保存到正式中心后，将已经展示的名称和简卡写入 description，以 create_asset_draft 创建私有草稿。身份、归属和默认私有范围由服务端决定。先按实际 capabilities 判断补充资料、附件是否开放；未开放则保留本地入口，不能声称已上传。资产关系写入仍未开放。
5. 草稿改动时先 get_asset，再用 update_asset_draft 提交当前 version。正文可简明，依据保留本地；正式草稿内容变动必然需要新网页预览。
6. 展示回执中的 confirmation_url，由本人在网页核对确切内容版本、选择共享范围并确认。不要再让用户在聊天中进行一遍等效最终确认；聊天“确认”、旧的 CONFIRMATION-vNN.md、Agent 自报 confirmed=true 均不能代替网页确认。
7. 本人操作后 get_asset 重读。status=draft 表示尚未登记；active 且 review_status=pending_review 表示已登记、待审核，不能称已批准使用、收益核实或业务验收。不反复确认已登记且未变的版本。

## 补充资料、截图与责任建议

部署与客户端更新分别核验；仅修改此说明不代表生产具备新能力。get_capabilities 中 structured_details=true / attachments=true 且实际工具目录包含对应工具才进入以下流程；否则说明当前服务不支持，并保留本地材料，不以浏览器会话或脚本绕过连接器限制。

- get_asset_details 读取本人成果当前 version、真实 field_definitions 和已存资料。profile 只用于 profile_kind=internal_system；字段为 repository_url、production_url、tech_stack、deployment_guide_url、recovery_guide_url、backup_description。根据已授权仓库或用户材料填实际内容；未知的生产入口、部署和备份事实不推测。
- save_asset_details 只填写实际需要修改的键；按实际 schema 使用远程顶层参数或本机 details 包装：profile 为部分字段；fields 为 [{field_definition_id, value}]，采用服务端定义的 ID、数据类型与选项；identifiers 为 [{namespace, identifier_type, identifier_value}]，只加入用户提供或可靠材料中的真实外部标识，不伪造平台原生 ID，不更改内部资产编号。类型没有专属模板时不编造字段，可填写已有接管资料。
- 用户指定负责人或协同人后，以 search_people 按姓名定位本公司在职成员；同名或职责不明确时询问用户。用 proposed_responsible_person_id / proposed_user_person_ids 提交候选，仅提议，不授予责任权限。省略的候选字段保留；明确 null / [] 清空相应建议。管理员在资产“责任与使用”查看候选、核对后确认责任配置；登记器不能代替管理员确认。
- 成果可以是截图。upload_asset_attachment 仅上传用户明确指定或明确授权生成并选用的 PNG、JPG/JPEG、WebP 或 ZIP。远程使用 file_name + content_base64、解码最大1,000,000字节；本机旧版使用绝对 file_path、最大20MB，服务端再次校验。不向远程传服务器路径。界面说明截图、空字段截图不能冒充产品实际成果；不能擅自截取敏感业务数据、上传整个目录或仓库。附件名称简要说明截图内容；不声称截图证明业务验收。
- 补充已登记成果的资料或新增附件，会使其回到**私有草稿、待审核**，旧确认失效。执行前告知用户这一影响；在用户已要求补充且理解该影响的范围内继续，不重复问等效确认。完成所有补充后再展示同一个 confirmation_url，由本人一次预览确认最新完整版本。重读 get_asset / get_asset_details 核实，不把历史回执当当前状态。管理员直接维护资料也会推进版本并重置待审状态。
- 本人网页确认登记与管理员成果审核分开。审核入口为“管理区 → 成果审核”（/manage/reviews），待审详情有“审核此成果”。授权管理员或对应部门负责人可审核当前版本，通过或填写原因退回；角色是否有效以服务端为准。责任配置不会使采用确切版本确认的 AI 成果自动审核通过；无机器审核工具。审核通过仍不等同于真实使用验收。

## 重试与状态

每次变更先生成并保留 UUID request_id，再调用工具；将 id、version、request_id 与必要下一步保存在既有 RESUME 或用户已授权的过程记录中。原请求重试沿用原编号与原内容；修改内容使用新编号。

网络结果未知时优先 operation_status，用 draft.create、draft.update、incubation.save、details.save 或 attachment.upload 和原 request_id 查询；仅查询当前连接器实际支持的操作。404 表示该身份当前没有已提交回执，可以原内容与原编号重试；不为未知结果换编号重复创建。409 先核对旧回执 / 当前版本 / 内容，不能盲目重试。401 重新本人授权；403 停止该操作并保留成果；不得绕过机器权限改用浏览器会话、脚本 HTTP 或直接数据库。

当前代码分别提供受限 HTTPS API、本机 stdio MCP，以及远程 OAuth MCP 候选。实际部署、客户端发现、本人授权与真人验收分别以回执为准；代码或候选包存在不表示生产已上线。
