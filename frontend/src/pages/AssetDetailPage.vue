<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import {
  Archive,
  ArrowLeft,
  CheckCircle2,
  CircleDot,
  Database,
  GitBranch,
  Layers3,
  Link2,
  Network,
  Plus,
  RotateCcw,
  Save,
  Server,
  ShieldCheck,
  Smartphone,
  Tags,
  UserRound,
  X,
} from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";

import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import {
  api,
  type Account,
  type Asset,
  type AssetAssignment,
  type AssetFieldDefinition,
  type AssetIdentifier,
  type AssetRelationshipView,
  type AssetType,
  type AuditLog,
  type Department,
  type InternalSystemProfile,
  type LegalEntity,
  type Person,
  type Platform,
  type PlatformAccountContext,
  type RelationOption,
  type RelationshipEdge,
  type RelationshipNode,
  type RelationshipSection,
  type ServiceInstance,
} from "../lib/api";
import { displayStatus } from "../lib/labels";
import { relationshipNodeHref } from "../lib/relationship";

type RelationDirection = "upstream" | "downstream" | "peer";
const route = useRoute();
const router = useRouter();
const id = String(route.params.id);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const message = ref("");
const tab = ref("overview");
const asset = ref<Asset | null>(null);
const types = ref<AssetType[]>([]);
const departments = ref<Department[]>([]);
const entities = ref<LegalEntity[]>([]);
const people = ref<Person[]>([]);
const allAssets = ref<Asset[]>([]);
const relationshipGraph = ref<AssetRelationshipView | null>(null);
const logs = ref<AuditLog[]>([]);
const profile = ref<InternalSystemProfile | null>(null);
const identifiers = ref<AssetIdentifier[]>([]);
const relationOptions = ref<RelationOption[]>([]);
const platformAccountContext = ref<PlatformAccountContext | null>(null);
const platforms = ref<Platform[]>([]);
const serviceInstances = ref<ServiceInstance[]>([]);
const childAccounts = ref<Account[]>([]);
const assignment = reactive<AssetAssignment>({
  owner_department_id: null,
  ownership_scope: "pending",
  responsible_person_id: null,
  user_person_ids: [],
});
const fieldDefinitions = ref<AssetFieldDefinition[]>([]);
const fieldValues = reactive<Record<string, string | number | null>>({});
const edit = reactive({
  name: "",
  status: "",
  criticality: "",
  confidentiality: "",
  expires_at: "",
  description: "",
});
const profileForm = reactive({
  repository_url: "",
  production_url: "",
  tech_stack: "",
  deployment_guide_url: "",
  recovery_guide_url: "",
  backup_description: "",
});
const relationForm = reactive<{
  direction: RelationDirection;
  related_asset_id: string;
  relation_type: string;
  note: string;
}>({
  direction: "upstream",
  related_asset_id: "",
  relation_type: "",
  note: "",
});
const editingRelationId = ref<string | null>(null);
const editingRelationTarget = ref("");
const identifierForm = reactive({
  namespace: "",
  identifier_type: "",
  identifier_value: "",
  is_primary: false,
  verification_status: "pending",
  confidentiality: "internal",
});
const childAccountForm = reactive({
  display_name: "",
  login_identifier: "",
  account_kind: "member_login",
  account_role: "member",
  account_type: "shared_business",
  login_method: "password_vault",
  mfa_status: "unknown",
  privilege_level: "normal",
  parent_account_id: "",
  note: "",
});

const personName = computed(() =>
  Object.fromEntries(people.value.map((item) => [item.id, item.display_name])),
);
const departmentName = computed(() =>
  Object.fromEntries(departments.value.map((item) => [item.id, item.name])),
);
const entityName = computed(() =>
  Object.fromEntries(entities.value.map((item) => [item.id, item.name])),
);
const assetById = computed(() =>
  Object.fromEntries(allAssets.value.map((item) => [item.id, item])),
);
const servicePlatform = computed(() => {
  const instance = serviceInstances.value.find((item) => item.asset_id === id);
  return instance?.purchase_platform_id
    ? platforms.value.find((item) => item.id === instance.purchase_platform_id) ?? null
    : null;
});
const linkedIdentity = computed(() => {
  const tenantIdentity = platformAccountContext.value?.registration_identities[0];
  if (tenantIdentity) return tenantIdentity.identifier;
  const identityEdge = relationshipGraph.value?.edges.find(
    (item) => item.section === "structure" && item.label === "注册身份",
  );
  return identityEdge
    ? relationshipGraph.value?.nodes.find((node) => node.id === identityEdge.source)
        ?.label ?? null
    : null;
});
const type = computed(() =>
  types.value.find((item) => item.id === asset.value?.asset_type_id),
);
const isPlatformTenant = computed(() => type.value?.code === "platform_tenant");
const l6CoreFieldKeys: Record<string, string[]> = {
  api_service: ["api_endpoint", "auth_method", "api_key"],
  saas_subscription: ["plan", "usage_purpose"],
  cloud_server: ["instance_id", "region"],
  email_service: ["service_domain"],
  vpn_network: ["vpn_endpoint", "usage_purpose"],
};
const isSupportedL6 = computed(
  () =>
    Boolean(
      type.value?.code &&
        (type.value.code in l6CoreFieldKeys || type.value.code === "internal_system"),
    ),
);
const coreFieldDefinitions = computed(() => {
  const keys = l6CoreFieldKeys[type.value?.code ?? ""] ?? [];
  return keys
    .map((key) => fieldDefinitions.value.find((field) => field.field_key === key))
    .filter((field): field is AssetFieldDefinition => Boolean(field));
});
const coreFieldValue = (field: AssetFieldDefinition) => {
  const value = fieldValues[field.id];
  return value === null || value === undefined || value === "" ? "待补充" : String(value);
};
const coreProfileFacts = computed(() => {
  if (type.value?.code !== "internal_system" || !profile.value) return [];
  return [
    { label: "生产访问地址", value: profile.value.production_url },
    { label: "代码仓库", value: profile.value.repository_url },
  ].filter((item): item is { label: string; value: string } => Boolean(item.value));
});
const groupedFields = computed(() =>
  Object.entries(
    fieldDefinitions.value.reduce<Record<string, AssetFieldDefinition[]>>(
      (groups, field) => {
        (groups[field.group_name] ??= []).push(field);
        return groups;
      },
      {},
    ),
  ),
);
const ownershipText = computed(() =>
  assignment.ownership_scope === "department"
    ? (departmentName.value[assignment.owner_department_id ?? ""] ?? "待选部门")
    : assignment.ownership_scope === "company"
      ? "公司级"
      : "待确认",
);
const responsibleDepartmentHint = computed(
  () =>
    people.value.find((item) => item.id === assignment.responsible_person_id)
      ?.department_id ?? null,
);
const completeness = computed(() => {
  if (platformAccountContext.value) {
    return Math.min(
      100,
      30 +
        15 +
        (platformAccountContext.value.registration_identities.length ? 15 : 0) +
        (assignment.responsible_person_id ? 15 : 0) +
        (assignment.ownership_scope !== "pending" ? 10 : 0) +
        (asset.value?.description ? 10 : 0) +
        (platformAccountContext.value.verification_status === "verified"
          ? 5
          : 0),
    );
  }
  const required = fieldDefinitions.value.filter((item) => item.is_required);
  const filled = required.filter(
    (item) =>
      fieldValues[item.id] !== null &&
      fieldValues[item.id] !== undefined &&
      fieldValues[item.id] !== "",
  ).length;
  return Math.min(
    100,
    45 +
      (assignment.ownership_scope !== "pending" ? 15 : 0) +
      (assignment.responsible_person_id ? 15 : 0) +
      (asset.value?.description ? 10 : 0) +
      (required.length ? Math.round((15 * filled) / required.length) : 15),
  );
});
const primaryIdentifier = computed(
  () =>
    identifiers.value.find((item) => item.namespace.startsWith("internal:"))
      ?.identifier_value ??
    asset.value?.asset_code ??
    "—",
);

