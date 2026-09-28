# 钉钉网页登录

普通浏览器通过钉钉官方扫码页面授权，返回后使用同一企业员工身份和服务端会话。钉钉内原免登接口保持兼容；网页登录不接收客户端指定的员工、企业或角色。

## 接入流程

1. `GET /api/dingtalk/web/config` 仅返回是否启用、是否已配置。
2. `GET /api/dingtalk/web/authorize?next=/my` 创建五分钟有效的状态及 HttpOnly 浏览器绑定 Cookie，然后跳转钉钉官方授权页面。授权范围为 `openid corpid`，固定指定已配置企业。
3. `GET /api/dingtalk/web/callback` 校验浏览器绑定并原子消费状态，随后在服务端交换授权码。确认返回的 `corpId`，通过个人 `unionId` 查询本企业 `userid`，再获取企业员工资料并复用原身份映射。
4. 回调设置应用 HttpOnly 会话 Cookie，重定向至本环境 `/login`；前端重新请求当前会话，确认后回到原页面。返回 URL 不携带授权码、上游 token 或应用会话 token。

缺少有效状态、浏览器不匹配、状态过期/重放、非本企业、身份映射不一致、未同步部门、停用账号均拒绝登录。浏览器 Cookie 写操作仍需 CSRF；正式权限仍由服务端 RBAC 决定。测试环境原有全量测试权限策略没有改变。

## 测试环境配置

在现有钉钉内部应用的「开发配置 → 安全设置」中，保留原配置并登记回调 URL：

```text
https://jtzhzt.flipbeltchina.com/test-api/api/dingtalk/web/callback
```

需要现有「成员信息读权限」及「通讯录个人信息读权限」。2026-09-28 已在「集团账号管理中台」核对两项均为已开通；经用户明确确认，测试回调地址已保存并重新进入安全设置核对持久状态。此实现不请求个人手机号或个人邮箱权限。员工本人完成扫码授权。

在隔离测试服务的环境文件中保留现有 AppKey/AppSecret、CorpId 和独立测试 Cookie 名称，仅补充：

```dotenv
DINGTALK_WEB_ENABLED=true
DINGTALK_WEB_REDIRECT_URI=https://jtzhzt.flipbeltchina.com/test-api/api/dingtalk/web/callback
DINGTALK_WEB_FRONTEND_URL=https://jtzhzt.flipbeltchina.com/test/
SESSION_SECURE_COOKIE=true
```

配置由服务端固定，不根据任意 Host/Forwarded 请求头或客户端参数生成回调域名。HTTPS 登录要求 Secure Cookie；回调和前端必须同源。仅本地开发允许回环 HTTP 地址。以上配置属于 `/test/`，不会自动开启生产网页登录。

## 数据迁移和回滚

新增迁移 `f13c20260928`，只增加 `dingtalk_web_login_states`。该表只保存随机状态、浏览器绑定的哈希、内部回跳路径及过期时间，不保存授权码或 token。成功/取消请求后消费状态；新登录请求会清理过期状态。

停用网页登录时将 `DINGTALK_WEB_ENABLED=false` 并重启测试服务；原免登继续可用。新应用可保留新表回滚到旧版本。仅需要撤销这条增量迁移时，可降级到 `f13b20260928`，只丢弃待完成的短期登录请求，不删除员工或业务记录。

`deploy/account-center.https.nginx.conf` 包含测试回调专用位置，避免访问日志记录授权码查询参数，并设置 `Referrer-Policy: no-referrer`。应用也对回调访问日志和钉钉上游 URL 的敏感参数做脱敏。部署时需要安装相应位置规则并运行 `nginx -t`；不应只部署业务代码而遗漏代理配置。

## 验证

本轮在本地 `127.0.0.1:55433` 隔离库验证：

- 新网页 OAuth 测试 49 项与旧会话/免登兼容测试 2 项通过。上游接口使用 HTTP mock，不能替代真实钉钉授权验收。
- 状态并发消费仅一条连接成功；错误状态不执行上游交换。
- Cookie/CSRF、已有员工映射复用、外企业及停用账号拒绝、回跳路径与日志脱敏通过。
- `f13b → f13c → f13b → f13c` 演练通过；71 张原业务表的行指纹一致。
- Vue 类型检查、本地前端构建和回跳辅助函数断言通过。

2026-09-28 服务器隔离 `/test/` 已部署功能提交 `a44ac57`，测试 schema 为 `f13c20260928`。备份独立还原的 72 表一致，迁移前后 71 张历史业务表指纹不变；公网 6 份前端文件哈希与冻结包一致，测试/生产 ready 均为 200，匿名业务 401，服务端演示入口 404，生产进程与静态首页基线不变。

测试回调专用代理已安装，测试网页登录开关已启用，`/api/dingtalk/web/config` 返回 `enabled=true, configured=true`。官方授权跳转、HttpOnly/Secure/SameSite Cookie、无效回调拒绝及生产边界检查通过，浏览器已到达官方授权页。未创建新的钉钉应用版本，未增加 API 权限；用户本人已完成官方授权并成功回到测试应用；2026-09-28 17:46:46 的服务端网页登录审计与既有员工映射一致，未创建重复身份。

真实网页登录及本人身份已核验；资产范围、原页面恢复、重新登录及钉钉内免登仍待验收。测试环境现有全量权限策略不能证明正式 RBAC 或真实业务 UAT 通过，不得以本地演示员工身份或 mock 测试代替此验收。

## 官方依据

- [获取登录用户的访问凭证](https://open.dingtalk.com/document/orgapp/obtain-identity-credentials)
- [获取用户 token](https://open.dingtalk.com/document/orgapp/obtain-user-token)
- [获取用户通讯录个人信息](https://open.dingtalk.com/document/orgapp/dingtalk-retrieve-user-information)
- [根据 unionId 获取企业 userId](https://open.dingtalk.com/document/orgapp/query-a-user-by-the-union-id)
