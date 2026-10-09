export const assetStructureCategories = [
  { value: 1, mode: "entity", label: "公司主体", hint: "资产属于哪家公司", example: "营业执照上的公司或分公司", when: "已有公司直接选择；只有新增真实公司时才建档。" },
  { value: 2, mode: "identity", label: "登录与注册身份", hint: "用什么手机号或邮箱登录", example: "注册邮箱、手机号、用户名", when: "需要保管和追溯登录身份时登记；普通用户名不等于企业账号。" },
  { value: 3, mode: "platform", label: "服务平台", hint: "在哪里购买或使用", example: "阿里云、DeepSeek、协作软件平台", when: "已有平台直接关联；平台目录只记录服务平台本身。" },
  { value: 4, mode: "platform-account", label: "企业账号或工作区", hint: "平台上的哪个企业账号", example: "企业租户、商户号、主账号、工作区", when: "确有企业账号或工作区时登记；仅有邮箱或用户名时选登录身份。" },
  { value: 5, mode: "grant", label: "人员使用授权", hint: "谁可以使用哪个对象", example: "员工席位、子账号、资源使用权", when: "由有权限的人分配已获批的使用权；资产负责人在责任配置中维护。" },
  { value: 6, mode: "resource", label: "系统、订阅与资源", hint: "具体管理什么成果或服务", example: "自研系统、SaaS 订阅、API、云服务器", when: "日常登记通常从这里开始；平台和管理账号不知道时可以稍后关联。" },
] as const;
