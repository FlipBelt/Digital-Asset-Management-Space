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

import AssetAttachments from "../components/AssetAttachments.vue";
import PeoplePicker from "../components/PeoplePicker.vue";
import ChildAccountsPanel from "../components/ChildAccountsPanel.vue";
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
  type RelationshipChoice,
  type RelationshipGroup,
  type RelationshipEdge,
  type RelationshipNode,
  type RelationshipSection,
  type ServiceInstance,
} from "../lib/api";
import { displayStatus } from "../lib/labels";
import { isPersonalSubscription, subscriptionStatus } from "../lib/personalSubscriptions";
import { isAIOutcome } from "../lib/aiDiscovery";
import { relationshipGroups, relationshipNodeHref, relationshipPreview, relationshipSentence } from "../lib/relationship";

const route = useRoute();
const router = useRouter();
const id = String(route.params.id);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const message = ref("");
const tab = ref(typeof route.query.tab === "string" && ["overview", "relations", "responsibility", "fields", "history"].includes(route.query.tab) ? route.query.tab : "overview");
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
const relationChoices = ref<RelationshipChoice[]>([]);
const relationGroup = ref<RelationshipGroup>("ownership");
const relationLoading = ref(false);
const relationError = ref("");
const relationRequestId = ref(crypto.randomUUID());
const identifierEditing = ref(false);
const nativeIdentifier = reactive({ identifier: "", identifier_type: "account_id" });
const identifierRequestId = ref(crypto.randomUUID());
let identifierPayload = "";
let relationPayload = "";
const platformAccountContext = ref<PlatformAccountContext | null>(null);
const platforms = ref<Platform[]>([]);
const serviceInstances = ref<ServiceInstance[]>([]);
const childAccounts = ref<Account[]>([]);
const confirmedResponsible = ref<string | null>(null);
const canSetRepositoryVisibility = ref(false);
const repositoryVisibility = ref<"public" | "private" | "unknown">("unknown");
const visibilityRequestId = ref(crypto.randomUUID());
let visibilityPayload = "";
const canReview = ref(false);
const canAssignAcrossCompany = ref(false);
const canUploadOutcome = ref(false);
const proposals = ref<{person_id: string | null; role_type: string}[]>([]);
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
const relationForm = reactive({ choice_key: "", target_id: "", note: "" });
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
    (item) => item.section === "structure" && item.label === "册册身份",
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
    { label: "访问地址", value: profile.value.production_url },
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
const responsibleDisplay = computed(() => confirmedResponsible.value
  ? personName.value[confirmedResponsible.value] || "已登记负责人"
  : assignment.responsible_status === "proposed" && assignment.responsible_person_id
    ? `建议：${personName.value[assignment.responsible_person_id] || '已登记人员'}` : "尚未配置");
