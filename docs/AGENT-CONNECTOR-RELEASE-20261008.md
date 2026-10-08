# AI 连接器生产发布记录 · 2026-10-08

用户已明确批准先测试再上线，并由本人完成阿里云登录。已按此顺序部署；没有代本人配对、创建成果或确认资产。

## 当前发布

- 源码提交：8ab801e1cecb70972de87b422edc4a22c43f71da。
- 生产：https://jtzhzt.flipbeltchina.com/；发布 8ab801e1cecb-agent-connector-production-20261008。
- 测试：https://jtzhzt.flipbeltchina.com/test/；发布 8ab801e1cecb-agent-connector-test-20261008。
- 两环境数据库仍独立：account_center / account_center_test；schema 均 f13d20261008。
- 仅新增 agent_grants、agent_operations、agent_incubations。生产原有72张表完整内容摘要一致；321资产、67人员、6用户、27类型、120服务实例保留。
- 正式连接入口：https://jtzhzt.flipbeltchina.com/agent/connect。
- Draft PR2：https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/2；未合并main。后续仅文档提交不改变此部署源码标识。

## 已执行的验证

- 基线68项后端目标检查、11项本机MCP检查、Vue类型和两种挂载构建通过。
- 最终代码再次通过22项连接器回归，包含生产模式真实Uvicorn HTTP进程、先ready再调用连接器的路径。原有路由与权限依赖保持不变。
- 空库及f13c升级/回退/再升级、本地旧表内容保留、带新表数据降级拒绝已验证。
- 服务器发布前核对实际服务、端口、两库、revision与磁盘容量。最初剩余约1.5GB；未为发布删除历史release或修改其他项目。
- 最终测试执行 t-hz06zei5fecx7gg，退出0；最终生产执行 t-hz06zeibg1ydfk0，退出0。
- 发布前由实际accountcenter服务账号加载候选代码，验证模块来源位于候选目录；停止服务后备份、对72张旧表逐表比较摘要，匹配才启动。
- 测试与生产各14项公网检查通过：release-meta、ready200、匿名/无效机器令牌/伪造会话401、无效配对输入422、原网页资产接口401、首页/授权路由200、JS/CSS及HTML与冻结构建逐字节一致。
- 正式授权页实际打开，访客状态与生产标识正确，浏览器error日志为空。截图显示在本Codex任务中；不称已完成真人登录或配对。
- 包含自动/合成检查；本人授权、客户端实际发现和业务验收仍开放。没有为演练写入生产孵化记录或成果。

## 发布过程中的修正

初次生产检查得到404，已两次自动恢复旧后端、旧静态资源和原配置；原有数据保留，新增三张空表未向下删除。
后来确认实际根因是私有解压目录0700被复制到生产root属主代码目录，accountcenter不能读取。
曾提出的路由搬移已撤回；最终业务代码仍沿用原挂载方式。部署脚本仅对发布包内代码设置目录0755/文件0644，保留秘密配置和运行数据原模式/属主，并增加服务账号来源检查。
随后重新验证/test/再发布生产，两次均通过。原始失败快照与回退材料仍在服务器私有备份目录。

## 包与备份

| 材料 | SHA-256 |
| --- | --- |
| 原始5a6c5f1完整包 | dcffdf074e26aa1e96bb13edc368be1b99031c07fff7fa8d6a53b5c1059dab25 |
| 最终8ab801e完整包 | 0fad156a95a453765c90018fb43ea47e4145bda21efc5f66a9eb71958c9820e8 |
| 8ab801e差异包 | 90b4995f4171f0044fbe4bdbbc52ccfcc924fc38718fcc9eda8d25c79670531b |
| 生产备份dump | 92aa0dd891565b0cb38348a841a1109c0af03f8610c582d6b237f5db17d21f5a |
| 测试备份dump | 2f90cf5765f68e020a7fcfd3fd1bc7e77695fcbdfce537963820253d3f4a5eed |

差异包仅替换说明、清单及发布元数据；服务器组合后全部128个文件摘要与最终完整包相符。业务后端与5a6c5f1一致，真实HTTP回归测试另随源码提交。

生产备份：/opt/account-center/backups/8ab801e1cecb-agent-connector-production-20261008。
测试备份：/opt/account-center-test/backups/8ab801e1cecb-agent-connector-test-20261008。
目录内保留database.dump、原app.env、backend-old、迁移前后摘要和PASS.json；dump已通过pg_restore --list，未在本轮生产上执行整库还原。

旧生产静态目录：/var/www/account-center-prod-releases/f784071-prod-20260930。
当前生产静态目录：/var/www/account-center-prod-releases/8ab801e1cecb-agent-connector-production-20261008。

本地完整包、PUBLIC-test.md / PUBLIC-production.md在工程.deploy-artifacts/agent-connector/8ab801e1cecb/。
最终发布、差异核验及失败回滚脚本在.deploy-artifacts/agent-connector/5a6c5f11245c/upload-parts/，不含凭据；配置和dump只留在服务器。

## 回滚边界

重新核对当前写入与授权状态后停止account-center.service，保留当前后端另存，恢复本次备份backend-old与原app.env，将静态符号链接切回旧目录，再启动并复核ready与匿名边界。
保留f13d的三张新增表及其中记录；旧应用可在增量schema上运行，前两次回退已验证此兼容路径。
不自动降级、清空新表或整库覆盖已有新业务记录。若需要恢复schema或业务数据，须另行审阅当前差异与恢复范围。

## 人工待验收

在新Codex会话调用已安装Skill，明确“连接正式资产中心”，由本人在授权页完成首次配对；随后验证孵化快照、私有草稿修改、网页确切版本确认和撤销。
Qoder-CN共享Skill已同步；IDE复用同一stdio适配器的配置见AGENT-CONNECTOR.md，实际发现尚未验收。当前聊天不能保证热加载新MCP工具。