const relationSections: RelationshipSection[] = [
  "structure",
  "business",
  "responsibility",
];
const relationGroups = computed<Record<RelationshipSection, RelationshipEdge[]>>(
  () => ({
    structure:
      relationshipGraph.value?.edges.filter((item) => item.section === "structure") ?? [],
    business:
      relationshipGraph.value?.edges.filter((item) => item.section === "business") ?? [],
    responsibility:
      relationshipGraph.value?.edges.filter(
        (item) => item.section === "responsibility",
      ) ?? [],
  }),
);
function relationSectionLabel(section: RelationshipSection) {
  return {
    structure: "关联结构",
    business: "业务关系",
    responsibility: "责任与使用",
  }[section];
}
function relationSectionDescription(section: RelationshipSection) {
  return {
    structure: "公司主体、注册身份和所属平台等结构性事实",
    business: "购买、开通、管理、部署、调用和包含等业务关系",
    responsibility: "负责人、使用人员、部门和账号授权",
  }[section];
}
function relationDirectionLabel(direction: RelationshipEdge["direction"]) {
  return {
    upstream: "上游",
    downstream: "下游",
    peer: "同级",
    responsibility: "责任 / 使用",
  }[direction];
}
function relationOtherNode(edge: RelationshipEdge) {
  const currentId = relationshipGraph.value?.current_node.id;
  const otherId = edge.source === currentId ? edge.target : edge.source;
  return relationshipGraph.value?.nodes.find((item) => item.id === otherId);
}
function startRelationEdit(edge: RelationshipEdge) {
  if (!edge.edit_kind) return;
  editingRelationId.value = edge.id;
  editingRelationTarget.value = edge.edit_target_id ?? "";
}
function cancelRelationEdit() {
  editingRelationId.value = null;
  editingRelationTarget.value = "";
}
function relationEditKind(edge: RelationshipEdge) {
  return edge.edit_kind;
}
function identityCandidates() {
  const identityType = types.value.find(
    (item) => item.code === "registration_identity",
  );
  return allAssets.value.filter(
    (item) =>
      !item.archived_at &&
      item.asset_type_id === identityType?.id &&
      item.legal_entity_id === asset.value?.legal_entity_id,
  );
}
async function saveRelationEdit(edge: RelationshipEdge) {
  const kind = relationEditKind(edge);
  if (!kind || !editingRelationTarget.value) return;
  try {
    relationshipGraph.value = await api.updateRelationshipLink(
      id,
      kind,
      editingRelationTarget.value,
    );
    cancelRelationEdit();
    message.value = "关联已更新";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "关联更新失败";
  }
}
const candidateAssets = computed(() => {
  const allowed = new Set(
    relationOptions.value
      .filter(
        (item) =>
          !relationForm.relation_type ||
          item.relation_type === relationForm.relation_type,
      )
      .flatMap((item) => item.target_type_codes),
  );
  return allAssets.value.filter(
    (item) =>
      item.id !== id &&
      !item.archived_at &&
      (!allowed.size ||
        allowed.has("*") ||
        allowed.has(
          types.value.find((type) => type.id === item.asset_type_id)?.code ??
            "",
        )),
  );
});
const relationshipSlots = computed(() => {
  const responsible = assignment.responsible_person_id
    ? personName.value[assignment.responsible_person_id]
    : null;
  return [
    {
      layer: "L1",
      label: "所属法人",
      value: asset.value?.legal_entity_id
        ? (entityName.value[asset.value.legal_entity_id] ?? "待确认")
        : "暂无法人归属证据",
      confirmed: Boolean(asset.value?.legal_entity_id),
    },
    {
      layer: "L3",
      label: "所属平台",
      value: platformAccountContext.value?.platform_name ?? servicePlatform.value?.name ?? "暂无明确平台关系",
      confirmed: Boolean(platformAccountContext.value ?? servicePlatform.value),
    },
    {
      layer: "L2",
      label: "注册身份",
      value: linkedIdentity.value ?? "暂无明确证据",
      confirmed: Boolean(linkedIdentity.value),
    },
    {
      layer: "L5",
      label: "责任 / 授权",
      value: responsible ?? "暂未登记",
      confirmed: Boolean(responsible),
    },
    {
      layer: "关系",
      label: "上下游实体",
      value: relationshipGraph.value?.edges.length
        ? `已建立 ${relationshipGraph.value.edges.length} 条关联`
        : "暂无明确关联",
      confirmed: Boolean(relationshipGraph.value?.edges.length),
    },
  ];
});
const confirmedRelationshipSlots = computed(() =>
  relationshipSlots.value.filter((slot) => slot.confirmed),
);

