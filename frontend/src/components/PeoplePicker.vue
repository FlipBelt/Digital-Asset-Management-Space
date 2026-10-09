<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { Department, Person } from "../lib/api";
import { findSelectablePeople, togglePersonSelection } from "../lib/peopleSelection";

const props = withDefaults(defineProps<{
  id: string; label: string; people: Person[]; departments: Department[];
  personId?: string | null; personIds?: string[]; multiple?: boolean;
  excludedIds?: string[]; disabled?: boolean; hint?: string;
}>(), { multiple: false, disabled: false });
const emit = defineEmits<{
  "update:personId": [value: string | null];
  "update:personIds": [value: string[]];
}>();
const query = ref("");
const department = ref("");
const selectedIds = computed(() => props.multiple ? props.personIds ?? [] : props.personId ? [props.personId] : []);
const departmentNames = computed(() => Object.fromEntries(props.departments.map(item => [item.id, item.name])));
const availableDepartments = computed(() => props.departments.filter(item => props.people.some(person => person.department_id === item.id)));
watch(availableDepartments, rows => {
  if (department.value && !rows.some(row => row.id === department.value)) department.value = "";
});
const matches = computed(() => findSelectablePeople(props.people, props.departments, query.value, department.value, props.excludedIds));
const visible = computed(() => matches.value.slice(0, 20));
function name(id: string) {
  const person = props.people.find(person => person.id === id);
  if (!person) return "原已选人员（当前列表不可用）";
  const team = departmentNames.value[person.department_id ?? ""];
  return team ? `${person.display_name} · ${team}` : person.display_name;
}
function select(id: string, checked: boolean) {
  if (props.disabled) return;
  if (props.multiple) emit("update:personIds", togglePersonSelection(selectedIds.value, id, checked));
  else emit("update:personId", checked ? id : null);
}
function remove(id: string) { select(id, false); }
</script>

<template>
  <fieldset class="people-picker" :disabled="disabled">
    <legend>{{ label }}<span>{{ multiple ? `已选 ${selectedIds.length} 人` : '单选' }}</span></legend>
    <div v-if="selectedIds.length" class="people-selected" :aria-label="label + '已选人员'">
      <button v-for="id in selectedIds" :key="id" type="button" :disabled="disabled" :aria-label="'移除' + name(id)" @click="remove(id)">{{ name(id) }}<span aria-hidden="true">×</span></button>
    </div>
    <p v-else class="people-selection-empty">{{ multiple ? '尚未选择协同人员，可留空。' : '尚未选择人员。' }}</p>
    <div class="people-search">
      <input :id="id + '-search'" v-model="query" type="search" :aria-label="label + '：搜索姓名、工号或部门'" placeholder="搜索姓名、工号或部门" autocomplete="off" :disabled="disabled" />
      <select v-if="availableDepartments.length > 1" v-model="department" :aria-label="label + '：筛选部门'" :disabled="disabled"><option value="">全部部门</option><option v-for="item in availableDepartments" :key="item.id" :value="item.id">{{ item.name }}</option></select>
    </div>
    <div class="people-results" :aria-label="label + '候选人员'">
      <label v-for="person in visible" :key="person.id" class="people-option">
        <input :type="multiple ? 'checkbox' : 'radio'" :name="id" :checked="selectedIds.includes(person.id)" :disabled="disabled" @change="select(person.id, ($event.target as HTMLInputElement).checked)" />
        <span><strong>{{ person.display_name }}</strong><small>{{ departmentNames[person.department_id ?? ''] || '未设置部门' }}<template v-if="person.employee_no"> · {{ person.employee_no }}</template></small></span>
      </label>
      <p v-if="!matches.length" class="people-no-results" role="status">没有匹配的在职人员，请调整搜索或部门筛选。</p>
    </div>
    <small class="people-hint">{{ hint || (multiple ? '勾选即可添加，点击上方已选人员可移除。' : '选择一名人员，可随时搜索更换。') }}<template v-if="matches.length > visible.length"> 匹配 {{ matches.length }} 人，当前显示前 20 人，请输入更具体的关键词。</template></small>
  </fieldset>
</template>

<style scoped>
.people-picker { display:grid; min-width:0; margin:0; padding:0; border:0; gap:12px; }
.people-picker legend { width:100%; margin-bottom:12px; padding:0; color:var(--text); font-size:13px; font-weight:700; }
.people-picker legend span { margin-left:10px; color:var(--muted); font-size:12px; font-weight:400; }
.people-search { display:flex; flex-wrap:wrap; gap:10px; }
.people-search input { flex:1 1 220px; min-width:0; }
.people-search select { flex:0 1 200px; min-width:0; }
.people-picker .people-search input, .people-picker .people-search select { width:100%; min-height:42px; padding:10px 12px; border:1px solid var(--border); border-radius:var(--radius); color:var(--text); background:var(--surface); }
.people-selected { display:flex; flex-wrap:wrap; gap:8px; }
.people-selected button { display:inline-flex; max-width:100%; align-items:center; gap:10px; padding:8px 10px; border:1px solid var(--border); border-radius:var(--radius); color:var(--text); background:var(--surface-soft); overflow-wrap:anywhere; cursor:pointer; }
.people-selection-empty { margin:0; color:var(--muted); font-size:12px; }
.people-results { max-height:260px; overflow:auto; border:1px solid var(--border); border-radius:var(--radius); background:var(--surface); }
.people-picker .people-option { display:flex; align-items:center; gap:12px; min-height:52px; margin:0; padding:10px 12px; cursor:pointer; }
.people-option + .people-option { border-top:1px solid var(--border); }
.people-picker .people-option input { flex:none; width:18px; height:18px; min-height:0; margin:0; padding:0; accent-color:var(--primary); }
.people-option > span { min-width:0; overflow-wrap:anywhere; }
.people-option strong, .people-option small { display:block; }
.people-option strong { color:var(--text); font-size:13px; }
.people-option small, .people-hint, .people-no-results { color:var(--muted); font-size:12px; line-height:1.6; }
.people-no-results { margin:0; padding:16px; }
.people-picker :focus-visible { outline:2px solid var(--primary); outline-offset:3px; }
.people-picker:disabled { opacity:.65; }
@media(max-width:600px) { .people-search input, .people-search select { flex-basis:100%; } }
</style>