const responsibleHint = computed(() => assignment.responsible_status === "proposed"
  ? "待确认 · 请在责任与使用中保存" : assignment.responsible_status === "inactive"
    ? assignment.responsibility_issue || "责任配置待更新" : assignment.responsible_status === "confirmed"
      ? "已确认的责任配置" : "请在责任与使用中配置");
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
const assignmentPeople = computed(() => people.value.filter(person =>
  person.person_type === "employee" && person.employment_status === "active" &&
  (canAssignAcrossCompany.value || !asset.value?.legal_entity_id || person.legal_entity_id === asset.value.legal_entity_id),
));
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
  if (type.value?.profile_kind === "internal_system") {
    const values = Object.values(profileForm);
    return Math.round(100 * values.filter(value => value.trim()).length / values.length);
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
    structure: "归属与账号资料",
    business: "部署、调用与使用",
    responsibility: "责任与使用",
  }[section];
}
function relationSectionDescription(section: RelationshipSection) {
  return {
    structure: "公司主体、册册身份和所属平台等结构性事实",
    business: "部署、挂载、调用、使用及已有采购记录；每条关系显示实际方向",
    responsibility: "负责人、使用人员、部门和账号授权",
  }[section];
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
const groupChoices = computed(() => relationChoices.value.filter(row => row.group === relationGroup.value));
const selectedChoice = computed(() => groupChoices.value.find(row => row.key === relationForm.choice_key));
const selectedTarget = computed(() => selectedChoice.value?.targets.find(row => row.id === relationForm.target_id));
const targetQuery = ref("");
const relationTargets = computed(() => (selectedChoice.value?.targets || []).filter(row =>
  `${row.label} ${row.object_type} ${row.detail}`.toLowerCase().includes(targetQuery.value.trim().toLowerCase())));
const targetLabel = computed(() => ({ platform: "已有平台", legal_entity: "归属公司", department: "归属部门", asset: "已有资产或公司账号" }[selectedChoice.value?.target_kind || "asset"]));
const relationshipSlots = computed(() => {
  const responsible = confirmedResponsible.value
    ? personName.value[confirmedResponsible.value]
    : null;
  return [
    {
      layer: "L1",
      label: "归属公司",
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
      label: "册册身份",
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
    if (item.is_child_account && item.management_href) {
      await router.replace(item.management_href);
      return;
    }
    const currentUser = await api.currentSession();
    canAssignAcrossCompany.value = currentUser.roles.some(role => ["system_admin", "asset_manager"].includes(role));
    canReview.value = currentUser.roles.some(role => ["system_admin", "asset_manager", "department_manager", "group_leader"].includes(role));
    canUploadOutcome.value = item.created_by_person_id === currentUser.person_id || currentUser.roles.some(role => ["system_admin", "asset_manager"].includes(role));
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
    repositoryVisibility.value = item.repository_visibility || "unknown";
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
    fieldDefinitions.value = typeRows.find(row => row.id === item.asset_type_id)?.code === "platform_tenant"
      ? fieldRows.filter(row => !["tenant_id", "account_id", "uid", "external_id", "workspace_id", "organization_id"].includes(row.field_key))
      : fieldRows;
    Object.assign(assignment, assignmentRow);
    const responsibilities = await api.assetResponsibilities(id);
    confirmedResponsible.value = assignmentRow.confirmed_responsible_person_id || null;
    canSetRepositoryVisibility.value = canUploadOutcome.value || canReview.value || confirmedResponsible.value === currentUser.person_id;
    proposals.value = responsibilities.filter(r => ["proposed_responsible", "proposed_user"].includes(r.role_type));
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
    if (currentType?.code === "registration_identity") {
      await router.replace({ path: "/accounts", query: { section: "contacts" } });
      return;
    }
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
    if (currentType?.code === "platform_tenant") {
      platformAccountContext.value = await api.platformAccountContext(id);
      nativeIdentifier.identifier = platformAccountContext.value.tenant_identifier || "";
      nativeIdentifier.identifier_type = platformAccountContext.value.external_identifier_type || "account_id";
      if (!["account_id", "uid", "organization_id", "workspace_id", "merchant_id", "other"].includes(nativeIdentifier.identifier_type)) nativeIdentifier.identifier_type = "other";
    }
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
  relationLoading.value = true; relationError.value = "";
  try {
    relationChoices.value = await api.relationshipChoices(id);
    if (!groupChoices.value.length) relationGroup.value = relationChoices.value[0]?.group || "ownership";
    relationForm.choice_key = groupChoices.value.find(row => row.targets.length)?.key || groupChoices.value[0]?.key || "";
    relationForm.target_id = "";
  } catch (reason) { relationError.value = reason instanceof Error ? reason.message : "关系读取失败"; }
  finally { relationLoading.value = false; }
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
function useResponsibleDepartment() {
  if (assignment.ownership_scope !== "pending" || !responsibleDepartmentHint.value) return;
  assignment.ownership_scope = "department";
  assignment.owner_department_id = responsibleDepartmentHint.value;
}
function applyProposals() {
  const responsible = proposals.value.find(r => r.role_type === "proposed_responsible");
  if (responsible?.person_id) assignment.responsible_person_id = responsible.person_id;
  assignment.user_person_ids = proposals.value.filter(r => r.role_type === "proposed_user" && r.person_id).map(r => r.person_id!);
}
async function saveAssignment() {
  if (!asset.value || !assignment.responsible_person_id) return;
  saving.value = true;
  error.value = "";
  message.value = "";
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
    await load();
    message.value = isPlatformTenant.value ? "责任配置已保存，概览与跟进同步更新。" : "责任配置已保存，概览与跟进同步更新。成果审核在管理区维护。";
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
    asset.value = await api.asset(id);
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
    asset.value = await api.asset(id);
    message.value = "接管资料已保存";
  } finally {
    saving.value = false;
  }
}

async function saveRepositoryVisibility() {
  if (!asset.value || saving.value) return;
  saving.value = true; error.value = "";
  const body = { version: asset.value.version, visibility: repositoryVisibility.value };
  const snapshot = JSON.stringify(body);
  if (visibilityPayload && visibilityPayload !== snapshot) visibilityRequestId.value = crypto.randomUUID();
  visibilityPayload = snapshot;
  try {
    await api.saveRepositoryVisibility(id, { ...body, request_id: visibilityRequestId.value });
    message.value = "仓库可见性已保存；私有或尚未确认的 GitHub 地址不对外展示。";
    visibilityPayload = ""; visibilityRequestId.value = crypto.randomUUID(); await load();
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "仓库可见性保存失败"; }
  finally { saving.value = false; }
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
  if (!asset.value || !relationForm.target_id || !selectedChoice.value || saving.value) return;
  saving.value = true; relationError.value = "";
  const body = { version: asset.value.version, ...relationForm };
  const snapshot = JSON.stringify(body);
  if (relationPayload && relationPayload !== snapshot) relationRequestId.value = crypto.randomUUID();
  relationPayload = snapshot;
  try {
    await api.createRelationshipConnection(id, { ...body, request_id: relationRequestId.value });
    relationForm.target_id = "";
    relationForm.note = "";
    relationPayload = ""; relationRequestId.value = crypto.randomUUID();
    await load();
    message.value = "关联已建立";
  } catch (reason) {
    relationError.value = reason instanceof Error ? reason.message : "建立失败";
  } finally { saving.value = false; }
}
async function saveNativeIdentifier() {
  if (!asset.value || saving.value) return;
  saving.value = true; error.value = "";
  const body = { version: asset.value.version, ...nativeIdentifier };
  const snapshot = JSON.stringify(body);
  if (identifierPayload && identifierPayload !== snapshot) identifierRequestId.value = crypto.randomUUID();
  identifierPayload = snapshot;
  try {
    await api.savePlatformIdentifier(id, { ...body, request_id: identifierRequestId.value });
    identifierEditing.value = false; identifierPayload = ""; identifierRequestId.value = crypto.randomUUID();
    await load(); message.value = "平台账号 ID 已保存；核验页会直接引用这份资料。";
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "账号 ID 保存失败"; }
  finally { saving.value = false; }
}
async function removeRelation(item: RelationshipEdge) {
  if (!item.relation_id || !item.editable) return;
  try {
    if (item.source_model === "AssetPlatformLink") await api.archivePlatformLink(id, item.relation_id);
    else await api.archiveRelation(id, item.relation_id);
    await load();
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
watch(relationGroup, () => {
  relationForm.choice_key = groupChoices.value.find(row => row.targets.length)?.key || groupChoices.value[0]?.key || "";
  relationForm.target_id = ""; targetQuery.value = "";
});
watch(() => relationForm.choice_key, () => { relationForm.target_id = ""; targetQuery.value = ""; });
watch(
  () => assignment.responsible_person_id,
  (personId) => {
    assignment.user_person_ids = assignment.user_person_ids.filter(id => id !== personId);
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
      <ArrowLeft :size="16" />返回数字中心
    </button>
    <PageHeader
      :eyebrow="primaryIdentifier"
      :title="asset?.name ?? '资产详情'"
      :description="type?.name ?? '统一资产资料'"
    >
      <RouterLink v-if="canReview && asset && type && isAIOutcome(asset, type) && asset.status === 'active' && asset.review_status === 'pending_review'" :to="{path: '/manage/reviews', query: {asset: asset.id}}" class="secondary-button">审核此成果</RouterLink>
      <StatusBadge v-if="asset && isPersonalSubscription(asset)">个人订阅 · 无需审核</StatusBadge>
      <RouterLink v-if="platformAccountContext" :to="{path: '/accounts', query: {tab: 'tenants', verify: asset?.id}}" class="secondary-button">查看账号核验</RouterLink>
      <StatusBadge :tone="asset?.archived_at ? 'default' : 'success'">{{
        asset?.archived_at ? "已归档" : asset ? subscriptionStatus(asset) : "待核验"
      }}</StatusBadge
      ><button v-if="asset" class="secondary-button" @click="toggleArchive">
        <component :is="asset.archived_at ? RotateCcw : Archive" :size="16" />{{
          asset.archived_at ? "恢复" : "归档"
        }}
      </button>
    </PageHeader>
    <AssetAttachments v-if="asset" :key="asset.version" :asset-id="asset.id" :can-upload="canUploadOutcome" @uploaded="load" />
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
            responsibleDisplay
          }}</strong
          ><small>{{ responsibleHint }} · {{ assignment.user_person_ids.length }} 位协同使用人</small>
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
            <small>{{ slot.label }}</small
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
            <h2>基本资料</h2>
            <p>确认资产名称和使用入口；状态与补充说明可以按需展开。</p>
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
              <Smartphone :size="19" /><span>主要册册身份</span
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
              <UserRound :size="19" /><span>负责人</span
              ><strong>{{
                responsibleDisplay
              }}</strong
              ><small
                >{{ responsibleHint }} · 登记人：{{
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
                  <b>使用状态与补充说明（选填）</b>
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
              <Save :size="16" />保存基本资料
            </button>
          </div>
        </form>
        <section v-if="platformAccountContext" class="identifier-panel" id="platform-identifier">
          <div><h3><Tags :size="18" />平台账号 ID</h3><p>这里只填写一次。概览和核验页直接引用；资产编号由系统生成。</p></div>
          <div v-if="!identifierEditing" class="native-id-read"><strong>{{ platformAccountContext.tenant_identifier || '平台未提供 / 暂未填写' }}</strong><button v-if="canReview" class="secondary-button" @click="identifierEditing = true">维护账号 ID</button></div>
          <form v-else class="balanced-form" @submit.prevent="saveNativeIdentifier">
            <label><span>ID 类型</span><select v-model="nativeIdentifier.identifier_type"><option value="account_id">账号 ID</option><option value="uid">UID</option><option value="organization_id">组织 ID</option><option value="workspace_id">工作区 ID</option><option value="merchant_id">商户号</option><option value="other">其他平台编号</option></select></label>
            <label><span>平台提供的账号 ID（可选）</span><input v-model="nativeIdentifier.identifier" maxlength="200" placeholder="从平台后台复制，平台没有提供时可留空" /></label>
            <div class="form-actions wide"><button type="button" class="secondary-button" :disabled="saving" @click="identifierEditing = false">取消</button><button class="primary-button" :disabled="saving">保存账号 ID</button></div>
          </form>
        </section>
        <section class="identifier-panel">
          <div>
            <h3><Tags :size="18" />{{ isPlatformTenant ? '历史编号（只读）' : '其他标识' }}</h3>
            <p>{{ isPlatformTenant ? '保留旧资料用于追溯。平台原生 ID 统一在上方维护。' : '补充当前资源的其他编号，资产编号由系统生成。' }}</p>
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
          <form v-if="!isPlatformTenant" class="identifier-form-v2" @submit.prevent="saveIdentifier">
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

      <section v-if="tab === 'accounts' && isPlatformTenant && asset" class="detail-surface profile-surface">
        <RouterLink v-if="platformAccountContext" :to="{ path: '/accounts', query: { platform: platformAccountContext.platform_id, tenant: asset.id } }" class="secondary-button">返回平台账号管理</RouterLink>
        <ChildAccountsPanel :asset-id="asset.id" :legal-entity-id="asset.legal_entity_id" :can-manage="canReview" @changed="load" />
      </section>

      <section v-if="tab === 'profile'" class="detail-surface profile-surface">
        <form class="balanced-form content-panel" @submit.prevent="saveRepositoryVisibility">
          <div class="wide"><h3>GitHub 仓库可见性</h3><p>由负责人确认仓库是公开还是私有。私有及尚未确认时隐藏地址和所有指向 GitHub 的按钮，访问应用的链接仍按资料展示。</p></div>
          <label><span>仓库可见性</span><select v-model="repositoryVisibility" :disabled="saving || !canSetRepositoryVisibility"><option value="unknown">尚未确认（隐藏地址）</option><option value="public">公开仓库</option><option value="private">私有仓库（隐藏地址）</option></select></label>
          <div class="form-actions"><button v-if="canSetRepositoryVisibility" class="secondary-button" :disabled="saving">保存仓库可见性</button><p v-else class="form-hint">请由负责人或资产管理员维护。</p></div>
        </form>
        <header>
          <div>
            <span class="section-kicker">专属资料</span>
            <h2>按类型填写，不用记复杂字段</h2>
            <p>每张彩色卡片对应一组业务信息；标册提示告诉你该填什么。</p>
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
              ><input v-model="profileForm.repository_url" placeholder="隐藏的已有地址无需重复填写，留空会保留" /></label
            ><label
              ><span>访问地址</span
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
            <h2>登记人固定，负责人可由管理员调整</h2>
            <p>AI 成果默认由认证登记人负责；改派不改变登记人，也不增加成果版本。归属与协同人员单独维护。</p>
          </div>
          <UserRound :size="30" />
        </header>
        <section v-if="proposals.length" class="content-panel"><h3>登记器建议的责任人员</h3><p v-for="row in proposals" :key="String(row.person_id)">{{ row.role_type === 'proposed_responsible' ? '建议负责人' : '建议协同人' }}：{{ people.find(p => p.id === row.person_id)?.display_name || '人员待核对' }}</p><p>建议尚未生效。核对后采用建议，再确认责任配置。</p><button class="secondary-button" type="button" @click="applyProposals">采用建议填写下方表单</button></section>
        <form
          class="balanced-form responsibility-form"
          @submit.prevent="saveAssignment"
        >
          <p class="wide responsibility-hint">归属决定由公司还是部门管理；公司级不等于全员可见，成果共享范围单独设置。</p>
          <label
            ><span>归属范围</span
            ><select v-model="assignment.ownership_scope">
              <option value="pending">暂不确定</option>
              <option value="company">公司统一管理</option>
              <option value="department">指定部门管理</option>
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
          <div class="wide responsibility-people">
            <PeoplePicker id="asset-responsible" v-model:person-id="assignment.responsible_person_id" label="负责人（必选一人）" :people="assignmentPeople" :departments="departments" :disabled="saving" />
            <p v-if="responsibleDepartmentHint" class="responsibility-hint">负责人主部门：{{ departmentName[responsibleDepartmentHint] }}。归属范围单独确认。
              <button v-if="assignment.ownership_scope === 'pending'" type="button" class="secondary-button" :disabled="saving" @click="useResponsibleDepartment">采用该部门作为归属</button>
            </p>
          </div>
          <PeoplePicker id="asset-users" v-model:person-ids="assignment.user_person_ids" class="wide" label="协同使用人员（选填）" :people="assignmentPeople" :departments="departments" multiple :excluded-ids="assignment.responsible_person_id ? [assignment.responsible_person_id] : []" :disabled="saving" hint="保存后负责人获得本系统资产管理与使用权限，协同人员按现有规则获得使用权限；跨公司配置由资产管理员维护，外部平台权限需单独处理。" />
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
            <span class="section-kicker">关联关系</span>
            <h2>选择实际关系，再关联已有对象</h2>
            <p>
              公司与部门决定归属；平台、账号和资源记录部署与使用。负责人在“责任与使用”中确认，机机号与邮箱在“平台与账号”中管理。
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
                v-for="group in relationshipGroups"
                :key="group.key"
                type="button"
                :class="{ active: relationGroup === group.key }"
                @click="relationGroup = group.key"
              >
                {{ group.label }}
              </button>
            </div>
            <p v-if="relationLoading" role="status" class="form-hint">正在读取数字中心已有对象…</p>
            <p v-if="selectedChoice" class="form-hint">{{ selectedChoice.description }}</p>
            <p v-if="selectedChoice" class="relation-preview">{{ relationshipPreview(asset.name, selectedChoice, selectedTarget?.label) }}</p>
            <p v-if="relationError" class="form-error" role="alert">{{ relationError }} <button type="button" class="secondary-button compact-button" @click="loadRelationOptions">重新读取</button></p>
            <div class="relation-input-grid">
              <label
                ><span>关系</span
                ><select v-model="relationForm.choice_key" required :disabled="relationLoading || saving">
                  <option
                    v-for="item in groupChoices"
                    :key="item.key"
                    :value="item.key"
                  >
                    {{ item.label }} · {{ item.targets.length }} 个可选对象
                  </option>
                  <option v-if="!groupChoices.length" value="">
                    当前对象不适用此类关系
                  </option>
                </select></label
              ><label
                ><span>{{ targetLabel }}</span
                ><input v-model="targetQuery" type="search" placeholder="搜索名称、编号或公司" :disabled="saving || !selectedChoice?.targets.length" />
                <select v-model="relationForm.target_id" required :disabled="saving || !selectedChoice?.targets.length">
                  <option value="" disabled>选择{{ targetLabel }}</option>
                  <option
                    v-for="item in relationTargets"
                    :key="item.id"
                    :value="item.id"
                  >
                    {{ item.label }} · {{ item.object_type }}{{ item.detail ? ` · ${item.detail}` : '' }}
                  </option>
                </select></label
              ><label
                ><span>备册（可选）</span
                ><input
                  v-model="relationForm.note"
                  placeholder="例如业务系统主实例" /></label
              ><button
                class="primary-button"
                :disabled="saving || relationLoading || !selectedTarget"
              >
                <Plus :size="16" />{{ saving ? '正在保存…' : '保存关系' }}
              </button>
            </div>
            <p v-if="!relationLoading && !selectedChoice?.targets.length" class="form-hint">{{ groupChoices.length ? '当前没有符合条件的已登记对象。请先登记对应资源，再回到这里关联。' : '此类关系不适用于当前对象或你没有维护权限，可查看下方已建立的关系。' }} <RouterLink to="/accounts">查看平台与账号</RouterLink></p>
            <p v-else-if="!relationTargets.length" class="form-hint">没有匹配搜索词的对象，请调整关键词。</p>
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
                  <small>{{ item.label }}</small
                  ><strong>{{ relationOtherNode(item)?.label ?? "关联对象" }}</strong
                  ><span>{{ relationshipGraph ? relationshipSentence(relationshipGraph.current_node, item, relationshipGraph.nodes) : '' }}</span>
                  <span v-if="item.note">{{ item.note }}</span>
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
.native-id-read { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.native-id-read strong { overflow-wrap:anywhere; }
.relation-preview { padding:12px; margin:12px 0; border:1px solid var(--border); border-radius:8px; background:var(--surface); font-size:13px; font-weight:600; overflow-wrap:anywhere; }
.responsibility-people { display:grid; gap:12px; min-width:0; }
.responsibility-hint { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin:0; color:var(--muted); font-size:12px; line-height:1.6; }

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