async function load() {
  loading.value = true;
  error.value = "";
  relationshipGraph.value = null;
  cancelRelationEdit();
  try {
    const item = await api.asset(id);
    const [
      typeRows,
      deptRows,
      entityRows,
      personRows,
      assetRows,
      assignmentRow,
      relationshipRows,
      auditRows,
      fieldRows,
      valueRows,
      identifierRows,
      platformRows,
      serviceInstanceRows,
    ] = await Promise.all([
      api.assetTypes(),
      api.departments(),
      api.legalEntities(),
      api.people(),
      api.assets({ include_archived: true }),
      api.assetAssignment(id),
      api.relationshipView(id),
      api.auditLogs(),
      api.assetFields(item.asset_type_id),
      api.assetFieldValues(id),
      api.assetIdentifiers(id),
      api.platforms(),
      api.serviceInstances(),
    ]);
    asset.value = item;
    types.value = typeRows;
    departments.value = deptRows;
    entities.value = entityRows;
    people.value = personRows;
    allAssets.value = assetRows.data;
    relationshipGraph.value = relationshipRows;
    logs.value = auditRows.filter((log) => log.object_id === id);
    identifiers.value = identifierRows;
    platforms.value = platformRows;
    serviceInstances.value = serviceInstanceRows;
    fieldDefinitions.value = fieldRows;
    Object.assign(assignment, assignmentRow);
    Object.assign(edit, {
      name: item.name,
      status: item.status,
      criticality: item.criticality,
      confidentiality: item.confidentiality,
      expires_at: item.expires_at ?? "",
      description: item.description ?? "",
    });
    valueRows.forEach((row) => {
      fieldValues[row.field_definition_id] = row.value.value as
        string | number | null;
    });
    const currentType = typeRows.find((row) => row.id === item.asset_type_id);
    if (currentType?.profile_kind === "internal_system") {
      profile.value = await api.internalProfile(id);
      if (profile.value)
        Object.assign(
          profileForm,
          Object.fromEntries(
            Object.entries(profile.value).map(([key, value]) => [
              key,
              value ?? "",
            ]),
          ),
        );
    }
    if (currentType?.code === "platform_tenant")
      platformAccountContext.value = await api.platformAccountContext(id);
    childAccounts.value = currentType?.code === "platform_tenant"
      ? await api.platformAccountChildren(id)
      : [];
    const requestedTab = String(route.query.tab ?? "");
    if (
      [
        "overview",
        "profile",
        "responsibility",
        "accounts",
        "relations",
        "history",
        ...(currentType?.code === "platform_tenant" ? ["accounts"] : []),
      ].includes(requestedTab)
    )
      tab.value = requestedTab;
    await loadRelationOptions();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "资产加载失败";
  } finally {
    loading.value = false;
  }
}
async function loadRelationOptions() {
  relationOptions.value = await api.relationOptions(id, relationForm.direction);
  if (
    !relationOptions.value.some(
      (item) => item.relation_type === relationForm.relation_type,
    )
  )
    relationForm.relation_type = relationOptions.value[0]?.relation_type ?? "";
  relationForm.related_asset_id = "";
}
async function saveAsset() {
  if (!asset.value) return;
  saving.value = true;
  try {
    asset.value = await api.updateAsset(id, {
      ...edit,
      expires_at: edit.expires_at || null,
      version: asset.value.version,
    });
    message.value = "概览资料已保存";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "保存失败";
  } finally {
    saving.value = false;
  }
}
async function saveChildAccount() {
  if (!childAccountForm.display_name || !childAccountForm.login_identifier) return;
  saving.value = true;
  try {
    await api.createPlatformAccountChild(id, {
      ...childAccountForm,
      parent_account_id: childAccountForm.parent_account_id || null,
      note: childAccountForm.note || null,
    });
    childAccounts.value = await api.platformAccountChildren(id);
    Object.assign(childAccountForm, {
      display_name: "",
      login_identifier: "",
      account_kind: "member_login",
      account_role: "member",
      account_type: "shared_business",
      login_method: "password_vault",
      mfa_status: "unknown",
      privilege_level: "normal",
      parent_account_id: "",
      note: "",
    });
    message.value = "账号明细已添加到当前公司平台账号";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "账号明细保存失败";
  } finally {
    saving.value = false;
  }
}
async function saveAssignment() {
  if (!asset.value || !assignment.responsible_person_id) return;
  saving.value = true;
  try {
    Object.assign(
      assignment,
      await api.saveAssetAssignment(id, {
        version: asset.value.version,
        owner_department_id:
          assignment.ownership_scope === "department"
            ? assignment.owner_department_id
            : null,
        ownership_scope: assignment.ownership_scope,
        responsible_person_id: assignment.responsible_person_id,
        user_person_ids: assignment.user_person_ids,
      }),
    );
    asset.value = await api.asset(id);
    message.value = "责任配置已保存";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "保存失败";
  } finally {
    saving.value = false;
  }
}
async function saveCustomFields() {
  saving.value = true;
  try {
    await api.saveAssetFieldValues(
      id,
      fieldDefinitions.value.map((field) => ({
        field_definition_id: field.id,
        value: fieldValues[field.id] ?? null,
      })),
    );
    message.value = "专属资料已保存";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "保存失败";
  } finally {
    saving.value = false;
  }
}
async function saveProfile() {
  saving.value = true;
  try {
    profile.value = await api.saveInternalProfile(id, profileForm);
    message.value = "接管资料已保存";
  } finally {
    saving.value = false;
  }
}
async function saveIdentifier() {
  if (
    !identifierForm.namespace ||
    !identifierForm.identifier_type ||
    !identifierForm.identifier_value
  )
    return;
  try {
    identifiers.value = [
      ...identifiers.value,
      await api.createAssetIdentifier(id, identifierForm),
    ];
    Object.assign(identifierForm, {
      namespace: "",
      identifier_type: "",
      identifier_value: "",
      is_primary: false,
      verification_status: "pending",
      confidentiality: "internal",
    });
    message.value = "标识已添加";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "标识已存在";
  }
}
async function addRelation() {
  if (!relationForm.related_asset_id || !relationForm.relation_type) return;
  try {
    await api.createIntelligentRelation(id, relationForm);
    relationshipGraph.value = await api.relationshipView(id);
    relationForm.related_asset_id = "";
    relationForm.note = "";
    message.value = "关联已建立";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "建立失败";
  }
}
async function removeRelation(item: RelationshipEdge) {
  if (!item.relation_id || !item.editable) return;
  try {
    await api.archiveRelation(id, item.relation_id);
    relationshipGraph.value = await api.relationshipView(id);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "无法删除关联";
  }
}
async function toggleArchive() {
  if (!asset.value) return;
  asset.value = asset.value.archived_at
    ? await api.restoreAsset(id, asset.value.version)
    : await api.archiveAsset(id, asset.value.version);
}
function fieldInputType(field: AssetFieldDefinition) {
  return field.data_type === "number"
    ? "number"
    : field.data_type === "date"
      ? "date"
      : "text";
}
function groupLabel(direction: RelationDirection) {
  return { upstream: "上游来源", downstream: "下游使用方", peer: "同级关系" }[
    direction
  ];
}
watch(
  () => relationForm.direction,
  () => {
    void loadRelationOptions();
  },
);
watch(
  () => assignment.responsible_person_id,
  (personId) => {
    const person = people.value.find((item) => item.id === personId);
    if (assignment.ownership_scope === "pending" && person?.department_id) {
      assignment.ownership_scope = "department";
      assignment.owner_department_id = person.department_id;
    }
  },
);
watch(
  () => assignment.ownership_scope,
  (scope) => {
    if (scope !== "department") assignment.owner_department_id = null;
  },
);
onMounted(load);
</script>

