<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  CheckCircle2,
  FileSpreadsheet,
  FileText,
  GitFork,
  Inbox,
  Link2,
  PlayCircle,
  RotateCcw,
  Upload,
  WandSparkles,
} from "lucide-vue-next";

import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import {
  api,
  type FlexibleImportPreview,
  type ImportDryRunResult,
  type ImportBatch,
  type ImportAccountCandidate,
  type ImportPlan,
  type ImportProposalObject,
} from "../lib/api";

const file = ref<File | null>(null);
const pastedText = ref("");
const preview = ref<FlexibleImportPreview | null>(null);
const plan = ref<ImportPlan | null>(null);
const batches = ref<ImportBatch[]>([]);
const batchId = ref("");
const dryRun = ref<ImportDryRunResult | null>(null);
const accountCandidates = ref<ImportAccountCandidate[]>([]);
const loading = ref(false);
const error = ref("");
const message = ref("");
const sourceMode = ref<"file" | "paste">("file");
const selectedRows = ref(new Set<number>());

const selectedCandidates = computed(
  () => preview.value?.candidates.filter((item) => selectedRows.value.has(item.row_number)) ?? [],
);
const objectLabels: Record<string, string> = {
  registration_identity: "注册身份",
  platform: "平台目录",
  platform_account: "公司平台账号",
  access_grant: "人员授权",
  resource: "服务 / 资源",
  service_instance: "服务实例",
  internal_system: "内部系统",
  department_reference: "组织参考",
  expense_entry: "历史费用流水",
  workflow_request: "历史报销",
  payment_method_reference: "付款方式参考",
  budget_snapshot: "历史预算快照",
};
const layerLabels: Record<string, string> = {
  registration_identity: "第二层 · 注册身份",
  platform_directory: "第三层 · 平台目录",
  company_platform_account: "第四层 · 公司平台账号",
  access_authorization: "第五层 · 访问与授权",
  service_resource_system: "第六层 · 服务、资源与系统",
  historical_reference: "历史资料区 · 待核对",
};
const reviewLabels: Record<string, string> = {
  pending_review: "待确认",
  approved: "已确认",
  historical_only: "仅保留历史",
  rejected: "不接入",
};
const planGroups = computed(() => {
  const groups = new Map<string, ImportProposalObject[]>();
  for (const item of plan.value?.objects ?? []) {
    groups.set(item.layer_code, [...(groups.get(item.layer_code) ?? []), item]);
  }
  return [...groups.entries()];
});
const objectById = computed(
  () => new Map((plan.value?.objects ?? []).map((item) => [item.id, item])),
);
const plannedCounts = computed(() => {
  const summary = plan.value?.summary.object_counts;
  return summary && typeof summary === "object" ? (summary as Record<string, number>) : {};
});
const sourceGroups = computed(() => {
  const groups = new Map<string, ImportProposalObject[]>();
  for (const item of plan.value?.objects ?? []) {
    const source = item.source_file || "来源文件待确认";
    groups.set(source, [...(groups.get(source) ?? []), item]);
  }
  return [...groups.entries()];
});

function chooseFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null;
  preview.value = null;
}

function toggleRow(row: number) {
  const next = new Set(selectedRows.value);
  next.has(row) ? next.delete(row) : next.add(row);
  selectedRows.value = next;
}

function resetWorkbench() {
  preview.value = null;
  plan.value = null;
  batchId.value = "";
  dryRun.value = null;
  accountCandidates.value = [];
  file.value = null;
  pastedText.value = "";
  selectedRows.value = new Set();
}

async function loadBatches() {
  try {
    batches.value = await api.importBatches();
  } catch {
    // A user without import permission receives the normal API error only after an action.
  }
}

async function openBatch(id: string) {
  loading.value = true;
  error.value = "";
  try {
    batchId.value = id;
    const [loadedPlan, loadedCandidates] = await Promise.all([
      api.importPlan(id),
      api.importAccountCandidates(id),
    ]);
    plan.value = loadedPlan;
    accountCandidates.value = loadedCandidates;
    dryRun.value = null;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "打开历史批次失败";
  } finally {
    loading.value = false;
  }
}

async function analyze() {
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    preview.value = await api.analyzeImport(
      sourceMode.value === "file" ? file.value : null,
      sourceMode.value === "paste" ? pastedText.value : "",
    );
    selectedRows.value = new Set(preview.value.candidates.map((item) => item.row_number));
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "资料解析失败";
  } finally {
    loading.value = false;
  }
}

