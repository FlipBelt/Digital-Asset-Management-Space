<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { Link2, Plus, Trash2 } from "lucide-vue-next";

import StatusBadge from "./StatusBadge.vue";
import { api, type AssetFieldDefinition, type AssetType, type RelationDefinition } from "../lib/api";

const props = defineProps<{ types: AssetType[] }>();
const selectedTypeId = ref("");
const fields = ref<AssetFieldDefinition[]>([]);
const definitions = ref<RelationDefinition[]>([]);
const saving = ref(false);
const message = ref("");
const error = ref("");
const fieldForm = reactive({
  field_key: "", label: "", data_type: "text", is_required: false, group_name: "基础信息",
  help_text: "", unit: "", options_text: "", confidentiality: "internal", is_searchable: false,
  completeness_weight: 0, sort_order: 0,
  entry_visibility: "optional", requirement_stage: "optional", applies_to_existing: false,
});
const relationForm = reactive({
  relation_type: "", source_type_code: "", target_type_code: "", forward_label: "", inverse_label: "",
  category: "upstream", source_max_count: "", target_max_count: "",
});

const selectedType = computed(() => props.types.find((item) => item.id === selectedTypeId.value));
const typeCodes = computed(() => props.types.map((item) => item.code).sort());

async function loadFields() {
  fields.value = selectedTypeId.value ? await api.assetFields(selectedTypeId.value) : [];
}
async function load() {
  selectedTypeId.value ||= props.types[0]?.id ?? "";
  await Promise.all([loadFields(), api.relationDefinitions().then((rows) => { definitions.value = rows; })]);
}
async function addField() {
  if (!selectedTypeId.value) return;
  saving.value = true; error.value = "";
  try {
    const options = fieldForm.options_text.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean);
    await api.createAssetField(selectedTypeId.value, {
      ...fieldForm, options: options.length ? options : null,
      help_text: fieldForm.help_text || null, unit: fieldForm.unit || null,
    });
    Object.assign(fieldForm, { field_key: "", label: "", data_type: "text", is_required: false, group_name: "基础信息", help_text: "", unit: "", options_text: "", confidentiality: "internal", is_searchable: false, completeness_weight: 0, sort_order: fields.value.length + 1, entry_visibility: "optional", requirement_stage: "optional", applies_to_existing: false });
    await loadFields(); message.value = "字段模板已添加";
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "字段保存失败"; }
  finally { saving.value = false; }
}
async function archiveField(item: AssetFieldDefinition) {
  if (!selectedTypeId.value || !confirm(`归档字段“${item.label}”？已有数据将保留。`)) return;
  await api.archiveAssetField(selectedTypeId.value, item.id); await loadFields(); message.value = "字段已归档";
}
async function addRelation() {
  saving.value = true; error.value = "";
  try {
    await api.createRelationDefinition({
      ...relationForm,
      source_max_count: relationForm.source_max_count ? Number(relationForm.source_max_count) : null,
      target_max_count: relationForm.target_max_count ? Number(relationForm.target_max_count) : null,
    });
    Object.assign(relationForm, { relation_type: "", source_type_code: "", target_type_code: "", forward_label: "", inverse_label: "", category: "upstream", source_max_count: "", target_max_count: "" });
    definitions.value = await api.relationDefinitions(); message.value = "关系规则已添加";
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "关系规则保存失败"; }
  finally { saving.value = false; }
}
watch(selectedTypeId, () => { void loadFields(); });
watch(() => props.types, () => { void load(); }, { deep: true });
onMounted(load);
</script>

