# 环境入口收口与上线记录

2026-10-10，用户要求移除前端测试环境的显性入口、收进系统管理员管理界面，并清除前端“生产环境”措辞；随后明确授权“推送上线”。运行前端提交为 `b6a22600c298371b76cfa5c937cf2680c23313b2`，后端继续使用 `4604859361b360975704924a52a37f8c54647bb1`，schema 为 `f13e20261009`。

## 最终行为与文件

- 顶部不再显示环境切换，侧栏只显示用户与角色。
- 测试入口位于“公司资产管理 → 系统设置 → 环境管理”，沿用服务端会话中 `system_admin` 的既有显隐判断。正式侧显示“当前：资产中心”和“进入测试环境”；测试侧显示“返回资产中心”。本地预览不提供环境切换。
- 详情、成果确认与审核的字段显示为“访问地址”，登记示例使用“业务系统主实例”“集团中台服务器”等中性用语；内部 `production_url` 字段保持兼容。
- 入口隐藏不改变直接访问 `/test/` 的能力或后端 RBAC；未修改身份、角色、数据库、依赖或 Nginx 配置。

| 文件 | 修改 |
| --- | --- |
| `frontend/src/App.vue`、`frontend/src/styles.css` | 移除全局环境入口、标签与废弃样式 |
| `frontend/src/pages/AdminPage.vue` | 系统管理员环境管理页签与往返链接 |
| `frontend/src/pages/AssetDetailPage.vue`、`AssetReviewPage.vue`、`IntakePage.vue` | 中性字段与示例文案 |
| `frontend/src/components/AssetConfirmationPanel.vue` | 中性字段名称 |
| `README.md`、`docs/ASSET-CENTER-DESIGN-SYSTEM.md` | 入口位置及统一设计规则 |

## 验证证据

- `node scripts/test-workspace-navigation.mjs`：11 条导航断言通过；`npm run build` 的 Vue 类型检查与构建通过，根与 `/test/` 两套冻结构建均成功；`git diff --check` 通过。
- 前端源码、公用资源及两套构建中无“生产”固定文案。本地只读合成 UI 完成两环境管理员往返，以及员工、资产管理员、部门主管、组长、审计员、匿名共 12 个负向场景；非系统管理员不显示系统设置或环境入口。
- 冻结包 16 个静态文件、71391 bytes，SHA-256 `2c5fde3ebcc71117b4a577dc85eec874c3b818253164d4d4fbe66791c7bbb963`；上传脚本 SHA-256 `29a70b1dc67f4ce7dd927892009717705675f45007ebc81f551e40c97bcfd745`。服务端先校验脚本、包和旧静态文件，再重建并校验所有新文件。
- 只读预检 `t-hz06zkno2jb5khs`，exit 0：两环境服务 active，schema 一致，均有 75 张业务表。预检物理资产行数测试 321、正式 324；该计数不作为新增、删除或业务验收证明。
- 测试发布 `t-hz06zkobru3gt1c`，exit 0，01:39:22 UTC：8 个静态文件校验通过，75 张业务表发布前后完整内容指纹一致；原静态版本回退、ready 回读及新版本重新应用通过；正式服务 PID 与元数据保持。
- 测试环境公网检查通过后，实际已认证管理员页面显示环境页签，顶部/侧栏环境链接为 0，页面无生产措辞，返回链接 `href=/` 实际进入 `/my`。据此写入正式发布门禁。
- 正式发布 `t-hz06zkokcn22fpc`，exit 0，01:42:03 UTC：8 个静态文件通过，75 张业务表发布前后完整内容指纹一致；服务 PID 保持、没有重启后端或执行数据库写入。
- `python .local/verify-environment-public.py test` 及随后 `python .local/verify-environment-public.py final` 通过。最终每环境 8 个静态文件与冻结字节一致、5 个 SPA 入口 200、ready/database 正常、4 个匿名受保护读接口 401。正式 JS `index-B2rIojNR.js`，测试 JS `index-haJ80z-z.js`，CSS `index-C6nOdRgt.css`。
- 正式浏览器刷新后实际加载新 JS；管理员经管理导航进入系统设置看到“环境管理”，进入链接 `href=/test/` 实际到 `/test/my`，测试返回实际到 `/my`。顶部/侧栏切换入口为 0，页面无生产措辞，浏览器 error 日志为空。
- 代码已推送 `codex/asset-center-registrar-completion`，既有 Draft [PR #3](https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/3) 保留；没有 GitHub 检查，不把本地验证称为 CI。后续证据文档提交不改变运行前端提交。

本轮覆盖代码验证、公网资源核对与实际管理员页面回读；员工真实会话及人工业务验收独立，合成身份验证不替代人工 UAT。没有代用户登记、确认、审核、删除或改派任何业务资产。

## 回退与证据位置

| 环境 | 当前静态目录 | 保留旧静态目录 | 本轮私有证据备份 |
| --- | --- | --- | --- |
| 测试 | `/var/www/account-center-test-releases/b6a22600c298-environment-test-20261010` | `/var/www/account-center-test-releases/4604859361b3-login-test-20261010` | `/opt/account-center-test/backups/b6a22600c298-environment-test-20261010` |
| 正式 | `/var/www/account-center-prod-releases/b6a22600c298-environment-production-20261010` | `/var/www/account-center-prod-releases/4604859361b3-login-production-20261010` | `/opt/account-center/backups/b6a22600c298-environment-production-20261010` |

服务器回执在 `/opt/account-center/releases/environment-b6a22600c298-upload/`：`test-PASS.json`、`test-ui-PASS.json`、`production-PASS.json` 及两环境 `*-ROLLBACK.json`。备份保存静态基线、服务状态和表内容指纹；本轮没有新的数据库转储，上一版数据库备份继续保留。测试演练只回退静态资源，正式没有执行回退演练。

如需回退正式前端，在目标服务器执行下列命令；先确认当前仍是本轮版本，仅原子切换静态链接，保留后端、schema 和业务数据：

```bash
/opt/account-center/.venv/bin/python - <<'PY'
import json
import os
from pathlib import Path

link = Path('/var/www/account-center')
old = Path('/var/www/account-center-prod-releases/4604859361b3-login-production-20261010')
temporary = link.with_name('account-center-environment-rollback')
assert link.is_symlink()
current = json.loads((link / 'release-meta.json').read_text())
previous = json.loads((old / 'release-meta.json').read_text())
assert current['commit'] == 'b6a22600c298371b76cfa5c937cf2680c23313b2'
assert current['backend_commit'] == previous['backend_commit'] == previous['commit'] == '4604859361b360975704924a52a37f8c54647bb1'
assert current['schema'] == previous['schema'] == 'f13e20261009'
assert not temporary.exists() and not temporary.is_symlink()
temporary.symlink_to(old, target_is_directory=True)
os.replace(temporary, link)
print(json.dumps({'frontend_commit': previous['commit'], 'static': str(link.resolve())}))
PY
curl -fsS https://jtzhzt.flipbeltchina.com/release-meta.json
curl -fsS https://jtzhzt.flipbeltchina.com/api/v1/health/ready
```

本机冻结包及公网回执：`.deploy-artifacts/environment-entry/b6a22600c298/`；正式截图：`.local/environment-entry-production-20261010.jpg`，均在忽略目录。开发状态同步至规格仓 `D:/flipbelt-ai-asset-center/docs/TODO.md`。