async function stage() {
  if (!preview.value || !selectedCandidates.value.length) return;
  loading.value = true;
  error.value = "";
  try {
    const result = await api.stageImport({ ...preview.value, candidates: selectedCandidates.value });
    batchId.value = result.batch_id;
    plan.value = await api.importPlan(result.batch_id);
    await loadBatches();
    dryRun.value = null;
    message.value = `已保留 ${result.staged_count} 条原始资料，并规划出 ${result.proposed_object_count} 个候选对象、${result.proposed_relation_count} 条候选关系。`;
    preview.value = null;
    file.value = null;
    pastedText.value = "";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "保存资料规划失败";
  } finally {
    loading.value = false;
  }
}

onMounted(() => { void loadBatches(); });

async function reviewProposal(item: ImportProposalObject, reviewStatus: string) {
  if (!batchId.value) return;
  loading.value = true;
  error.value = "";
  try {
    plan.value = await api.reviewImportProposal(batchId.value, item.id, {
      review_status: reviewStatus,
    });
    dryRun.value = null;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "更新审核状态失败";
  } finally {
    loading.value = false;
  }
}

async function rebuildPlan() {
  if (!batchId.value) return;
  loading.value = true;
  error.value = "";
  try {
    plan.value = await api.rebuildImportPlan(batchId.value);
    dryRun.value = null;
    message.value = "已按当前目录、人员、资产和关系规则重新规划。";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "重新规划失败";
  } finally {
    loading.value = false;
  }
}

async function enhanceWithAi() {
  if (!batchId.value) return;
  loading.value = true;
  error.value = "";
  try {
    plan.value = await api.enhanceImportWithAi(batchId.value);
    dryRun.value = null;
    message.value = "DeepSeek 已补充字段语义与分类建议；请继续人工确认，尚未写入正式资产库。";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "AI 增强分析失败";
  } finally {
    loading.value = false;
  }
}

async function runDryRun() {
  if (!batchId.value) return;
  loading.value = true;
  error.value = "";
  try {
    dryRun.value = await api.dryRunImport(batchId.value);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "提交预检失败";
  } finally {
    loading.value = false;
  }
}

function matchLabel(item: ImportProposalObject) {
  if (item.match_status === "matched") return "已匹配库内对象";
  if (item.match_status === "not_applicable") return "不进入正式资产库";
  return "建议新建 / 待确认";
}

function sourceReference(item: ImportProposalObject) {
  return item.source_reference || item.source_record_id?.slice(0, 8) || "来源记录待确认";
}

function relationSummary(item: ImportProposalObject) {
  const relations = (plan.value?.relations ?? []).filter(
    (relation) => relation.source_proposal_id === item.id || relation.target_proposal_id === item.id,
  );
  if (!relations.length) return "尚未建立候选关系";
  return relations.map((relation) => {
    const otherId = relation.source_proposal_id === item.id ? relation.target_proposal_id : relation.source_proposal_id;
    const other = objectById.value.get(otherId);
    const direction = relation.source_proposal_id === item.id ? "→" : "←";
    return `${direction} ${relation.relation_type} ${other?.suggested_name || "待确认对象"}`;
  }).join("；");
}

function relationGuidance(item: ImportProposalObject) {
  if (item.object_type === "registration_identity") return "可关联 L3；L4 / L5 暂不推断";
  if (item.object_type === "platform") return "平台目录；不自动生成 L4";
  if (item.object_type === "platform_account") return "L4 候选；需确认主体、租户或商户证据";
  if (item.object_type === "access_grant") return "L5 候选；需确认人员与权限";
  if (["service_instance", "resource", "internal_system"].includes(item.object_type)) return "可直接作为 L6；平台、L4、L5 均可后续关联";
  return "仅保留为历史或参考资料";
}
</script>

