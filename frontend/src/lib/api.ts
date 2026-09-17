export interface HealthStatus { status: string; database: string }
export interface ScenarioSummary {
  code: string; name: string; description: string;
  asset_count: number; platform_count: number; account_count: number;
  resource_count: number; responsible_count: number;
}
export interface ScenarioNode {
  id: string; parent_id: string | null; kind: string; label: string;
  subtitle: string | null; asset_id: string | null; status: string;
  responsible_name: string | null; department_name: string | null;
  href: string | null; metadata: Record<string, string | number | boolean | null>;
}
export interface ScenarioOverview { scenario: ScenarioSummary; nodes: ScenarioNode[]; unclassified_count: number }
export interface LegalEntity { id: string; code: string; name: string; status: string }
export interface LegalEntityProfile {
  id: string; legal_entity_id: string; entity_type: string | null; jurisdiction: string | null;
  registration_status: string | null; legal_representative: string | null; established_on: string | null;
  registered_address: string | null; registered_capital: string | null; business_scope: string | null;
  source_note: string | null; verification_status: string;
}
export interface LegalEntityIdentifier {
  id: string; legal_entity_id: string; namespace: string; identifier_type: string;
  identifier_value: string; is_primary: boolean; verification_status: string;
  source_note: string | null; archived_at: string | null;
}
export interface Department { id: string; legal_entity_id: string; parent_id: string | null; code: string; name: string; status: string }
export interface Person { id: string; legal_entity_id: string; department_id: string | null; employee_no: string; display_name: string; email: string | null; employment_status: string; person_type: string }
export interface DepartmentMembership { id: string; person_id: string; department_id: string; is_manager: boolean; is_primary: boolean; is_active: boolean }
export interface AssetCategory { id: string; parent_id: string | null; code: string; name: string; sort_order: number }
export interface AssetType { id: string; category_id: string; code: string; name: string; profile_kind: string; code_prefix: string; ownership_default: string; is_system: boolean; completeness_rules?: Record<string, unknown> }
export interface AssetFieldDefinition { id: string; asset_type_id: string; field_key: string; label: string; data_type: string; is_required: boolean; options: string[] | null; group_name: string; help_text: string | null; unit: string | null; validation: Record<string, unknown>; confidentiality: string; is_searchable: boolean; completeness_weight: number; sort_order: number; entry_visibility: "core" | "optional" | "advanced" | "conditional"; requirement_stage: "create" | "activation" | "optional"; applies_to_existing: boolean; condition_rules: Record<string, unknown> }
export interface AssetFieldValue { id: string; asset_id: string; field_definition_id: string; value: { value: unknown } }
export interface Asset {
  id: string; asset_code: string; name: string; asset_type_id: string; legal_entity_id: string | null;
  owner_department_id: string | null; ownership_scope: string; status: string; criticality: string; confidentiality: string;
  source_type: string; started_at: string | null; expires_at: string | null; last_verified_at: string | null;
  description: string | null; version: number; created_at: string; updated_at: string; archived_at: string | null;
  created_by_person_id?: string | null; confirmed_by_person_id?: string | null; confirmed_at?: string | null; review_status?: string;
}
export interface AssetListResponse { data: Asset[]; pagination: { page: number; page_size: number; total: number } }
export interface HuduAssetItem {
  id: string; asset_code: string; name: string; status: string; review_status: string;
  criticality: string; confidentiality: string; ownership_scope: string;
  asset_type_id: string; asset_type_code: string | null; asset_type_name: string;
  profile_kind: string; category_id: string | null; category_code: string | null; category_name: string;
  legal_entity_id: string | null; legal_entity_name: string | null;
  owner_department_id: string | null; owner_department_name: string | null;
  expires_at: string | null; started_at: string | null; last_verified_at: string | null;
  description: string | null; version: number; updated_at: string | null; created_at: string | null;
  archived_at: string | null; has_owner: boolean;
}
export interface HuduOverview {
  total_assets: number; active_assets: number; draft_assets: number; expiring_soon: number; missing_owner: number;
  category_counts: { label: string; value: number }[]; recent_assets: HuduAssetItem[]; due_items: HuduAssetItem[]; generated_at: string;
}
export interface HuduAssetsResponse {
  items: HuduAssetItem[]; total: number; page: number; page_size: number;
  categories: { id: string; code: string; name: string; count: number }[];
  types: { id: string; code: string; name: string; category_id: string; count: number }[];
}
export interface HuduResponsibility { id: string; role_type: string; is_primary: boolean; person_id: string | null; person_name: string | null; department_id: string | null; department_name: string | null; starts_at: string | null; ends_at: string | null }
export interface HuduRelation { id: string; relation_type: string; note: string | null; direction: string; related_asset_id: string; related_name: string; related_asset_code: string; related_type_name: string; related_category_name: string }
export interface HuduAssetDetail { asset: HuduAssetItem; responsibilities: HuduResponsibility[]; relations: HuduRelation[]; identifiers: { id: string; namespace: string; identifier_type: string; identifier_value: string; is_primary: boolean; verification_status: string }[]; profile: { kind: string; data: Record<string, string | null> } | null; account_context: { login_identifier: string; account_type: string; mfa_status: string; privilege_level: string; platform_name: string | null; tenant_identifier: string | null } | null; history: { id: string; action: string; created_at: string | null; after_data: Record<string, unknown> | null }[] }
export interface HuduExpirationsResponse { items: HuduAssetItem[]; total: number; window_days: number }
export interface Responsibility { id: string; asset_id: string; person_id: string | null; department_id: string | null; role_type: string; is_primary: boolean; starts_at: string | null; ends_at: string | null; archived_at: string | null }
export interface AssetRelation { id: string; source_asset_id: string; target_asset_id: string; relation_type: string; source_type: string; note: string | null; archived_at: string | null }
export type RelationshipSection = "structure" | "business" | "responsibility";
export type RelationshipDirection = "upstream" | "downstream" | "peer" | "responsibility";
export interface RelationshipNode { id: string; layer: number; label: string; object_type: string; kind: string; asset_id: string | null; status: string | null; href: string | null }
export interface RelationshipEdge { id: string; source: string; target: string; label: string; section: RelationshipSection; direction: RelationshipDirection; source_model: string; editable: boolean; relation_id: string | null; note: string | null; edit_kind: string | null; edit_target_id: string | null }
export interface AssetRelationshipView { current_node: RelationshipNode; nodes: RelationshipNode[]; edges: RelationshipEdge[] }
export interface AssetPlatformLink { id: string; asset_id: string; platform_id: string; relation_type: string; source_type: string; source_import_record_id: string | null; review_status: string; confirmed_by_person_id: string | null; confirmed_at: string | null; note: string | null; archived_at: string | null }
export interface Provider { id: string; code: string; name: string; website: string | null }
export interface Platform { id: string; provider_id: string | null; code: string; name: string; category: string; website: string | null; review_status: string; description: string | null; submitted_by_person_id: string | null }
export interface PlatformTenant { id: string; asset_id: string; platform_id: string; legal_entity_id: string; tenant_identifier: string | null; external_identifier_type: string | null; ownership_nature: string; account_scope: string; verification_status: string }
export interface Account { id: string; asset_id: string; platform_tenant_id: string; login_identifier: string; account_type: string; registration_identity_type: string; registration_person_id: string | null; mfa_status: string; privilege_level: string; parent_account_id: string | null; account_kind: string; login_method: string; account_role: string; primary_person_id: string | null; legacy_source_id: string | null; legacy_metadata: Record<string, unknown> }
export interface CredentialReference { id: string; account_id: string | null; asset_id: string | null; provider: string; item_id: string; secure_url: string | null; last_rotated_at: string | null; last_verified_at: string | null }
export interface ServiceProduct { id: string; provider_id: string; code: string; name: string; service_category: string; billing_mode: string }
export interface ServiceInstance { id: string; asset_id: string; service_product_id: string; purchase_platform_id: string | null; purchase_tenant_asset_id: string | null; subscription_name: string | null; currency: string; starts_at: string | null; expires_at: string | null }
export interface MetricDefinition { id: string; metric_key: string; display_name: string; unit: string; aggregation: string }
export interface MetricSample { id: string; service_instance_id: string; metric_definition_id: string; value: string; currency: string | null; collected_at: string; source_type: string }
export interface InternalSystemProfile { id: string; asset_id: string; repository_url: string | null; production_url: string | null; tech_stack: string | null; deployment_guide_url: string | null; recovery_guide_url: string | null; backup_description: string | null }
export interface DashboardData { scope: string; metrics: Record<string, number>; by_status: ChartDatum[]; by_type: ChartDatum[]; recent_assets: Pick<Asset, "id" | "asset_code" | "name" | "status" | "updated_at">[] }
export interface ChartDatum { label: string; value: number }
export interface GroupView { dimension: string; groups: { id: string; label: string; count: number }[] }
export interface ConnectorDefinition { id: string; code: string; name: string; version: string; capabilities: string[]; enabled: boolean }
export interface ProviderConnection { id: string; connector_definition_id: string; legal_entity_id: string; name: string; status: string; configuration: Record<string, unknown>; last_synced_at: string | null; last_error: string | null }
export interface UsageConnection {
  id: string; platform_code: "deepseek" | "minimax" | "aliyun"; platform_name: string; legal_entity_id: string;
  service_instance_id: string | null; name: string; status: string; configuration: Record<string, unknown>;
  last_synced_at: string | null; last_error: string | null;
}
export interface UsageConnectionAction { status: string; message: string; metrics_written: number; observed_at: string | null; snapshot: Record<string, unknown> | null }
export interface UsageAlertRule { id: string; provider_connection_id: string; name: string; metric_key: string; threshold: string; currency: string | null; recipient_person_ids: string[]; enabled: boolean; last_state: string | null; last_notified_at: string | null }
export interface UsageNotificationSchedule { id: string; name: string; connection_ids: string[]; recipient_person_ids: string[]; time_of_day: string; timezone: string; enabled: boolean; last_sent_on: string | null }
export interface UsageNotificationLog { id: string; event_type: string; status: string; recipient_count: number; message_summary: string; detail: Record<string, unknown>; created_at: string }
export interface UsageMonitoringOverview { connections: { id: string; name: string; platform_code: string; status: string; latest_snapshot_at: string | null }[]; dingtalk_recipient_person_ids: string[] }
export interface AuditLog { id: string; action: string; object_type: string; object_id: string | null; before_data: Record<string, unknown> | null; after_data: Record<string, unknown> | null; created_at: string }
export interface WorkflowRequest { id: string; request_no: string; request_type: string; title: string; requester_person_id: string | null; asset_id: string | null; status: string; detail: Record<string, unknown>; version: number; created_at: string }
export interface RiskFinding { id: string; rule_key: string; asset_id: string | null; person_id: string | null; severity: string; status: string; title: string; detail: Record<string, unknown>; version: number; detected_at: string }
export interface ImportPreview { file_name: string; rows: Record<string, unknown>[]; valid_count: number; error_count: number }
export interface CurrentUser { id: string; username: string; person_id: string | null; display_name: string | null; department_id: string | null; job_title: string | null; roles: string[]; permissions: string[]; csrf_token: string }
export interface Session { user: CurrentUser; expires_at: string; session_token?: string | null }
export interface DingTalkStatus { enabled: boolean; configured: boolean; corp_id: string | null }
export interface DingTalkConfig { corpId: string | null; agentId: string | null; configured: boolean }
export interface PmSessionUser { dingUserId: string; name: string; avatar: string | null; department: string | null; role: string; roles: string[]; permissions: string[]; sessionToken: string }
export interface DingTalkProfile { person_id: string; dingtalk_user_id: string; job_title: string | null }
export interface DingTalkIdentity { person_id: string; display_name: string; department_id: string | null; job_title: string | null; is_department_manager: boolean }
export interface DingTalkSession { user: CurrentUser; identity: DingTalkIdentity; expires_at: string }
export interface AssetAssignment { owner_department_id: string | null; ownership_scope: string; responsible_person_id: string | null; user_person_ids: string[] }
export interface AssetIdentifier { id: string; asset_id: string; namespace: string; identifier_type: string; identifier_value: string; is_primary: boolean; verification_status: string; confidentiality: string; source_import_record_id: string | null; archived_at: string | null }
export interface RelationDefinition { id: string; relation_type: string; source_type_code: string; target_type_code: string; forward_label: string; inverse_label: string; category: string; source_max_count: number | null; target_max_count: number | null; is_system: boolean }
export interface RelationOption { relation_type: string; label: string; target_type_codes: string[]; direction: "upstream" | "downstream" | "peer" }
export interface RegistrationIdentity { id: string; asset_id: string; asset_code: string; legal_entity_id: string | null; name: string; identity_type: string; identifier: string; source_nature: string; custodian_person_id: string | null; verification_status: string }
export interface LayerRecord { id: string; layer: number; name: string; object_type: string; legal_entity_name: string | null; platform_name: string | null; category: string | null; ownership_nature: string | null; account_count: number; status: string; asset_id: string | null; updated_at: string }
export interface IntakeLink { kind: string; label: string; relation: string; asset_id: string | null }
export interface IntakeNextAction { key: string; label: string; description: string; target: string; required: boolean }
export interface IntakeResult { id: string; asset_id: string; asset_code: string; name: string; object_type: string; completion_percent: number; links: IntakeLink[]; next_actions: IntakeNextAction[] }
export interface PlatformAccountContext { asset_id: string; platform_id: string; platform_name: string; platform_category: string; platform_website: string | null; tenant_identifier: string | null; external_identifier_type: string | null; ownership_nature: string; account_scope: string; verification_status: string; evidence_note?: string | null; registration_identities: RegistrationIdentity[] }
export interface AssetMapNode { id: string; label: string; kind: string; status: string; asset_id: string | null; subtitle: string | null }
export interface AssetMapEdge { id: string; source: string; target: string; relation: string }
export interface AssetMapData { nodes: AssetMapNode[]; edges: AssetMapEdge[] }
export interface FlexibleImportCandidate { row_number: number; source_category?: string | null; source_identifier?: string | null; suggested_object_type: string; suggested_name: string; confidence: number; raw: Record<string, unknown>; warnings: string[] }
export interface FlexibleImportPreview { source_name: string; source_kind: string; source_sha256?: string | null; recognized_counts?: Record<string, number>; candidates: FlexibleImportCandidate[] }
export interface ImportBatch { id: string; file_name: string; status: string; total_count: number; proposed_object_count: number; proposed_relation_count: number; analysis_mode: string | null; created_at: string }
export interface ImportAccountCandidate { source_record_id: string; platform_name: string; login_identifier: string; source_file: string; evidence: string[]; confidence: number; status: string; pending_reason: string; assigned_l4_asset_id: string | null; assigned_l4_name: string | null }
export interface ImportProposalObject {
  id: string; proposal_key: string; source_record_id: string | null; source_file: string | null; source_reference: string | null; layer_code: string; object_type: string; suggested_name: string;
  normalized_payload: Record<string, unknown>; evidence: { source_record_id: string; field: string; value: string }[];
  extraction_confidence: number; match_confidence: number; match_status: string; review_status: string;
  matched_asset_id: string | null; matched_platform_id: string | null; matched_person_id: string | null;
  matched_department_id: string | null; review_note: string | null;
}
export interface ImportProposalRelation {
  id: string; source_proposal_id: string; target_proposal_id: string; relation_type: string;
  evidence: { source_record_id: string; field: string; value: string }[]; confidence: number;
  validation_status: string; review_status: string; review_note: string | null;
}
export interface ImportPlan {
  batch_id: string; analysis_mode: string; catalog_fingerprint: string; summary: Record<string, unknown>;
  objects: ImportProposalObject[]; relations: ImportProposalRelation[];
}
export interface ImportDryRunResult {
  batch_id: string; can_commit: boolean; create_count: number; reuse_count: number;
  pending_review_count: number; invalid_relation_count: number; messages: string[];
}
export interface BossPilotImportResult { batch_id: string; created_service_assets: number; created_internal_system_assets: number; pending_access_grants: number; unresolved_access_grants: number; staged_finance_records: number; status: string }

