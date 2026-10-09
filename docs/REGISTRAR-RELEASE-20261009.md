# 登记器补充资料与成果审核发布记录

日期：2026-10-09。状态：按用户批准先测试、后正式上线完成；真实业务验收单列。

## 版本与范围

- 发布代码：3af34f13033dd3b8019b51f3cf22f12399edba68；分支 codex/asset-center-registrar-completion。
- 审阅：https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/3 。只推送本候选，没有合并 main 或其他工作区改动。
- 发布包 SHA-256：bfa9b9b0aec76e2bcb7d0ae2c78a6a90656c376384c1fcb318d9442629fd952e；127个文件逐一校验。
- 发布脚本 SHA-256：de3286cbd7228834108f533623378e719578eb1075fa527eea538eab2d26c03d。
- 沿用 schema f13d20261008，没有执行迁移；Pillow 12.3.0 与锁文件一致。
- 接管资料、真实类型字段、外部标识、负责人/协作者候选、PNG/JPG/WebP/ZIP附件及独立成果审核入口上线。候选不授予权限，责任配置和成果审核由管理员在网页分别完成。

## 实际发布证据

| 环境 | 云助手任务 | 服务 | 资产数 | 公网检查 |
| --- | --- | --- | --- | --- |
| /test/ | t-hz06zh1zkad9csg | active，PID 1693130 | 321 | 18项通过 |
| 正式 | t-hz06zh23o15k8ao | active，PID 1693212 | 322 | 18项通过 |

- 两环境的页面、JS、CSS字节与各自冻结发布包一致；新接口匿名401、无效机器令牌及无效会话401、无效配对输入422、健康就绪200。
- 测试发布核对正式服务PID和静态版本未变后，才允许正式发布。
- 最终复核任务 t-hz06zh2yu8jci68：两环境全部76张public表在重启和只读检查后仍与本次备份前摘要一致；以实际accountcenter账号运行已部署代码，PNG/JPEG/WebP内存图片校验通过，附件目录可写。
- Nginx两个API作用域均30m，nginx -t通过；备份和附件目录仍私有。
- 现有管理员会话实读测试/正式管理区与成果审核页面成功。正式列表显示配色管理中台第5版待审核，详情及审核说明/通过/退回按钮可见；未点击实际审核操作。
- 新安装本机适配器源码哈希与候选一致，官方stdio发现16工具；正式capabilities实读 attachments=true、structured_details=true、格式png/jpg/jpeg/webp/zip、responsibility=proposal_web_governance、confirmation=web_only、relations=false。
- 原配色中台资料接口200，仍active/v5/pending_review；未修改实际资产、指派责任、确认版本或上传空表单截图。

公网核验回执位于本机 .deploy-artifacts/registrar-completion/3af34f13033d/PUBLIC-test.md 和 PUBLIC-production.md。远端私有暂存目录 /opt/account-center/releases/registrar-3af34f13033d-upload 保存 test-PASS.json、TEST-PUBLIC-PASS.json、production-PASS.json、POST-RELEASE-PASS.json。

## 处理的问题

首次测试预检查因Pillow程序文件继承私有umask，服务账号读取异常而失败，尚未切换服务。失败暂存目录和日志保留在测试备份的 -preflight-failed-1 目录。发布脚本改为仅将Pillow程序目录0755/文件0644，并重新验证服务账号导入；运行数据和秘密配置权限不扩大。随后测试、正式和重启后的图片解码检查通过。

本机 uv tool install --force 被已打开的stdio进程占用，中断卸载；通过 uv pip install --python 既有工具解释器 ./connector --offline 恢复依赖并更新源码，源码哈希及新进程16工具发现通过。现有聊天仍缓存旧12工具，需要重连该MCP连接器或重新启动Codex以载入新目录；没有终止其他聊天进程或改动授权凭据。

## 备份与回退

- 测试：/opt/account-center-test/backups/3af34f13033d-registrar-test-20261008 。数据库备份SHA-256 88b9337cc85cde67630acdf883008f50cd49a2c5306f2d39af85c992c6575701。
- 正式：/opt/account-center/backups/3af34f13033d-registrar-production-20261008 。数据库备份SHA-256 52e3f7c2417f353f0110f1e9866bbe508988ab59f4edba50b4de42160c9e2d26。
- 备份包含旧后端、Nginx配置、秘密配置和可列出的数据库dump；不在仓库或本文复制配置值。
- 回退时按环境停止对应服务、恢复backend-old和旧静态链接、恢复匹配Nginx配置并nginx -t/reload/start；保留新附件及数据库记录，不以整库恢复覆盖新记录。没有新增迁移需要降级。

## 验收边界

隔离后端104项、MCP13项、构建与本地合成截图上传→确认→退回链路证据见 [实现记录](REGISTRAR-COMPLETION-20261008.md)。扩展旧导入2项失败在原始基线复现，不宣称全量测试全绿。

正式页面只读复核和部署通过不替代真实创建人/管理员的资料补充、候选采纳、截图确认及审核业务验收；Qoder-CN实际发现、钉钉窄屏及业务UAT尚未执行。旧会话载入16工具的客户端重连需用户完成，既有授权仍按原有效期由服务端验证。