<template>
  <div class="page-stack import-workbench">
    <PageHeader
      eyebrow="六层资料接入"
      title="资料接入规划工作台"
      description="先保留原始资料，再拆解为六层对象、关系与待确认项；预检前不会写入正式资产库。"
    />
    <div v-if="message" class="message-panel success-message">
      <CheckCircle2 :size="18" />{{ message }}
    </div>
    <div v-if="error" class="message-panel error-message">{{ error }}</div>

    <section v-if="!preview && !plan" class="import-source-panel">
      <div v-if="batches.length" class="import-preview-heading">
        <div><span>已暂存资料</span><h2>继续处理历史批次</h2><p>已保存的来源资料可随时重新打开；不会因为离开页面而丢失。</p></div>
      </div>
      <div v-if="batches.length" class="record-list import-batch-list">
        <div v-for="item in batches" :key="item.id">
          <span class="record-icon"><Inbox :size="18" /></span>
          <div><strong>{{ item.file_name }}</strong><span>{{ new Date(item.created_at).toLocaleString("zh-CN") }} · 原始 {{ item.total_count }} 条 · 候选对象 {{ item.proposed_object_count }} · 关系 {{ item.proposed_relation_count }}</span></div>
          <StatusBadge :tone="item.analysis_mode === 'ai_enhanced' ? 'success' : 'default'">{{ item.analysis_mode === 'ai_enhanced' ? 'DeepSeek 已分析' : item.status }}</StatusBadge>
          <button class="secondary-button" :disabled="loading" @click="openBatch(item.id)">查看规划</button>
        </div>
      </div>
      <div class="import-mode-tabs">
        <button :class="{ active: sourceMode === 'file' }" @click="sourceMode = 'file'">
          <FileSpreadsheet :size="18" />上传文件
        </button>
        <button :class="{ active: sourceMode === 'paste' }" @click="sourceMode = 'paste'">
          <FileText :size="18" />粘贴内容
        </button>
      </div>
      <div v-if="sourceMode === 'file'" class="smart-upload-zone">
        <Upload :size="34" />
        <strong>{{ file?.name || "选择外部业务表格、IT资料或历史快照" }}</strong>
        <span>支持 .xlsx、.csv、.txt、.md、.html、.json，单个文件不超过 20MB</span>
        <input type="file" accept=".xlsx,.csv,.txt,.md,.html,.htm,.json" @change="chooseFile" />
      </div>
      <label v-else class="paste-source">
        <span>粘贴聊天记录、账号清单或临时整理内容</span>
        <textarea
          v-model="pastedText"
          rows="12"
          placeholder="每行可以是一条账号、平台、服务器、域名或授权信息……"
        />
      </label>
      <div class="import-source-examples">
        <span><b>业务授权资料</b>：识别员工、工具、订阅与使用关系</span>
        <span><b>IT资产资料</b>：识别平台、账号、服务器、域名与系统候选项</span>
      </div>
      <button
        class="primary-button import-analyze-button"
        :disabled="loading || (sourceMode === 'file' ? !file : !pastedText.trim())"
        @click="analyze"
      >
        <WandSparkles :size="17" />{{ loading ? "正在解析…" : "解析并预览" }}
      </button>
    </section>

    <section v-if="!preview && !plan" class="import-preview-panel mapping-quick-view">
      <div class="import-preview-heading">
        <div>
          <span>接入后的展示结构</span>
          <h2>先看实例，再决定是否连接</h2>
          <p>上传并暂存后，系统会按来源文件展示原子实例。以下是老板台账和阿里云资料的展示示意。</p>
        </div>
      </div>
      <div class="mapping-quick-grid">
        <article><span class="mapping-kicker">老板台账 · 服务记录</span><strong>ChatGPT Plus / Team、Claude Pro、API</strong><p><b>L6</b> 具体订阅或 API 实例；可关联 OpenAI / Anthropic / Google 等 L3；L4、L5 待确认。</p></article>
        <article><span class="mapping-kicker">阿里云.txt</span><strong>阿里云、163 邮箱、登录身份</strong><p><b>L3</b> 平台目录；<b>L2</b> 邮箱身份；没有企业租户证据，不自动生成 L4。</p></article>
        <article><span class="mapping-kicker">影刀.txt</span><strong>影刀服务、VPN 入口、管理员身份</strong><p><b>L6</b> 影刀与 VPN 服务；<b>L2</b> 登录身份；VPN 供应商和租户关系待确认。</p></article>
      </div>
    </section>

    <section v-if="preview" class="import-preview-panel">
      <div class="import-preview-heading">
        <div>
          <span>来源：{{ preview.source_name }}</span>
          <h2>识别出 {{ preview.candidates.length }} 条候选资料</h2>
          <p>先选择要保留的来源记录。下一步会按六层模型拆解对象和关系，不直接创建正式资产。</p>
          <small v-if="preview.source_sha256">源文件指纹：{{ preview.source_sha256.slice(0, 16) }}…</small>
          <small v-if="preview.recognized_counts">{{ Object.entries(preview.recognized_counts).map(([key, value]) => `${objectLabels[key] || key} ${value} 条`).join("；") }}</small>
        </div>
        <button class="secondary-button" @click="preview = null">重新选择</button>
      </div>
      <div class="import-candidate-table"><table><thead><tr><th></th><th>识别名称</th><th>建议归类</th><th>可信度</th><th>原始内容</th></tr></thead><tbody><tr v-for="candidate in preview.candidates" :key="candidate.row_number"><td><input type="checkbox" :checked="selectedRows.has(candidate.row_number)" @change="toggleRow(candidate.row_number)" /></td><td><strong>{{ candidate.suggested_name }}</strong><small v-if="candidate.warnings.length">{{ candidate.warnings.join("；") }}</small></td><td><StatusBadge tone="default">{{ objectLabels[candidate.suggested_object_type] || candidate.suggested_object_type }}</StatusBadge></td><td>{{ Math.round(candidate.confidence * 100) }}%</td><td><span class="raw-preview">{{ Object.values(candidate.raw).filter(Boolean).join(" · ") }}</span></td></tr></tbody></table></div>
      <div class="import-commit-bar"><span><Inbox :size="18" />已选择 {{ selectedCandidates.length }} 条，将保留原始来源供后续核对</span><button class="primary-button" :disabled="loading || !selectedCandidates.length" @click="stage">{{ loading ? "正在建立规划…" : "建立六层规划" }}</button></div>
    </section>

    <template v-if="plan">
      <section class="import-source-panel">
        <div class="import-preview-heading">
          <div>
            <span>导入批次 {{ plan.batch_id.slice(0, 8) }} · {{ plan.analysis_mode === "rules" ? "规则规划" : plan.analysis_mode === "ai_enhanced" ? "DeepSeek 增强规划" : plan.analysis_mode }}</span>
            <h2>六层对象与关系规划</h2>
            <p>当前规划只保存候选项。确认后先运行提交预检；正式入库会在后续统一提交步骤中执行。</p>
          </div>
          <div class="button-row"><button class="secondary-button" :disabled="loading" @click="enhanceWithAi"><WandSparkles :size="16" />DeepSeek 增强分析</button><button class="secondary-button" :disabled="loading" @click="rebuildPlan"><RotateCcw :size="16" />仅按规则重建</button><button class="secondary-button" :disabled="loading" @click="resetWorkbench">新建接入</button></div>
        </div>
        <div class="import-source-examples"><span v-for="(count, layer) in plannedCounts" :key="layer"><b>{{ layerLabels[layer] || layer }}</b>：{{ count }} 项</span></div>
      </section>

      <section class="import-preview-panel instance-map-panel">
        <div class="section-heading">
          <div>
            <span>实例化映射预览</span>
            <h2>每条来源资料先确定自身层级</h2>
            <p>这里按来源文件展开原子实例。关系只展示已有证据和规则建议；没有证据的 L4、L5 不会被自动补出。</p>
          </div>
          <div class="instance-map-legend"><span><i class="legend-dot source-dot" />来源事实</span><span><i class="legend-dot layer-dot" />建议层级</span><span><i class="legend-dot relation-dot" />候选关系</span></div>
        </div>
        <div class="source-instance-groups">
          <article v-for="[source, items] in sourceGroups" :key="source" class="source-instance-group">
            <header>
              <div><span>来源文件</span><strong>{{ source }}</strong></div>
              <small>{{ items.length }} 个候选实例</small>
            </header>
            <div class="source-instance-list">
              <div v-for="item in items" :key="item.id" class="source-instance-row">
                <div class="source-instance-main">
                  <div class="source-instance-title"><strong>{{ item.suggested_name }}</strong><StatusBadge tone="default">{{ layerLabels[item.layer_code] || item.layer_code }}</StatusBadge></div>
                  <small>{{ sourceReference(item) }} · {{ relationGuidance(item) }}</small>
                </div>
                <div class="source-instance-relation"><Link2 :size="15" /><span>{{ relationSummary(item) }}</span></div>
                <div class="source-instance-review"><StatusBadge :tone="item.review_status === 'approved' ? 'success' : item.review_status === 'historical_only' ? 'warning' : 'default'">{{ reviewLabels[item.review_status] || item.review_status }}</StatusBadge><small>{{ Math.round(item.extraction_confidence * 100) }}% 识别</small></div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section v-for="[layer, items] in planGroups" :key="layer" class="import-preview-panel">
        <div class="section-heading"><div><span>{{ layerLabels[layer] || layer }}</span><h2>{{ items.length }} 个候选对象</h2><p>“已匹配”仅是建议，仍由您确认是否复用；历史资料不会进入正式资产库。</p></div></div>
        <div class="import-candidate-table"><table><thead><tr><th>建议对象</th><th>对象类型</th><th>来源与匹配</th><th>识别可信度</th><th>审核</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td><strong>{{ item.suggested_name }}</strong><small>{{ item.evidence.map((entry) => `${entry.field}：${entry.value}`).join("；") }}</small></td><td><StatusBadge tone="default">{{ objectLabels[item.object_type] || item.object_type }}</StatusBadge></td><td><small>{{ matchLabel(item) }}<template v-if="item.match_confidence"> · 匹配 {{ Math.round(item.match_confidence * 100) }}%</template></small></td><td>{{ Math.round(item.extraction_confidence * 100) }}%</td><td><div class="button-row"><StatusBadge :tone="item.review_status === 'approved' ? 'success' : item.review_status === 'historical_only' ? 'warning' : 'default'">{{ reviewLabels[item.review_status] || item.review_status }}</StatusBadge><button v-if="item.review_status === 'pending_review'" class="secondary-button" :disabled="loading" @click="reviewProposal(item, 'approved')">确认</button><button v-if="item.review_status === 'pending_review'" class="secondary-button" :disabled="loading" @click="reviewProposal(item, 'rejected')">不接入</button></div></td></tr></tbody></table></div>
      </section>

      <section v-if="accountCandidates.length" class="import-preview-panel">
        <div class="section-heading"><div><span>惜君批次 · 账号资料承载</span><h2>待归属账号</h2><p>这些是脱敏的“平台＋登录标识”资料，不是 L2、L4 或 L6 正式对象。确认公司及 L4 证据后再归入账号与席位。</p></div></div>
        <div class="import-candidate-table"><table><thead><tr><th>平台</th><th>账号标识</th><th>来源文件与证据</th><th>置信度</th><th>当前状态</th></tr></thead><tbody><tr v-for="item in accountCandidates" :key="`${item.source_record_id}-${item.platform_name}-${item.login_identifier}`"><td><strong>{{ item.platform_name }}</strong></td><td>{{ item.login_identifier }}</td><td><small><b>{{ item.source_file }}</b> · {{ item.evidence.join("；") }}</small><small>{{ item.pending_reason }}</small></td><td>{{ Math.round(item.confidence * 100) }}%</td><td><RouterLink v-if="item.assigned_l4_asset_id" :to="`/assets/${item.assigned_l4_asset_id}?tab=accounts`"><StatusBadge tone="success">{{ item.status }} · {{ item.assigned_l4_name }}</StatusBadge></RouterLink><StatusBadge v-else tone="warning">{{ item.status }}</StatusBadge></td></tr></tbody></table></div>
      </section>

      <section class="import-preview-panel">
        <div class="section-heading"><div><span>对象关系</span><h2>识别出 {{ plan.relations.length }} 条候选关系</h2><p>关系会根据当前关系规则预检；未配置或不兼容的关系不能直接进入正式资产图谱。</p></div></div>
        <div class="import-candidate-table"><table><thead><tr><th>来源对象</th><th>关系</th><th>目标对象</th><th>可信度</th><th>规则校验</th></tr></thead><tbody><tr v-for="relation in plan.relations" :key="relation.id"><td>{{ objectById.get(relation.source_proposal_id)?.suggested_name || "待确认对象" }}</td><td><GitFork :size="15" /> {{ relation.relation_type }}</td><td>{{ objectById.get(relation.target_proposal_id)?.suggested_name || "待确认对象" }}</td><td>{{ Math.round(relation.confidence * 100) }}%</td><td><StatusBadge :tone="relation.validation_status === 'valid' ? 'success' : relation.validation_status === 'informational' ? 'default' : 'warning'">{{ relation.validation_status === 'valid' ? '已通过' : relation.validation_status === 'informational' ? '仅作参考' : '需配置或确认' }}</StatusBadge></td></tr></tbody></table></div>
        <div class="import-commit-bar"><span><Inbox :size="18" />预检不会写入正式资产、账号、人员或关系。</span><button class="primary-button" :disabled="loading" @click="runDryRun"><PlayCircle :size="17" />{{ loading ? "正在预检…" : "运行提交预检" }}</button></div>
      </section>

      <section v-if="dryRun" class="import-source-panel">
        <div class="section-heading"><div><span>提交预检结果</span><h2>{{ dryRun.can_commit ? "规划已具备提交条件" : "仍有待处理事项" }}</h2><p>新建 {{ dryRun.create_count }} 项；复用 {{ dryRun.reuse_count }} 项；待确认 {{ dryRun.pending_review_count }} 项；关系问题 {{ dryRun.invalid_relation_count }} 项。</p></div></div>
        <div class="message-panel" :class="dryRun.can_commit ? 'success-message' : 'error-message'"><CheckCircle2 :size="18" />{{ dryRun.messages.join("；") }}</div>
      </section>
    </template>
  </div>
</template>
