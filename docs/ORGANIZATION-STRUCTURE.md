# 公司主体归属与部门协作分离

组织架构提供独立的“公司”和“部门”视图。公司名通讯录节点不再计入职能部门，公司成员按成员详情中的公司字段分组，而不是沿用该公司名节点的部门挂靠成员。

## 来源与边界

当前已核对的来源字段为钉钉成员详情的“主体（社保公司）”。兼容 extension 对象 / JSON 字符串和 ext_attrs 同名字段的 value.text。只保存该字段的公司名、原始标签、核对状态和时间；不保存完整成员响应或新增联系方式、证件等资料。

这个字段证明钉钉资料中的主体归属，不证明公司负责人、法定代表人、股权或劳动合同关系。公司主体档案仍独立维护；未登记的公司来源项不会自动创建法人、资产或权限。

- 公司视图：按可用主体字段列成员，同时显示成员的职能部门。目录公司名、已有法人和主体字段按精确名称合并展示，不据名称推断同一工商实体。
- 部门视图：保留职能层级、原部门成员/主管关系；公司名节点从部门树分离。跨类型父节点只在展示层投影到最近职能部门上级，不修改数据库父子关系。
- 现有组织绑定继续确定读取/补同步范围；Person.legal_entity_id 保留现有租户边界。主体字段不会被写回租户、主要部门、角色或资产权限。
- 名称后缀仅用于目录节点的展示分类，不作为法人登记或核验依据。登记公司仍使用现有主体档案流程。

## 可核对与待核验

管理员可通过“核对公司归属”补齐已存在人员的公司字段及当前可见目录快照；新接口 POST /api/v1/dingtalk/organization/companies/refresh 沿用现有管理员门槛和绑定目标保护。

上游查询在写入之前全部完成。详情身份不一致、目录空或一般接口失败时不写入新快照；60121只记录“源资料不可查询”，不据此判定离职、归档人员或撤回权限。公司字段缺失、格式异常、两个来源冲突时不推测公司，集中列为待核验。成员字段接口继续要求管理员，不暴露完整 profile_data。

旧目录节点不在最新可见目录中时，主树不再计数，保留于“历史节点待核验”。这可能是删除、范围变动等原因，不自动删除既有数据。完整部门同步仍是独立操作；公司核对不更新部门成员关系。

无需新增 Schema，使用既有 profile_data 与 AppSetting 保存小型白名单快照，并记录汇总审计。发布前对受影响字段和快照保存精确回退资料，生产与角色指纹分别复核。

## 2026-09-29 验证

- 本地回环55433隔离库：pytest tests/test_dingtalk_organization.py tests/test_pm_session_security.py，46项通过，覆盖公司解析、冲突、不可查、完整失败保留、身份一致性、管理员/绑定保护及旧登录兼容。
- node scripts/test-organization-structure.mjs：16条断言通过，覆盖公司/部门来源分离、跨主体隔离、历史节点、循环/跨类型父节点及输入不变。
- 本次Python文件定向Ruff、git diff --check、Vue类型及本地正式构建通过。
- 既有Starlette/httpx弃用和大块构建警告保留，没有改无关依赖。
- 合成测试不代表真实组织资料、完整权限或钉钉设备UAT。服务器发布与真实页面结果另记录在测试发布证据和任务日志。

## 涉及文件

- 后端：app/services/dingtalk.py、app/services/dingtalk_company.py、app/api/v1/dingtalk.py、app/schemas/dingtalk.py。
- 前端：src/pages/OrganizationPage.vue、src/lib/organizationStructure.ts、src/lib/api.ts、src/styles.css。
- 验证：backend/tests/test_dingtalk_organization.py、scripts/test-organization-structure.mjs。