<template>
  <div class="page-stack detail-page-v2">
    <button class="back-link" @click="router.push('/assets')">
      <ArrowLeft :size="16" />返回资产中心
    </button>
    <PageHeader
      :eyebrow="primaryIdentifier"
      :title="asset?.name ?? '资产详情'"
      :description="type?.name ?? '统一资产资料'"
    >
      <StatusBadge :tone="asset?.archived_at ? 'default' : 'success'">{{
        asset?.archived_at ? "已归档" : displayStatus(asset?.status ?? "")
      }}</StatusBadge
      ><button v-if="asset" class="secondary-button" @click="toggleArchive">
        <component :is="asset.archived_at ? RotateCcw : Archive" :size="16" />{{
          asset.archived_at ? "恢复" : "归档"
        }}
      </button>
    </PageHeader>
    <div v-if="message" class="message-panel success-message">
      {{ message }}
    </div>
    <div v-if="error" class="message-panel error-message">{{ error }}</div>
    <div v-if="loading" class="loading-state">正在加载资产资料…</div>
    <template v-else-if="asset">
      <section class="asset-hero-grid">
        <article class="asset-code-card">
          <span>资产编号</span><strong>{{ primaryIdentifier }}</strong
          ><small>简单、固定，用于日常沟通和查找</small>
        </article>
        <article>
          <span>归属范围</span><strong>{{ ownershipText }}</strong
          ><small>{{
            assignment.owner_department_id
              ? departmentName[assignment.owner_department_id]
              : "未绑定具体部门"
          }}</small>
        </article>
        <article>
          <span>负责人</span
          ><strong>{{
            assignment.responsible_person_id
              ? personName[assignment.responsible_person_id]
              : "待配置"
          }}</strong
          ><small>{{ assignment.user_person_ids.length }} 位协同使用人</small>
        </article>
        <article class="completion-card">
          <span>登记状态</span><strong>已建档</strong
          ><small>完整资料可按需补充</small>
        </article>
      </section>
      <section class="relationship-position">
        <header>
          <div>
            <span class="section-kicker">关联摘要</span>
            <h2>已建立的关系优先展示</h2>
            <p>没有关系时不生成补位对象，可在“关联关系”中继续添加。</p>
          </div>
          <Network :size="26" />
        </header>
        <div>
          <article
            v-for="slot in confirmedRelationshipSlots"
            :key="slot.label"
            :class="{ confirmed: slot.confirmed }"
          >
            <span>{{ slot.layer }}</span
            ><small>{{ slot.label }}</small
            ><strong>{{ slot.value }}</strong>
          </article>
          <div v-if="!confirmedRelationshipSlots.length" class="relationship-summary-empty">暂未建立明确关系</div>
        </div>
      </section>
      <nav class="asset-detail-tabs">
        <button
          v-for="item in [
            ['overview', '概览'],
            ['relations', '关联关系'],
            ['responsibility', '责任与使用'],
            ['profile', '补充资料'],
            ['history', '证据与历史'],
          ]"
          :key="item[0]"
          :class="{ active: tab === item[0] }"
          @click="tab = item[0]"
        >
          {{ item[1] }}
        </button>
        <button
          v-if="isPlatformTenant"
          :class="{ active: tab === 'accounts' }"
          @click="tab = 'accounts'"
        >
          账号与席位 {{ childAccounts.length }}
        </button>
      </nav>

      <section
        v-if="tab === 'overview'"
        class="detail-surface overview-surface"
      >
        <header>
          <div>
            <span class="section-kicker">资产概览</span>
            <h2>让名称回归名称，让编号负责区分</h2>
            <p>默认只处理核心事实；治理字段和历史标识按需展开。</p>
          </div>
          <Server :size="30" />
        </header>
        <div class="overview-context">
          <div>
            <span>简短编号</span><strong>{{ primaryIdentifier }}</strong>
          </div>
          <div>
            <span>资产类型</span><strong>{{ type?.name }}</strong>
          </div>
        </div>
        <section v-if="isSupportedL6" class="l6-core-facts">
          <header>
            <div>
              <span class="section-kicker">当前类型核心资料</span>
              <h3>先看能不能用，再补完整档案</h3>
              <p>只展示当前类型最重要的信息；其他字段在“补充资料”中维护。</p>
            </div>
          </header>
          <div class="l6-core-fact-grid">
            <article v-for="field in coreFieldDefinitions" :key="field.id">
              <span>{{ field.label }}</span>
              <strong>{{ coreFieldValue(field) }}</strong>
            </article>
            <article v-for="fact in coreProfileFacts" :key="fact.label">
              <span>{{ fact.label }}</span>
              <strong>{{ fact.value }}</strong>
            </article>
            <article v-if="!coreFieldDefinitions.length && !coreProfileFacts.length">
              <span>核心资料</span><strong>待补充</strong>
            </article>
          </div>
        </section>
        <section v-if="platformAccountContext" class="core-linkage-panel">
          <header>
            <div>
              <span class="section-kicker">登记时已自动联动</span>
              <h3>平台账号核心资料</h3>
              <p>这里直接读取登记时写入的对象表，不需要在其他页签重复填写。</p>
            </div>
            <CheckCircle2 :size="25" />
          </header>
          <div>
            <article>
              <Layers3 :size="19" /><span>所属平台</span
              ><strong>{{ platformAccountContext.platform_name }}</strong
              ><small>{{ platformAccountContext.platform_category }}</small>
            </article>
            <article>
              <Smartphone :size="19" /><span>主要注册身份</span
              ><strong>{{
                platformAccountContext.registration_identities[0]?.identifier ||
                "暂不清楚"
              }}</strong
              ><small>{{
                platformAccountContext.registration_identities[0]?.asset_code ||
                "可稍后补充"
              }}</small>
            </article>
            <article>
              <Tags :size="19" /><span>平台原生标识</span
              ><strong>{{
                platformAccountContext.tenant_identifier ||
                "平台未提供 / 暂未填写"
              }}</strong
              ><small>{{
                platformAccountContext.external_identifier_type || "可选字段"
              }}</small>
            </article>
            <article>
              <UserRound :size="19" /><span>登记人与负责人</span
              ><strong>{{
                assignment.responsible_person_id
                  ? personName[assignment.responsible_person_id]
                  : "待确认"
              }}</strong
              ><small
                >登记人：{{
                  asset.created_by_person_id
                    ? personName[asset.created_by_person_id] || "已记录"
                    : "系统登记"
                }}</small
              >
            </article>
          </div>
        </section>
        <form class="balanced-form" @submit.prevent="saveAsset">
          <label class="wide"
            ><span>资产名称</span><input v-model="edit.name" required /></label
          ><details class="asset-governance-details wide">
            <summary>
              <span class="governance-toggle-title">
                <ShieldCheck :size="20" />
                <span>
                  <b>还有可选的治理资料</b>
                  <small>状态、重要程度、保密、到期、用途</small>
                </span>
              </span>
              <span class="governance-toggle-action">展开补充 <Plus :size="16" /></span>
            </summary>
            <div class="governance-grid">
              <label
                ><span>当前状态</span
                ><select v-model="edit.status">
                  <option value="draft">草稿</option>
                  <option value="active">在用</option>
                  <option value="pending_handover">待接管</option>
                  <option value="paused">暂停</option>
                  <option value="retired">停用</option>
                </select></label
              ><label
                ><span>重要程度</span
                ><select v-model="edit.criticality">
                  <option value="normal">普通</option>
                  <option value="important">重要</option>
                  <option value="critical">关键</option>
                </select></label
              ><label
                ><span>保密级别</span
                ><select v-model="edit.confidentiality">
                  <option value="public">公开</option>
                  <option value="internal">内部</option>
                  <option value="sensitive">敏感</option>
                  <option value="restricted">严格受限</option>
                </select></label
              ><label
                ><span>到期日期</span
                ><input v-model="edit.expires_at" type="date" /></label
              ><label class="wide"
                ><span>用途与说明</span
                ><textarea v-model="edit.description" rows="4" />
              </label>
            </div>
          </details>
          <div class="form-actions wide">
            <button class="primary-button" :disabled="saving">
              <Save :size="16" />保存核心资料
            </button>
          </div>
        </form>
        <section class="identifier-panel">
          <div>
            <h3><Tags :size="18" />平台与历史标识</h3>
            <p>没有平台原生 ID 可以留空；历史编号只保留用于追溯。</p>
          </div>
          <div class="identifier-chips">
            <span
              v-for="item in identifiers"
              :key="item.id"
              :class="{ primary: item.namespace.startsWith('internal:') }"
              ><small>{{
                item.namespace.startsWith("internal:")
                  ? "资产编号"
                  : item.identifier_type
              }}</small
              ><b>{{ item.identifier_value }}</b></span
            >
          </div>
          <form class="identifier-form-v2" @submit.prevent="saveIdentifier">
            <input
              v-model="identifierForm.namespace"
              placeholder="平台名称，例如：阿里云"
            /><input
              v-model="identifierForm.identifier_type"
              placeholder="标识类型，例如：实例 ID"
            /><input
              v-model="identifierForm.identifier_value"
              placeholder="对应的编号"
            /><button class="secondary-button"><Plus :size="15" />添加</button>
          </form>
        </section>
      </section>

      <section v-if="tab === 'accounts' && isPlatformTenant" class="detail-surface profile-surface">
        <header>
          <div>
            <span class="section-kicker">L4 下的账号明细</span>
            <h2>账号与席位，不是新的资产层级</h2>
            <p>这里记录管理员、子账号和开发账号；不填写密码，也不会因账号自动创建 L6 服务。</p>
          </div>
          <StatusBadge tone="default">{{ childAccounts.length }} 个账号</StatusBadge>
        </header>
        <div v-if="childAccounts.length" class="account-detail-grid">
          <article v-for="item in childAccounts" :key="item.id" class="account-detail-card">
            <UserRound :size="19" />
            <div>
              <strong>{{ item.login_identifier }}</strong>
              <small>{{ item.account_role === 'admin' ? '管理员账号' : item.account_kind === 'developer' ? '开发账号' : '登录账号 / 席位' }}</small>
            </div>
            <StatusBadge :tone="item.privilege_level === 'admin' || item.privilege_level === 'root' ? 'warning' : 'default'">{{ item.privilege_level }}</StatusBadge>
          </article>
        </div>
        <div v-else class="mini-empty">尚未登记账号明细。确认公司平台账号后，再将原始资料中的登录账号添加到这里。</div>
        <form class="balanced-form account-detail-form" @submit.prevent="saveChildAccount">
          <label><span>账号名称 *</span><input v-model="childAccountForm.display_name" required placeholder="例如：法务账号 / 开发账号 A" /></label>
          <label><span>登录标识 *</span><input v-model="childAccountForm.login_identifier" required placeholder="邮箱、手机号或用户名；不填写密码" /></label>
          <label><span>账号用途</span><select v-model="childAccountForm.account_kind"><option value="member_login">普通登录账号</option><option value="developer">开发账号</option><option value="admin">管理员账号</option><option value="service">服务账号</option></select></label>
          <label><span>权限级别</span><select v-model="childAccountForm.privilege_level"><option value="normal">普通</option><option value="admin">管理员</option><option value="root">根权限</option></select></label>
          <details class="asset-governance-details wide"><summary><span class="governance-toggle-title"><ShieldCheck :size="20" /><span><b>可选的账号说明</b><small>上级账号、MFA、来源说明</small></span></span><span class="governance-toggle-action">展开补充 <Plus :size="16" /></span></summary><div class="governance-grid"><label><span>上级账号</span><select v-model="childAccountForm.parent_account_id"><option value="">无 / 直属企业账号</option><option v-for="item in childAccounts" :key="item.id" :value="item.id">{{ item.login_identifier }}</option></select></label><label><span>MFA 状态</span><select v-model="childAccountForm.mfa_status"><option value="unknown">未知</option><option value="enabled">已开启</option><option value="disabled">未开启</option></select></label><label class="wide"><span>来源说明</span><textarea v-model="childAccountForm.note" rows="3" placeholder="例如：来源于账号资料；密码仅保存在密码库。" /></label></div></details>
          <div class="form-actions wide"><button class="primary-button" :disabled="saving"><Plus :size="16" />添加账号明细</button></div>
        </form>
      </section>

      <section v-if="tab === 'profile'" class="detail-surface profile-surface">
        <header>
          <div>
            <span class="section-kicker">专属资料</span>
            <h2>按类型填写，不用记复杂字段</h2>
            <p>每张彩色卡片对应一组业务信息；标注提示告诉你该填什么。</p>
          </div>
          <StatusBadge :tone="completeness >= 80 ? 'success' : 'warning'">{{
            completeness >= 80 ? "资料较完整" : "仍有待补充项"
          }}</StatusBadge>
        </header>
        <form
          v-if="fieldDefinitions.length"
          class="profile-card-grid"
          @submit.prevent="saveCustomFields"
        >
          <section
            v-for="[group, fields] in groupedFields"
            :key="group"
            class="field-group-card"
          >
            <div class="group-title">
              <CircleDot :size="18" />
              <div>
                <h3>{{ group }}</h3>
                <small>{{ fields.length }} 项信息</small>
              </div>
            </div>
            <div class="group-fields">
              <label v-for="field in fields" :key="field.id"
                ><span>{{ field.label }}<b v-if="field.is_required">*</b></span
                ><select
                  v-if="field.options?.length"
                  v-model="fieldValues[field.id]"
                >
                  <option :value="null">请选择</option>
                  <option
                    v-for="option in field.options"
                    :key="String(option)"
                    :value="option"
                  >
                    {{ option }}
                  </option></select
                ><textarea
                  v-else-if="field.data_type === 'textarea'"
                  v-model="fieldValues[field.id]"
                  rows="3"
                /><input
                  v-else-if="field.data_type === 'boolean'"
                  v-model="fieldValues[field.id]"
                  type="checkbox"
                /><input
                  v-else
                  v-model="fieldValues[field.id]"
                  :type="fieldInputType(field)"
                /><small v-if="field.help_text || field.unit"
                  >{{ field.help_text
                  }}{{ field.unit ? `（${field.unit}）` : "" }}</small
                ></label
              >
            </div>
          </section>
          <div class="profile-save">
            <button class="primary-button" :disabled="saving">
              <Save :size="16" />保存专属资料
            </button>
          </div>
        </form>
        <div v-else class="large-empty-panel">
          <CheckCircle2 :size="28" /><strong>该类型还没有专属字段模板</strong>
          <p>管理员可在“分类与规则”中添加，不需要改代码。</p>
        </div>
        <section
          v-if="type?.profile_kind === 'internal_system'"
          class="system-handover"
        >
          <div>
            <h3><ShieldCheck :size="19" />自研系统接管资料</h3>
            <p>固定接管信息和上方专属字段分开维护。</p>
          </div>
          <form class="balanced-form" @submit.prevent="saveProfile">
            <label
              ><span>代码仓库地址</span
              ><input v-model="profileForm.repository_url" /></label
            ><label
              ><span>生产访问地址</span
              ><input v-model="profileForm.production_url" /></label
            ><label class="wide"
              ><span>技术栈</span
              ><input v-model="profileForm.tech_stack" /></label
            ><label
              ><span>部署说明地址</span
              ><input v-model="profileForm.deployment_guide_url" /></label
            ><label
              ><span>恢复说明地址</span
              ><input v-model="profileForm.recovery_guide_url" /></label
            ><label class="wide"
              ><span>备份方式</span
              ><textarea v-model="profileForm.backup_description" rows="3" />
            </label>
            <div class="form-actions wide">
              <button class="secondary-button">
                <ShieldCheck :size="16" />保存接管资料
              </button>
            </div>
          </form>
        </section>
      </section>

      <section
        v-if="tab === 'responsibility'"
        class="detail-surface responsibility-surface"
      >
        <header>
          <div>
            <span class="section-kicker">责任人员</span>
            <h2>先确定归属，再安排负责人和协同人</h2>
            <p>负责人部门只作智能建议；不会悄悄覆盖已经确认的归属。</p>
          </div>
          <UserRound :size="30" />
        </header>
        <form
          class="balanced-form responsibility-form"
          @submit.prevent="saveAssignment"
        >
          <label
            ><span>归属范围</span
            ><select v-model="assignment.ownership_scope">
              <option value="pending">待确认</option>
              <option value="company">公司级</option>
              <option value="department">部门级</option>
            </select></label
          ><label v-if="assignment.ownership_scope === 'department'"
            ><span>归属部门</span
            ><select v-model="assignment.owner_department_id" required>
              <option :value="null" disabled>选择部门</option>
              <option
                v-for="item in departments"
                :key="item.id"
                :value="item.id"
              >
                {{ item.name }}
              </option>
            </select></label
          >
          <div v-else class="ownership-note">
            {{
              assignment.ownership_scope === "company"
                ? "公司级资产不归属具体部门，由资产管理员统一治理。"
                : "请确认该资产应归公司级还是部门级。"
            }}
          </div>
          <label class="wide"
            ><span>负责人</span
            ><select v-model="assignment.responsible_person_id" required>
              <option :value="null" disabled>选择一名负责人</option>
              <option v-for="item in people" :key="item.id" :value="item.id">
                {{ item.display_name
                }}{{
                  item.department_id
                    ? ` · ${departmentName[item.department_id] ?? ""}`
                    : ""
                }}
              </option></select
            ><small v-if="responsibleDepartmentHint"
              >负责人主部门：{{
                departmentName[responsibleDepartmentHint]
              }}；仅在归属待确认时用于建议。</small
            ></label
          ><label class="wide"
            ><span>协同使用人员</span
            ><select v-model="assignment.user_person_ids" multiple size="7">
              <option
                v-for="item in people.filter(
                  (row) => row.id !== assignment.responsible_person_id,
                )"
                :key="item.id"
                :value="item.id"
              >
                {{ item.display_name }}
              </option></select
            ><small
              >负责人默认已拥有管理和使用权限，无需重复选择。</small
            ></label
          >
          <div class="form-actions wide">
            <button
              class="primary-button"
              :disabled="saving || !assignment.responsible_person_id"
            >
              <UserRound :size="16" />确认责任配置
            </button>
          </div>
        </form>
      </section>

      <section
        v-if="tab === 'relations'"
        class="detail-surface relations-surface"
      >
        <header>
          <div>
            <span class="section-kicker">关联资产</span>
            <h2>像搭积木一样建立清晰关系</h2>
            <p>
              先选“我和谁的关系”，系统只提供符合层级的对象，不再出现一整页无关选项。
            </p>
          </div>
          <Network :size="30" />
        </header>
        <div class="relation-studio">
          <aside>
            <span>当前资产</span><strong>{{ asset.name }}</strong
            ><small>{{ primaryIdentifier }} · {{ type?.name }}</small
            ><i />
          </aside>
          <form @submit.prevent="addRelation">
            <div class="direction-picker">
              <button
                v-for="direction in [
                  'upstream',
                  'downstream',
                  'peer',
                ] as RelationDirection[]"
                :key="direction"
                type="button"
                :class="{ active: relationForm.direction === direction }"
                @click="relationForm.direction = direction"
              >
                {{ groupLabel(direction) }}
              </button>
            </div>
            <div class="relation-input-grid">
              <label
                ><span>关系</span
                ><select v-model="relationForm.relation_type" required>
                  <option
                    v-for="item in relationOptions"
                    :key="item.relation_type"
                    :value="item.relation_type"
                  >
                    {{ item.label }}
                  </option>
                  <option v-if="!relationOptions.length" value="">
                    暂无可用关系
                  </option>
                </select></label
              ><label
                ><span>目标资产</span
                ><select v-model="relationForm.related_asset_id" required>
                  <option value="" disabled>选择兼容的目标资产</option>
                  <option
                    v-for="item in candidateAssets"
                    :key="item.id"
                    :value="item.id"
                  >
                    {{ item.name }} · {{ item.asset_code }}
                  </option>
                </select></label
              ><label
                ><span>备注（可选）</span
                ><input
                  v-model="relationForm.note"
                  placeholder="例如生产环境主实例" /></label
              ><button
                class="primary-button"
                :disabled="!relationOptions.length"
              >
                <Plus :size="16" />建立关系
              </button>
            </div>
          </form>
        </div>
        <div class="relation-lanes">
          <section
            v-for="section in relationSections"
            :key="section"
            :class="section"
          >
            <header>
              <span>{{ String(relationSections.indexOf(section) + 1).padStart(2, "0") }}</span>
              <div>
                <h3>{{ relationSectionLabel(section) }}</h3>
                <p>{{ relationSectionDescription(section) }}</p>
              </div>
            </header>
            <div class="relation-card-list">
              <RouterLink
                v-for="item in relationGroups[section]"
                :key="item.id"
                :to="relationshipNodeHref(relationOtherNode(item) as RelationshipNode | undefined)"
                class="relation-card"
                ><GitBranch :size="17" />
                <div>
                  <small>{{ item.label }} · {{ relationDirectionLabel(item.direction) }}</small
                  ><strong>{{ relationOtherNode(item)?.label ?? "关联对象" }}</strong
                  ><span>{{ relationOtherNode(item)?.object_type ?? "" }} · 来源 {{ item.source_model }}</span>
                  <div
                    v-if="editingRelationId === item.id"
                    class="relation-inline-edit"
                    @click.prevent.stop
                  >
                    <select v-model="editingRelationTarget">
                      <option value="" disabled>选择新的关联对象</option>
                      <template v-if="item.edit_kind === 'platform'">
                        <option v-for="candidate in platforms" :key="candidate.id" :value="candidate.id">
                          {{ candidate.name }}
                        </option>
                      </template>
                      <template v-else-if="item.edit_kind === 'registration_identity'">
                        <option v-for="candidate in identityCandidates()" :key="candidate.id" :value="candidate.id">
                          {{ candidate.name }}
                        </option>
                      </template>
                      <template v-else-if="item.edit_kind === 'legal_entity'">
                        <option v-for="candidate in entities" :key="candidate.id" :value="candidate.id">
                          {{ candidate.name }}
                        </option>
                      </template>
                    </select>
                    <span>
                      <button class="primary-button compact-button" @click.prevent.stop="saveRelationEdit(item)">保存</button>
                      <button class="secondary-button compact-button" @click.prevent.stop="cancelRelationEdit">取消</button>
                    </span>
                  </div>
                </div>
                <button
                  v-if="item.editable && editingRelationId !== item.id"
                  class="icon-button"
                  @click.prevent.stop="item.edit_kind ? startRelationEdit(item) : removeRelation(item)"
                >
                  <span v-if="item.edit_kind">调整</span><X v-else :size="15" /></button
              ></RouterLink>
              <div
                v-if="!relationGroups[section].length"
                class="relation-empty"
              >
                <Database :size="18" />暂无{{ relationSectionLabel(section) }}
              </div>
            </div>
          </section>
        </div>
      </section>

      <section v-if="tab === 'history'" class="detail-surface history-surface">
        <header>
          <div>
            <span class="section-kicker">变更历史</span>
            <h2>所有关键调整都有记录</h2>
            <p>包含归属、负责人、关系和资料变更。</p>
          </div>
        </header>
        <div class="timeline-v2">
          <article v-for="item in logs" :key="item.id">
            <i />
            <div>
              <strong>{{ item.action }}</strong
              ><span>{{
                new Date(item.created_at).toLocaleString("zh-CN")
              }}</span
              ><code>{{ item.after_data }}</code>
            </div>
          </article>
          <div v-if="!logs.length" class="large-empty-panel">暂无审计记录</div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.detail-page-v2 {
  gap: 18px;
}
.asset-hero-grid {
  display: grid;
  grid-template-columns: 1.25fr repeat(3, 1fr);
  gap: 13px;
}
.asset-hero-grid article {
  min-height: 116px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
  box-shadow: var(--shadow);
}
.asset-hero-grid article:nth-child(2) {
  background: linear-gradient(135deg, #eff6ff, var(--surface));
}
.asset-hero-grid article:nth-child(3) {
  background: linear-gradient(135deg, #f4efff, var(--surface));
}
.asset-hero-grid .completion-card {
  background: linear-gradient(135deg, #ecfbf4, var(--surface));
}
.asset-hero-grid span,
.asset-hero-grid strong,
.asset-hero-grid small {
  display: block;
}
.asset-hero-grid span {
  color: var(--muted);
  font-size: 10px;
  font-weight: 800;
}
.asset-hero-grid strong {
  margin-top: 14px;
  font-size: 18px;
}
.asset-hero-grid small {
  margin-top: 5px;
  color: var(--muted);
  font-size: 10px;
}
.asset-code-card strong {
  color: var(--primary);
  font-size: 23px;
  letter-spacing: 0.02em;
}
.relationship-position {
  padding: 20px;
  border: 1px solid color-mix(in srgb, var(--primary) 22%, var(--border));
  border-radius: 15px;
  background: linear-gradient(135deg, #f7fbff, var(--surface));
}
.relationship-position > header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}
.relationship-position h2 {
  margin: 5px 0;
  font-size: 17px;
}
.relationship-position p {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
}
.relationship-position > header > svg {
  padding: 8px;
  color: var(--primary);
  background: color-mix(in srgb, var(--primary) 9%, var(--surface));
  border-radius: 10px;
}
.relationship-position > div {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 9px;
}
.relationship-position article {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 12px;
  border: 1px dashed var(--border);
  border-radius: 10px;
  background: var(--surface);
}
.relationship-position article.confirmed {
  border-style: solid;
  border-color: color-mix(in srgb, var(--success) 45%, var(--border));
}
.relationship-position article > span {
  color: var(--primary);
  font-size: 9px;
  font-weight: 900;
}
.relationship-position small {
  color: var(--muted);
  font-size: 10px;
}
.relationship-position strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
}
.relationship-summary-empty {
  grid-column: 1 / -1;
  padding: 18px;
  border: 1px dashed var(--border);
  border-radius: 12px;
  color: var(--muted);
  text-align: center;
}
.asset-detail-tabs {
  display: flex;
  gap: 5px;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
}
.asset-detail-tabs button {
  padding: 10px 16px;
  border: 0;
  border-radius: 8px;
  color: var(--muted);
  background: transparent;
  cursor: pointer;
  font-size: 12px;
}
.asset-detail-tabs button.active {
  color: var(--primary);
  background: color-mix(in srgb, var(--primary) 10%, var(--surface));
  font-weight: 800;
}
.detail-surface {
  padding: 26px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--surface);
  box-shadow: var(--shadow);
}
.detail-surface > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 22px;
}
.detail-surface > header > svg {
  padding: 9px;
  border-radius: 11px;
  color: var(--primary);
  background: color-mix(in srgb, var(--primary) 10%, var(--surface));
}
.section-kicker {
  color: var(--primary);
  font-size: 10px;
  font-weight: 900;
  letter-spacing: 0.12em;
}
.detail-surface h2 {
  margin: 6px 0;
  font-size: 21px;
}
.detail-surface h3 {
  margin: 0;
}
.detail-surface p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}
.overview-context {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 18px;
}
.overview-context div {
  padding: 13px;
  border-radius: 10px;
  background: var(--surface-soft);
}
.overview-context span,
.overview-context strong {
  display: block;
}
.overview-context span {
  color: var(--muted);
  font-size: 10px;
}
.overview-context strong {
  margin-top: 6px;
  font-size: 13px;
}
.l6-core-facts {
  margin-top: 18px;
  padding: 18px;
  border: 1px solid color-mix(in srgb, var(--primary) 24%, var(--border));
  border-radius: 14px;
  background: color-mix(in srgb, var(--primary) 3%, var(--surface));
}
.l6-core-facts header {
  margin-bottom: 14px;
}
.l6-core-facts h3 {
  margin: 5px 0;
  font-size: 16px;
}
.l6-core-facts p {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
}
.l6-core-fact-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.l6-core-fact-grid article {
  min-width: 0;
  padding: 13px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
}
.l6-core-fact-grid span,
.l6-core-fact-grid strong {
  display: block;
}
.l6-core-fact-grid span {
  color: var(--muted);
  font-size: 10px;
}
.l6-core-fact-grid strong {
  margin-top: 5px;
  overflow: hidden;
  color: var(--ink);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.balanced-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.balanced-form label {
  display: grid;
  gap: 7px;
}
.balanced-form label > span,
.relation-input-grid label > span {
  color: var(--muted);
  font-size: 10px;
  font-weight: 800;
}
.balanced-form input,
.balanced-form select,
.balanced-form textarea,
.identifier-form-v2 input,
.relation-input-grid input,
.relation-input-grid select {
  width: 100%;
  min-height: 42px;
  padding: 9px 11px;
}
.balanced-form .wide {
  grid-column: span 2;
}
.asset-governance-details {
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--primary) 45%, var(--border));
  border-radius: 14px;
  background: linear-gradient(135deg, #eef6ff, var(--surface));
  box-shadow: 0 8px 20px rgba(28, 102, 207, 0.08);
}
.asset-governance-details summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 68px;
  padding: 10px 17px;
  cursor: pointer;
  color: var(--text);
  list-style: none;
}
.asset-governance-details summary::-webkit-details-marker {
  display: none;
}
.asset-governance-details[open] summary {
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}
.governance-toggle-title {
  display: flex;
  align-items: center;
  gap: 11px;
  color: var(--primary);
}
.governance-toggle-title > span {
  display: grid;
  gap: 3px;
}
.governance-toggle-title b {
  color: var(--text);
  font-size: 14px;
}
.governance-toggle-title small {
  color: var(--muted);
  font-size: 10px;
  font-weight: 500;
}
.governance-toggle-action {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: auto;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--primary);
  color: #fff;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}