let csrfToken = "";
let pmSessionToken = "";

export function setCsrfToken(value: string) { csrfToken = value; }
export function setPmSessionToken(value: string) { pmSessionToken = value; }
export function clearPmSessionToken() { pmSessionToken = ""; }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (pmSessionToken) headers.set("X-PM-Session", pmSessionToken);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes((init.method ?? "GET").toUpperCase()) && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const controller = init.signal ? null : new AbortController();
  const timeout = controller ? window.setTimeout(() => controller.abort(), 12000) : null;
  let response: Response;
  const requestPath = apiPath(path);
  try {
    response = await fetch(requestPath, { ...init, credentials: "include", headers, signal: init.signal ?? controller?.signal });
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") {
      throw new ApiError(408, "请求超时，请检查网络或钉钉连接后重试");
    }
    throw reason;
  } finally {
    if (timeout !== null) window.clearTimeout(timeout);
  }
  if (!response.ok) {
    let message = `请求失败：${response.status}`;
    try { const body = await response.json(); message = body.detail ?? body.message ?? message } catch { /* keep generic */ }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

/** Resolve API links for both the production root and the isolated test mount. */
export function apiPath(path: string): string {
  const apiBase = import.meta.env.VITE_API_BASE
    ?? (window.location.pathname === "/test" || window.location.pathname.startsWith("/test/") ? "/test-api" : "");
  return path.startsWith("/api") ? `${apiBase}${path}` : path;
}

const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  login: async (username: string, password: string) => {
    const session = await request<Session>("/api/v1/sessions", json("POST", { username, password }));
    setCsrfToken(session.user.csrf_token);
    if (session.session_token) setPmSessionToken(session.session_token);
    return session;
  },
  currentSession: async () => {
    const user = await request<CurrentUser>("/api/v1/sessions/current");
    setCsrfToken(user.csrf_token);
    return user;
  },
  logout: async () => { await request<void>("/api/v1/sessions/current", { method: "DELETE" }); setCsrfToken(""); clearPmSessionToken(); },
  dingtalkStatus: () => request<DingTalkStatus>("/api/v1/dingtalk/status"),
  dingtalkConfig: async () => {
    const config = await request<DingTalkConfig>("/api/dingtalk/config");
    return { enabled: config.configured, configured: config.configured, corp_id: config.corpId } as DingTalkStatus;
  },
  dingtalkLogin: async (authCode: string) => request<{ user: PmSessionUser }>("/api/dingtalk/login", json("POST", { authCode })),
  dingtalkDiagnostic: (body: { phase: string; bridge?: string; message?: string; user_agent?: string }) => request<void>("/api/v1/dingtalk/client-diagnostic", json("POST", body)),
  dingtalkIdentity: async (authCode: string) => {
    const session = await request<DingTalkSession>("/api/v1/dingtalk/identity", json("POST", { auth_code: authCode }));
    setCsrfToken(session.user.csrf_token);
    return session;
  },
  dingtalkProfiles: () => request<DingTalkProfile[]>("/api/v1/dingtalk/profiles"),
  syncDingtalkDirectory: (legalEntityId: string) => request<Record<string, number | string>>("/api/v1/dingtalk/sync", json("POST", { legal_entity_id: legalEntityId })),
  myAssets: () => request<Asset[]>("/api/v1/workspace/my-assets"),
  health: () => request<HealthStatus>("/api/v1/health/ready"),
  scenarios: () => request<ScenarioSummary[]>("/api/v1/workspace/scenarios"),
  scenario: (code: string) => request<ScenarioOverview>(`/api/v1/workspace/scenarios/${encodeURIComponent(code)}`),
  dashboard: (scope = "company") => request<DashboardData>(`/api/v1/dashboard?scope=${scope}`),
  analytics: () => request<{ by_category: ChartDatum[]; by_department: (ChartDatum & { id: string })[] }>("/api/v1/analytics/summary"),
  groupView: (dimension: string) => request<GroupView>(`/api/v1/views/${dimension}`),
  search: (q: string) => request<{ assets: Asset[]; people: Person[] }>(`/api/v1/search?q=${encodeURIComponent(q)}`),
  legalEntities: () => request<LegalEntity[]>("/api/v1/legal-entities"),
  createLegalEntity: (body: Record<string, unknown>) => request<LegalEntity>("/api/v1/legal-entities", json("POST", body)),
  legalEntityProfile: (id: string) => request<LegalEntityProfile | null>(`/api/v1/legal-entities/${id}/profile`),
  saveLegalEntityProfile: (id: string, body: Record<string, unknown>) => request<LegalEntityProfile>(`/api/v1/legal-entities/${id}/profile`, json("PUT", body)),
  legalEntityIdentifiers: (id: string) => request<LegalEntityIdentifier[]>(`/api/v1/legal-entities/${id}/identifiers`),
  createLegalEntityIdentifier: (id: string, body: Record<string, unknown>) => request<LegalEntityIdentifier>(`/api/v1/legal-entities/${id}/identifiers`, json("POST", body)),
  departments: () => request<Department[]>("/api/v1/departments"),
  departmentMemberships: () => request<DepartmentMembership[]>("/api/v1/department-memberships"),
  createDepartment: (body: Record<string, unknown>) => request<Department>("/api/v1/departments", json("POST", body)),
  people: () => request<Person[]>("/api/v1/people"),
  createPerson: (body: Record<string, unknown>) => request<Person>("/api/v1/people", json("POST", body)),
  assetCategories: () => request<AssetCategory[]>("/api/v1/asset-categories"),
  assetTypes: () => request<AssetType[]>("/api/v1/asset-types"),
  createAssetType: (body: Record<string, unknown>) => request<AssetType>("/api/v1/asset-types", json("POST", body)),
  assetFields: (typeId: string) => request<AssetFieldDefinition[]>(`/api/v1/asset-types/${typeId}/fields`),
  createAssetField: (typeId: string, body: Record<string, unknown>) => request<AssetFieldDefinition>(`/api/v1/asset-types/${typeId}/fields`, json("POST", body)),
  archiveAssetField: (typeId: string, fieldId: string) => request<void>(`/api/v1/asset-types/${typeId}/fields/${fieldId}/archive`, json("POST")),
  relationDefinitions: () => request<RelationDefinition[]>("/api/v1/relation-definitions"),
  createRelationDefinition: (body: Record<string, unknown>) => request<RelationDefinition>("/api/v1/relation-definitions", json("POST", body)),
  assets: (params: Record<string, string | number | boolean | undefined> = {}) => {
    const search = new URLSearchParams({ page: "1", page_size: "100" });
    Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== "") search.set(key, String(value)) });
    return request<AssetListResponse>(`/api/v1/assets?${search}`);
  },
  huduOverview: () => request<HuduOverview>("/api/v1/hudu/overview"),
  huduAssets: (params: Record<string, string | number | boolean | undefined> = {}) => {
    const search = new URLSearchParams({ page: "1", page_size: "60" });
    Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== "") search.set(key, String(value)) });
    return request<HuduAssetsResponse>(`/api/v1/hudu/assets?${search}`);
  },
  huduAsset: (id: string) => request<HuduAssetDetail>(`/api/v1/hudu/assets/${id}`),
  huduExpirations: () => request<HuduExpirationsResponse>("/api/v1/hudu/expirations"),
  asset: (id: string) => request<Asset>(`/api/v1/assets/${id}`),
  assetIdentifiers: (id: string) => request<AssetIdentifier[]>(`/api/v1/assets/${id}/identifiers`),
  createAssetIdentifier: (id: string, body: Record<string, unknown>) => request<AssetIdentifier>(`/api/v1/assets/${id}/identifiers`, json("POST", body)),
  createAsset: (body: Record<string, unknown>) => request<Asset>("/api/v1/assets", json("POST", body)),
  updateAsset: (id: string, body: Record<string, unknown>) => request<Asset>(`/api/v1/assets/${id}`, json("PATCH", body)),
  archiveAsset: (id: string, version: number) => request<Asset>(`/api/v1/assets/${id}/archive?version=${version}`, json("POST")),
  restoreAsset: (id: string, version: number) => request<Asset>(`/api/v1/assets/${id}/restore?version=${version}`, json("POST")),
  responsibilities: (id: string) => request<Responsibility[]>(`/api/v1/assets/${id}/responsibilities`),
  assetAssignment: (id: string) => request<AssetAssignment>(`/api/v1/assets/${id}/assignment`),
  saveAssetAssignment: (id: string, body: { version: number; owner_department_id: string | null; ownership_scope: string; responsible_person_id: string; user_person_ids: string[] }) => request<AssetAssignment>(`/api/v1/assets/${id}/assignment`, json("PUT", body)),
  addResponsibility: (id: string, body: Record<string, unknown>) => request<Responsibility>(`/api/v1/assets/${id}/responsibilities`, json("POST", body)),
  archiveResponsibility: (assetId: string, id: string) => request(`/api/v1/assets/${assetId}/responsibilities/${id}/archive`, json("POST")),
  relations: (id: string) => request<AssetRelation[]>(`/api/v1/assets/${id}/relations`),
  relationNeighborhood: (id: string) => request<AssetRelation[]>(`/api/v1/assets/${id}/relation-neighborhood`),
  relationshipView: (id: string) => request<AssetRelationshipView>(`/api/v1/assets/${id}/relationship-view`),
  updateRelationshipLink: (id: string, kind: string, target_id: string) => request<AssetRelationshipView>(`/api/v1/assets/${id}/relationship-links/${kind}`, json("PUT", { target_id })),
  addRelation: (id: string, body: Record<string, unknown>) => request<AssetRelation>(`/api/v1/assets/${id}/relations`, json("POST", body)),
  archiveRelation: (assetId: string, id: string) => request(`/api/v1/assets/${assetId}/relations/${id}/archive`, json("POST")),
  relationOptions: (id: string, direction: "upstream" | "downstream" | "peer") => request<RelationOption[]>(`/api/v1/assets/${id}/relation-options?direction=${direction}`),
  createIntelligentRelation: (id: string, body: Record<string, unknown>) => request<AssetRelation>(`/api/v1/assets/${id}/relations/intelligent`, json("POST", body)),
  internalProfile: (id: string) => request<InternalSystemProfile | null>(`/api/v1/assets/${id}/internal-system-profile`),
  saveInternalProfile: (id: string, body: Record<string, unknown>) => request<InternalSystemProfile>(`/api/v1/assets/${id}/internal-system-profile`, json("PUT", body)),
  assetFieldValues: (id: string) => request<AssetFieldValue[]>(`/api/v1/assets/${id}/field-values`),
  saveAssetFieldValues: (id: string, body: { field_definition_id: string; value: unknown }[]) => request<AssetFieldValue[]>(`/api/v1/assets/${id}/field-values`, json("PUT", body)),
  providers: () => request<Provider[]>("/api/v1/providers"),
  createProvider: (body: Record<string, unknown>) => request<Provider>("/api/v1/providers", json("POST", body)),
  platforms: () => request<Platform[]>("/api/v1/platforms"),
  createPlatform: (body: Record<string, unknown>) => request<Platform>("/api/v1/platforms", json("POST", body)),
  updatePlatform: (id: string, body: Record<string, unknown>) => request<Platform>(`/api/v1/platforms/${id}`, json("PATCH", body)),
  platformRelationshipView: (id: string) => request<AssetRelationshipView>(`/api/v1/platforms/${id}/relationship-view`),
  platformTenants: () => request<PlatformTenant[]>("/api/v1/platform-tenants"),
  createPlatformTenant: (body: Record<string, unknown>) => request<PlatformTenant>("/api/v1/platform-tenants", json("POST", body)),
  accounts: () => request<Account[]>("/api/v1/accounts"),
  platformAccountChildren: (assetId: string) => request<Account[]>(`/api/v1/workspace/platform-accounts/${assetId}/child-accounts`),
  createPlatformAccountChild: (assetId: string, body: Record<string, unknown>) => request<Account>(`/api/v1/workspace/platform-accounts/${assetId}/child-accounts`, json("POST", body)),
  createAccount: (body: Record<string, unknown>) => request<Account>("/api/v1/accounts", json("POST", body)),
  credentialReferences: () => request<CredentialReference[]>("/api/v1/credential-references"),
  createCredentialReference: (body: Record<string, unknown>) => request<CredentialReference>("/api/v1/credential-references", json("POST", body)),
  serviceProducts: () => request<ServiceProduct[]>("/api/v1/service-products"),
  createServiceProduct: (body: Record<string, unknown>) => request<ServiceProduct>("/api/v1/service-products", json("POST", body)),
  serviceInstances: () => request<ServiceInstance[]>("/api/v1/service-instances"),
  createServiceInstance: (body: Record<string, unknown>) => request<ServiceInstance>("/api/v1/service-instances", json("POST", body)),
  metricDefinitions: () => request<MetricDefinition[]>("/api/v1/metric-definitions"),
  usageConnections: () => request<UsageConnection[]>("/api/v1/usage-connections"),
  createUsageConnection: (body: Record<string, unknown>) => request<UsageConnection>("/api/v1/usage-connections", json("POST", body)),
  updateUsageConnection: (id: string, body: Record<string, unknown>) => request<UsageConnection>(`/api/v1/usage-connections/${id}`, json("PATCH", body)),
  testUsageConnection: (id: string) => request<UsageConnectionAction>(`/api/v1/usage-connections/${id}/test`, json("POST")),
  syncUsageConnection: (id: string) => request<UsageConnectionAction>(`/api/v1/usage-connections/${id}/sync`, json("POST")),
  usageMonitoringOverview: () => request<UsageMonitoringOverview>("/api/v1/usage-monitoring/overview"),
  usageAlertRules: () => request<UsageAlertRule[]>("/api/v1/usage-monitoring/rules"),
  createUsageAlertRule: (body: Record<string, unknown>) => request<UsageAlertRule>("/api/v1/usage-monitoring/rules", json("POST", body)),
  usageNotificationSchedules: () => request<UsageNotificationSchedule[]>("/api/v1/usage-monitoring/schedules"),
  createUsageNotificationSchedule: (body: Record<string, unknown>) => request<UsageNotificationSchedule>("/api/v1/usage-monitoring/schedules", json("POST", body)),
  usageNotificationLogs: () => request<UsageNotificationLog[]>("/api/v1/usage-monitoring/logs"),
  runUsageMonitoring: () => request<Record<string, number>>("/api/v1/usage-monitoring/run", json("POST")),
  metrics: (id: string) => request<MetricSample[]>(`/api/v1/service-instances/${id}/metrics`),
  createMetric: (id: string, body: Record<string, unknown>) => request<MetricSample>(`/api/v1/service-instances/${id}/metrics`, json("POST", body)),
  uiConfig: () => request<{ default_theme: string; allowed_themes: string[]; features: Record<string, boolean> }>("/api/v1/app-config/ui"),
  updateUiConfig: (body: Record<string, unknown>) => request("/api/v1/admin/ui-settings", json("PATCH", body)),
  connectorDefinitions: () => request<ConnectorDefinition[]>("/api/v1/connector-definitions"),
  connections: () => request<ProviderConnection[]>("/api/v1/provider-connections"),
  createConnection: (body: Record<string, unknown>) => request<ProviderConnection>("/api/v1/provider-connections", json("POST", body)),
  testConnection: (id: string) => request<{ status: string; message: string }>(`/api/v1/provider-connections/${id}/test`, json("POST")),
  syncConnection: (id: string) => request(`/api/v1/provider-connections/${id}/sync`, json("POST")),
  auditLogs: () => request<AuditLog[]>("/api/v1/audit-logs"),
  requests: () => request<WorkflowRequest[]>("/api/v1/requests"),
  createRequest: (body: Record<string, unknown>) => request<WorkflowRequest>("/api/v1/requests", json("POST", body)),
  transitionRequest: (id: string, target: string, version: number) => request<WorkflowRequest>(`/api/v1/requests/${id}/transition?target_status=${target}&version=${version}`, json("POST")),
  risks: () => request<RiskFinding[]>("/api/v1/risk-findings"),
  scanRisks: () => request<RiskFinding[]>("/api/v1/risk-findings/scan", json("POST")),
  resolveRisk: (id: string, version: number) => request<RiskFinding>(`/api/v1/risk-findings/${id}/resolve?version=${version}`, json("POST")),
  previewImport: (file: File) => { const form = new FormData(); form.append("file", file); return request<ImportPreview>("/api/v1/imports/preview", { method: "POST", body: form }) },
  commitImport: (body: ImportPreview) => request("/api/v1/imports/commit", json("POST", body)),
  registrationIdentities: () => request<RegistrationIdentity[]>("/api/v1/workspace/registration-identities"),
  layerRecords: (layer: number) => request<LayerRecord[]>(`/api/v1/workspace/layer-records?layer=${layer}`),
  createRegistrationIdentity: (body: Record<string, unknown>) => request<RegistrationIdentity>("/api/v1/workspace/registration-identities", json("POST", body)),
  assetPlatformLinks: (assetId: string) => request<AssetPlatformLink[]>(`/api/v1/assets/${assetId}/platform-links`),
  createAssetPlatformLink: (assetId: string, body: Record<string, unknown>) => request<AssetPlatformLink>(`/api/v1/assets/${assetId}/platform-links`, json("POST", body)),
  platformAccountContext: (assetId: string) => request<PlatformAccountContext>(`/api/v1/workspace/platform-accounts/by-asset/${assetId}`),
  createCompanyPlatformAccount: (body: Record<string, unknown>) => request<IntakeResult>("/api/v1/workspace/platform-accounts", json("POST", body)),
  createResource: (body: Record<string, unknown>) => request<IntakeResult>("/api/v1/workspace/resources", json("POST", body)),
  createAccessGrant: (body: Record<string, unknown>) => request<{ id: string }>("/api/v1/workspace/access-grants", json("POST", body)),
  assetMap: (includePeople = false, platformId?: string) => {
    const params = new URLSearchParams({ include_people: String(includePeople) });
    if (platformId) params.set("platform_id", platformId);
    return request<AssetMapData>(`/api/v1/asset-map?${params.toString()}`);
  },
  analyzeImport: (file: File | null, pastedText = "") => {
    const form = new FormData();
    if (file) form.append("file", file);
    if (pastedText) form.append("pasted_text", pastedText);
    return request<FlexibleImportPreview>("/api/v1/imports/analyze", { method: "POST", body: form });
  },
  stageImport: (body: FlexibleImportPreview) => request<{ batch_id: string; staged_count: number; status: string; proposed_object_count: number; proposed_relation_count: number }>("/api/v1/imports/stage", json("POST", body)),
  importBatches: () => request<ImportBatch[]>("/api/v1/imports/batches"),
  importAccountCandidates: (batchId: string) => request<ImportAccountCandidate[]>(`/api/v1/imports/${batchId}/account-candidates`),
  importPlan: (batchId: string) => request<ImportPlan>(`/api/v1/imports/${batchId}/plan`),
  rebuildImportPlan: (batchId: string) => request<ImportPlan>(`/api/v1/imports/${batchId}/rebuild-plan`, json("POST")),
  enhanceImportWithAi: (batchId: string) => request<ImportPlan>(`/api/v1/imports/${batchId}/ai-analyze`, json("POST")),
  reviewImportProposal: (batchId: string, proposalId: string, body: Record<string, unknown>) => request<ImportPlan>(`/api/v1/imports/${batchId}/proposals/${proposalId}`, json("PATCH", body)),
  reviewImportRelation: (batchId: string, relationId: string, body: Record<string, unknown>) => request<ImportPlan>(`/api/v1/imports/${batchId}/relations/${relationId}`, json("PATCH", body)),
  dryRunImport: (batchId: string) => request<ImportDryRunResult>(`/api/v1/imports/${batchId}/dry-run`, json("POST")),
  commitBossPilotImport: (batchId: string, body: { legal_entity_id?: string; boss_person_id?: string }) => request<BossPilotImportResult>(`/api/v1/imports/${batchId}/commit-boss-pilot`, json("POST", body)),
};
