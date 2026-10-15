# 平台官方 Logo

关联任务：[FBC-215](https://linear.app/j21nianyi/issue/FBC-215)，代码与证据：[PR #21](https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/21)。用户明确授权候选 `1b216a847cee4f5d73d344510c9a09f069c32a92` 提交推送及测试→正式发布；2026-10-15 双环境已部署该应用版本，独立公开检查和认证页面回读通过。

## 范围与来源

冻结品牌表34项：27项使用核对后的官方原图；安捷云、易尚云、yishangcloud、预策、著作权登记系统、专利查询系统经用户明确保持待确认，“供应商待确认”继续中性占位。正式目录回读为34张卡片；测试目录的实际差异见发布记录。缺失图片不会按相似名称猜品牌。

用户另明确确认：现有“xAI”条目网址为grok.com，使用Grok官方产品图标，名称和网址不改。该匹配要求实际官网为grok.com，避免把SpaceX母公司图标或旧xAI标识混入。

素材取自官方网站实际声明的图标、站头Logo，或原发布者的官方App Store页面声明资源。12315和管易云使用其官方发布者App图标；京东与拼多多优先采用现有登记入口京麦/IPP实际声明的图标。来源、URL、核对时间、原文件SHA-256保存在 `frontend/src/assets/platform-logos/sources.json`。图片保留下载原始字节，未生成、重绘或更改颜色。

## 行为

- `PlatformLogo.vue` 用于平台目录卡片、平台标题、所属账号行和平台资料。完整平台名称继续显示，Logo仅作装饰，不承担唯一可访问名称。
- 本地资源由Vite处理根路径与`/test/`路径；浏览器不向第三方Logo服务发送平台名称或图片请求。官方来源URL只是复核记录，不用作运行时图片地址。
- 精确名称和官方主机白名单匹配；相似名称、拼接域名、带凭据URL、非HTTP协议不用于主机识别。已知品牌冲突与明确待确认条目显示中性图标。
- 正常标识框40×40；宽高比至少2.4的官方宽Logo用96×40框完整显示。图片加载失败回到方形中性图标，平台/网址变化后可重新加载。
- 不更改平台名称、网址、审核状态、账号数量或业务权限；无后端或数据库迁移。

## 验证

- 前端目标19/19通过：5项来源/映射边界、5项组件真实渲染/失败恢复、9项平台工作台与路由回归。命令：在frontend目录执行 `node --test --test-concurrency=1 tests/platformBrand.test.mjs tests/platformLogo.test.mjs tests/platformWorkspace.test.mjs`。
- `npm run build`（含Vue类型检查）通过；另以VITE_BASE_PATH=/test/、VITE_API_BASE=/test-api执行Vite构建到隔离输出目录。两套入口前缀正确，18份外置图片与原始SHA及双环境字节一致，其余由Vite内联；既有包体积提示保留。
- 本地只读合成页面34张卡片：27图实际加载、7中性图标、0外站Logo HTTP请求；搜索、375px窄屏、两种宽Logo比例、平台标题/账号行/资料页复用通过。Grok最终180px图标已回读；不连接真实后端，不保存业务资料。
- 独立代码与发布操作器复核无阻断；diff检查通过。无后端行为变更，未新增数据库测试；技术发布和真实业务验收分别记录。

## 发布与线上回读

- 应用版本：`1b216a847cee4f5d73d344510c9a09f069c32a92`（实现 `b2071c9`，SVG原字节保全 `1b216a8`），从线上基线 `95cf02a` 发布；后续文档提交不改变已部署应用版本。PR保持Draft/Open，未合并main。
- 测试：云助手 `t-hz07039boti8qgw`，exit 0 / PASS；旧应用和静态资源实际回退后重新应用同候选，保留schema，测试期间正式版本未动。
- 正式：云助手 `t-hz07039zbn5ntvk`，exit 0 / PASS。双环境各75张业务表内容保持，schema仍为 `f13f20261010`，无数据库迁移。发布包包含3个后端文件，其新旧字节相同，无后端行为变更；服务已按发布流程重启。正式环境未执行回退演练或数据库恢复。
- 双环境独立公开校验：各26个冻结静态文件逐字节一致，其中18个外置Logo文件，其余由构建内联；ready/database正常，13条SPA路径、13类匿名读及责任/标识/联系方式写入拒绝检查通过。首次公网读取超时后，仅在本地校验脚本加入有限网络重试，完整校验通过。
- 测试认证页面：实际33张卡片、26图加载、7中性、0加载失败。测试缺少Linear和易尚云，yishangcloud出现两项；未修改测试业务数据。测试门禁中的27/7明确是冻结品牌表覆盖数量，不能解释为测试DOM数量；Linear另有原图SHA、公开构建字节与本地加载证据。
- 正式认证页面：实际34张卡片、27图加载、7中性、0加载失败，模块 `/assets/index-Dk32LGoe.js`。搜索、Grok 180×180官方PNG、资料页及DeepSeek标题/账号行Logo复用通过。页面Logo的实际src均为同源或内联，官方SVG源已检查无外部引用；此项为DOM/来源检查，不宣称网络抓包。
- 私有本地回执位于 `.deploy-artifacts/platform-logos/1b216a847cee/`：`test-server-PASS.json`、`test-public-PASS.json`、`test-ui-PASS.json`、`production-server-PASS.json`、`final-public-PASS.json`、`production-ui-PASS.json`。未保存真实业务资料，未同步外部余额，未代替人工业务验收。
- 发布包SHA-256：`dd90d13962c3b7cb0ce8042c553bbf9643a0591e77866039b1109f40a8951231`；冻结操作器SHA-256：`9473eb34d347b3018e0e7a6076ffdd92244ba31b91b41c47a6bf83f4c99ec248`。两环境均保留发布前备份。

## 官方来源表


| 平台 | 官方原页面 | 原始素材 |
| --- | --- | --- |
| 12315 | [官方来源](https://apps.apple.com/cn/app/%E5%85%A8%E5%9B%BD12315%E5%B9%B3%E5%8F%B0/id1213288950) | [12315.webp](https://is1-ssl.mzstatic.com/image/thumb/Purple114/v4/0f/57/3f/0f573ffd-06fb-8582-c17e-ed6fa0a0decc/AppIcon-0-0-1x_U007emarketing-0-0-0-5-0-0-sRGB-0-0-0-GLES2_U002c0-512MB-85-220-0-0.png/400x400ia-75.webp) |
| 阿里知识产权保护平台 | [官方来源](https://ipp.taobao.com/home.htm#/home) | [alibaba-ipp.png](https://gw.alicdn.com/imgextra/i2/O1CN01qyQjdD1FrpEsmouLT_!!6000000000541-2-tps-106-106.png) |
| 阿里云 | [官方来源](https://www.aliyun.com/) | [aliyun.ico](https://img.alicdn.com/tfs/TB1_ZXuNcfpK1RjSZFOXXa6nFXa-32-32.ico) |
| Anthropic | [官方来源](https://www.anthropic.com/) | [anthropic.png](https://cdn.prod.website-files.com/67ce28cfec624e2b733f8a52/67d31dd7aa394792257596c5_webclip.png) |
| DeepSeek | [官方来源](https://www.deepseek.com/) | [deepseek.ico](https://www.deepseek.com/favicon.ico) |
| 钉钉 | [官方来源](https://www.dingtalk.com/) | [dingtalk.png](https://gw.alicdn.com/imgextra/i3/O1CN014ZbI6ZTEhdC0ttN2_!!6000000003783-2-tps-444-444.png) |
| 抖音 | [官方来源](https://trust.douyin.com/) | [douyin.ico](https://lf1-cdn-tos.bytegoofy.com/goofy/ies/douyin_web/public/favicon.ico) |
| Google | [官方来源](https://about.google/) | [google.png](https://www.gstatic.com/marketing-cms/assets/images/33/52/d31eb4894f69969b24d075e0d33c/favicon.png=s180) |
| 中国物品编码中心（GS1） | [官方来源](https://bizhall.ancc.org.cn/hall_web/) | [gs1.png](https://bizhall.ancc.org.cn/hall_web/favicon.ico) |
| 管易云 | [官方来源](https://apps.apple.com/cn/app/%E7%AE%A1%E6%98%93%E4%BA%91c-erp/id1641475064) | [guanyi.webp](https://is1-ssl.mzstatic.com/image/thumb/Purple116/v4/f0/01/fe/f001fe99-390f-1b59-8c09-6d85a95ab9a2/AppIcon-0-0-1x_U007emarketing-0-0-0-5-0-0-sRGB-0-0-0-GLES2_U002c0-512MB-85-220-0-0.png/400x400ia-75.webp) |
| 京东 | [官方来源](https://shop.jd.com/) | [jd.png](https://storage.360buyimg.com/shop-pageframe/shop.jd.com/v11/favicon/favicon.ico) |
| 聚水潭 | [官方来源](https://open.jushuitan.com/) | [jushuitan.png](https://open.jushuitan.com/skin/logo_jst_open.png) |
| Linear | [官方来源](https://linear.app/) | [linear.svg](https://linear.app/static/favicon.svg?v=2) |
| MiniMax | [官方来源](https://www.minimax.io/) | [minimax.ico](https://www.minimax.io/favicon.ico) |
| 网易企业邮箱 | [官方来源](https://qiye.163.com/) | [netease-enterprise-mail.png](https://mg.127.net/static/qiye-official/new/img/logo.23c43759.png) |
| 163邮箱 | [官方来源](https://mail.163.com/) | [netease-mail.png](https://mail.163.com/favicon.ico) |
| OpenAI | [官方来源](https://developers.openai.com/) | [openai.png](https://developers.openai.com/favicon.png) |
| 拼多多 | [官方来源](https://ipp.pinduoduo.com/) | [pinduoduo.ico](https://mms-static.pddpic.com/cpp/favicon.ico) |
| 新浪邮箱 | [官方来源](https://mail.sina.com.cn/) | [sina-mail.png](https://2008mail.sina.com.cn/images/mobile/icon_touch.png) |
| 搜狐邮箱 | [官方来源](https://mail.sohu.com/fe/) | [sohu-mail.png](https://1cbbb2d148753.cdn.sohucs.com/e0de4a/img/favicon.66dcaa54.ico) |
| 中国商标网 | [官方来源](https://sbj.cnipa.gov.cn/) | [trademark.png](https://sbj.cnipa.gov.cn/res/shangbiaoju/default/favicon.ico) |
| 微博 | [官方来源](https://zh.ir.weibo.com/) | [weibo.ico](https://zh.ir.weibo.com/favicon.ico) |
| xAI | [官方来源](https://grok.com) | [xai.png](https://grok.com/images/apple-touch-icon.png) |
| 小红书 | [官方来源](https://www.xiaohongshu.com/) | [xiaohongshu.png](https://picasso-static.xiaohongshu.com/fe-platform/f43dc4a8baf03678996c62d8db6ebc01a82256ff.png) |
| 影刀 | [官方来源](https://www.yingdao.com/) | [yingdao.svg](https://winrobot-pub-a-dev-1302949341.cos.ap-shanghai.myqcloud.com/image/20260901134651/5401fcb49f712bdcf1784a2c0da52685.svg) |
| 用友云 | [官方来源](https://www.yonyou.com/) | [yonyou.png](https://www.yonyou.com/favicon.png) |
| 知蝉网 | [官方来源](https://www.izhichan.com/) | [zhichan.png](https://www.izhichan.com/favicon.ico) |