.asset-governance-details[open] .governance-toggle-action {
  background: var(--surface-soft);
  color: var(--primary);
}
.asset-governance-details[open] .governance-toggle-action svg {
  transform: rotate(45deg);
}
.governance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  padding: 16px;
}
.governance-grid label {
  display: grid;
  gap: 7px;
}
.governance-grid label > span {
  color: var(--muted);
  font-size: 10px;
  font-weight: 800;
}
.governance-grid .wide {
  grid-column: span 2;
}
.balanced-form small {
  color: var(--muted);
  font-size: 10px;
}
.identifier-panel {
  display: grid;
  gap: 13px;
  margin-top: 22px;
  padding: 19px;
  border-radius: 13px;
  background: linear-gradient(135deg, #f8f5ff, var(--surface-soft));
}
.identifier-panel h3 {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
}
.identifier-panel p {
  margin-top: 5px;
}
.identifier-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.identifier-chips span {
  display: grid;
  gap: 3px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
}
.identifier-chips span.primary {
  border-color: color-mix(in srgb, var(--primary) 45%, var(--border));
  background: color-mix(in srgb, var(--primary) 8%, var(--surface));
}
.identifier-chips small {
  color: var(--muted);
  font-size: 9px;
}
.identifier-chips b {
  font-size: 11px;
}
.identifier-form-v2 {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr auto;
  gap: 9px;
}
.profile-card-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 15px;
}
.field-group-card {
  display: grid;
  gap: 15px;
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface-soft);
}
.field-group-card:nth-child(odd) {
  background: linear-gradient(145deg, #f1f7ff, var(--surface));
}
.field-group-card:nth-child(even) {
  background: linear-gradient(145deg, #fbf5ff, var(--surface));
}
.group-title {
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--primary);
}
.group-title h3 {
  color: var(--text);
  font-size: 14px;
}
.group-title small {
  color: var(--muted);
  font-size: 10px;
}
.group-fields {
  display: grid;
  gap: 12px;
}
.group-fields label {
  display: grid;
  gap: 6px;
}
.group-fields label > span {
  color: var(--muted);
  font-size: 10px;
  font-weight: 800;
}
.group-fields b {
  color: #dc4c3e;
}
.group-fields input,
.group-fields select,
.group-fields textarea {
  width: 100%;
  min-height: 40px;
  padding: 8px 10px;
}
.group-fields small {
  color: var(--muted);
  font-size: 10px;
  line-height: 1.5;
}
.profile-save {
  display: flex;
  grid-column: span 2;
  justify-content: flex-end;
}
.system-handover {
  display: grid;
  gap: 16px;
  margin-top: 20px;
  padding: 20px;
  border: 1px solid color-mix(in srgb, var(--primary) 24%, var(--border));
  border-radius: 14px;
}
.system-handover h3 {
  display: flex;
  align-items: center;
  gap: 7px;
}
.system-handover p {
  margin-top: 5px;
}
.responsibility-surface {
  background: linear-gradient(150deg, #fbfdff, var(--surface));
}
.responsibility-form {
  padding: 20px;
  border-radius: 14px;
  background: var(--surface-soft);
}
.ownership-note {
  display: grid;
  place-items: center start;
  padding: 12px;
  border-radius: 9px;
  color: var(--muted);
  background: var(--surface);
  font-size: 11px;
  line-height: 1.6;
}
.relation-studio {
  display: grid;
  grid-template-columns: 210px 1fr;
  gap: 17px;
  padding: 17px;
  border-radius: 14px;
  background: linear-gradient(135deg, #eff6ff, #fbf9ff);
}
.relation-studio aside {
  position: relative;
  display: grid;
  align-content: center;
  gap: 6px;
  min-height: 156px;
  padding: 18px;
  overflow: hidden;
  border-radius: 13px;
  color: #fff;
  background: linear-gradient(145deg, var(--primary-strong), var(--primary));
}
.relation-studio aside span {
  color: rgb(255 255 255 / 70%);
  font-size: 10px;
}
.relation-studio aside strong {
  font-size: 15px;
}
.relation-studio aside small {
  color: rgb(255 255 255 / 78%);
  font-size: 10px;
}
.relation-studio aside i {
  position: absolute;
  width: 130px;
  height: 130px;
  right: -40px;
  bottom: -58px;
  border: 1px solid rgb(255 255 255 / 30%);
  border-radius: 50%;
}
.relation-studio form {
  display: grid;
  align-content: center;
  gap: 14px;
}
.direction-picker {
  display: flex;
  gap: 7px;
}
.direction-picker button {
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--muted);
  background: var(--surface);
  cursor: pointer;
  font-size: 11px;
}
.direction-picker button.active {
  border-color: var(--primary);
  color: var(--primary);
  background: color-mix(in srgb, var(--primary) 9%, var(--surface));
  font-weight: 800;
}
.relation-input-grid {
  display: grid;
  grid-template-columns: 1fr 1.5fr 1fr auto;
  align-items: end;
  gap: 9px;
}
.relation-input-grid label {
  display: grid;
  gap: 6px;
}
.relation-lanes {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-top: 20px;
}
.relation-lanes section {
  min-height: 260px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
}
.relation-lanes section > header {
  display: flex;
  gap: 10px;
  padding: 15px;
  border-bottom: 1px solid var(--border);
}
.relation-lanes section > header > span {
  display: grid;
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 8px;
  color: var(--primary);
  background: color-mix(in srgb, var(--primary) 10%, var(--surface));
  font-size: 10px;
  font-weight: 900;
}
.relation-lanes h3 {
  font-size: 13px;
}
.relation-lanes header p {
  margin-top: 4px;
  font-size: 9px;
  line-height: 1.5;
}
.relation-card-list {
  display: grid;
  gap: 9px;
  padding: 11px;
}
.relation-card {
  display: grid;
  grid-template-columns: 18px 1fr 24px;
  align-items: center;
  gap: 8px;
  padding: 11px;
  border: 1px solid var(--border);
  border-radius: 9px;
  color: var(--text);
  background: var(--surface-soft);
}
.relation-card:hover {
  border-color: var(--primary);
}
.relation-card > svg {
  color: var(--primary);
}
.relation-card small,
.relation-card strong,
.relation-card span {
  display: block;
}
.relation-card small,
.relation-card span {
  color: var(--muted);
  font-size: 9px;
}
.relation-card strong {
  margin: 2px 0;
  font-size: 11px;
}
.relation-inline-edit {
  display: grid;
  gap: 6px;
  margin-top: 8px;
}
.relation-inline-edit select {
  min-width: 0;
  padding: 7px 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--ink);
}
.relation-inline-edit > span {
  display: flex;
  gap: 6px;
}
.compact-button {
  min-height: 28px;
  padding: 5px 9px;
  font-size: 11px;
}
.relation-empty {
  display: grid;
  min-height: 105px;
  place-items: center;
  align-content: center;
  gap: 8px;
  color: var(--muted);
  font-size: 10px;
  text-align: center;
}
.timeline-v2 {
  display: grid;
  gap: 0;
}
.timeline-v2 article {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 12px;
  padding: 0 0 18px;
}
.timeline-v2 i {
  width: 10px;
  height: 10px;
  margin-top: 4px;
  border-radius: 50%;
  background: var(--primary);
  box-shadow: 0 0 0 5px color-mix(in srgb, var(--primary) 11%, transparent);
}
.timeline-v2 strong,
.timeline-v2 span,
.timeline-v2 code {
  display: block;
}
.timeline-v2 strong {
  font-size: 12px;
}
.timeline-v2 span {
  margin-top: 3px;
  color: var(--muted);
  font-size: 10px;
}
.timeline-v2 code {
  margin-top: 7px;
  color: var(--muted);
  font-size: 9px;
  white-space: normal;
  word-break: break-all;
}
.danger {
  color: #cc3a1d;
}
@media (max-width: 1060px) {
  .asset-hero-grid,
  .relationship-position > div,
  .relation-lanes {
    grid-template-columns: repeat(2, 1fr);
  }
  .asset-hero-grid .asset-code-card {
    grid-column: span 2;
  }
  .relation-studio,
  .relation-input-grid {
    grid-template-columns: 1fr;
  }
  .profile-card-grid {
    grid-template-columns: 1fr;
  }
  .profile-save {
    grid-column: auto;
  }
  .identifier-form-v2 {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 680px) {
  .asset-hero-grid,
  .relationship-position > div,
  .overview-context,
  .balanced-form,
  .relation-lanes {
    grid-template-columns: 1fr;
  }
  .asset-hero-grid .asset-code-card,
  .balanced-form .wide,
  .governance-grid .wide {
    grid-column: auto;
  }
  .governance-grid {
    grid-template-columns: 1fr;
  }
  .detail-surface {
    padding: 18px;
  }
  .asset-detail-tabs {
    overflow: auto;
  }
  .asset-detail-tabs button {
    white-space: nowrap;
  }
  .identifier-form-v2 {
    grid-template-columns: 1fr;
  }
}
</style>