<template>
  <div class="panel-heading"><div><h2>分类、字段与关系规则</h2><p>类型决定内部编号前缀；字段模板和关系规则不再散落在资产详情页。</p></div></div>
  <p v-if="message" class="message-panel success-message">{{ message }}</p><p v-if="error" class="message-panel error-message">{{ error }}</p>
  <div class="rule-grid">
    <section class="rule-card"><div class="panel-heading"><div><h3>专属资料字段模板</h3><p>按资产类型配置。新增字段会立即出现在该类型的“专属资料”中。</p></div></div>
      <label><span>资产类型</span><select v-model="selectedTypeId"><option v-for="item in props.types" :key="item.id" :value="item.id">{{ item.name }} · {{ item.code_prefix }}</option></select></label>
      <div v-if="selectedType" class="type-summary"><strong>{{ selectedType.code_prefix }}-序号</strong><span>默认归属：{{ selectedType.ownership_default }}</span></div>
      <div class="template-list"><div v-for="item in fields" :key="item.id"><span><strong>{{ item.label }}</strong><small>{{ item.group_name }} · {{ item.data_type }} · {{ item.entry_visibility === 'core' ? '核心区' : item.entry_visibility === 'advanced' ? '高级区' : item.entry_visibility === 'conditional' ? '条件显示' : '补充区' }} · {{ item.requirement_stage === 'create' ? '创建时必填' : item.requirement_stage === 'activation' ? '启用前补充' : '按需补充' }}</small></span><button class="icon-button danger" title="归档字段" @click="archiveField(item)"><Trash2 :size="15" /></button></div><div v-if="!fields.length" class="mini-empty">该类型尚无专属字段模板</div></div>
      <form class="compact-form" @submit.prevent="addField"><input v-model="fieldForm.field_key" required placeholder="字段编码，如 instance_id" /><input v-model="fieldForm.label" required placeholder="显示名称，如 ECS 实例 ID" /><select v-model="fieldForm.data_type"><option value="text">文本</option><option value="textarea">多行文本</option><option value="number">数字</option><option value="date">日期</option><option value="boolean">是/否</option></select><input v-model="fieldForm.group_name" required placeholder="字段分组" /><select v-model="fieldForm.entry_visibility"><option value="optional">补充区（默认折叠）</option><option value="core">核心区</option><option value="advanced">高级区</option><option value="conditional">条件显示</option></select><select v-model="fieldForm.requirement_stage"><option value="optional">按需补充</option><option value="activation">正式启用前补充</option><option value="create">创建时必填</option></select><input v-model="fieldForm.options_text" placeholder="选项，逗号分隔（可选）" /><input v-model="fieldForm.help_text" placeholder="填写提示（可选）" /><label class="check-label"><input v-model="fieldForm.applies_to_existing" type="checkbox" />追溯已有数据</label><label class="check-label"><input v-model="fieldForm.is_searchable" type="checkbox" />可检索</label><button class="secondary-button" :disabled="saving"><Plus :size="15" />添加字段</button></form>
    </section>
    <section class="rule-card"><div class="panel-heading"><div><h3><Link2 :size="17" />关系白名单</h3><p>只允许符合对象类型的上游、下游或平级关系，详情页据此过滤目标和关系名。</p></div></div>
      <div class="template-list relation-list"><div v-for="item in definitions" :key="item.id"><span><strong>{{ item.source_type_code }} → {{ item.target_type_code }}</strong><small>{{ item.forward_label }} / {{ item.inverse_label }} · {{ item.category }}</small></span><StatusBadge :tone="item.is_system ? 'success' : 'default'">{{ item.is_system ? '系统规则' : '自定义' }}</StatusBadge></div></div>
      <form class="compact-form relation-form" @submit.prevent="addRelation"><input v-model="relationForm.relation_type" required placeholder="关系编码，如 DEPLOYED_ON" /><select v-model="relationForm.source_type_code" required><option value="" disabled>源类型</option><option v-for="code in typeCodes" :key="code" :value="code">{{ code }}</option></select><select v-model="relationForm.target_type_code" required><option value="" disabled>目标类型</option><option v-for="code in typeCodes" :key="code" :value="code">{{ code }}</option></select><input v-model="relationForm.forward_label" required placeholder="源侧名称，如 部署在" /><input v-model="relationForm.inverse_label" required placeholder="目标侧名称，如 承载" /><select v-model="relationForm.category"><option value="upstream">上下游</option><option value="peer">平级</option></select><input v-model="relationForm.source_max_count" inputmode="numeric" placeholder="源侧上限（可选）" /><button class="secondary-button" :disabled="saving"><Plus :size="15" />添加规则</button></form>
    </section>
  </div>
</template>

<style scoped>
.rule-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 18px; }
.rule-card { display: grid; align-content: start; gap: 12px; min-width: 0; padding: 17px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-soft); }
.rule-card h3 { display: flex; align-items: center; gap: 7px; margin: 0; font-size: 14px; }.rule-card p { margin: 5px 0 0; color: var(--muted); font-size: 10px; line-height: 1.6; }
.rule-card label > span { display: block; margin-bottom: 6px; color: var(--muted); font-size: 10px; font-weight: 700; }.rule-card select, .rule-card input { width: 100%; min-height: 36px; padding: 7px 9px; font-size: 11px; }
.type-summary { display: flex; align-items: center; justify-content: space-between; padding: 10px; border-radius: 7px; background: var(--surface); }.type-summary strong { color: var(--primary); font-size: 12px; }.type-summary span { color: var(--muted); font-size: 10px; }
.template-list { display: grid; max-height: 232px; overflow: auto; border: 1px solid var(--border); border-radius: 7px; background: var(--surface); }.template-list > div { display: flex; min-height: 45px; align-items: center; justify-content: space-between; gap: 8px; padding: 7px 9px; border-top: 1px solid var(--border); }.template-list > div:first-child { border-top: 0; }.template-list strong, .template-list small { display: block; }.template-list strong { font-size: 11px; }.template-list small { margin-top: 3px; color: var(--muted); font-size: 9px; }
.compact-form { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }.compact-form button { justify-content: center; }.compact-form .check-label { min-height: 36px; padding: 0 4px; }.relation-form { grid-template-columns: 1fr 1fr; }.relation-list { max-height: 280px; }
@media (max-width: 1120px) { .rule-grid { grid-template-columns: 1fr; } }
</style>
