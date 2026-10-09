<script setup lang="ts">
import { assetStructureCategories } from "../lib/assetStructure";
</script>
<template>
  <details class="structure-guide">
    <summary>不知道选哪项？查看六类资料的填写说明</summary>
    <div class="structure-guide-body">
      <p>原来的 L1–L6 表示六类对象，各自回答一个问题。登记一项资产只需填写相关资料，不需要补齐六类，也不必按顺序建立。</p>
      <div class="structure-guide-list">
        <article v-for="item in assetStructureCategories" :key="item.value"><div><strong>{{ item.label }}</strong><small>L{{ item.value }} · {{ item.hint }}</small></div><div><span>例如：{{ item.example }}</span><p>{{ item.when }}</p></div><RouterLink :to="{ path:'/intake', query:{mode:item.mode} }" class="secondary-button">{{ item.value === 5 ? '分配使用权' : '登记' + item.label }}</RouterLink></article>
      </div>
      <p class="structure-example">例如：产品配色中台直接登记为“系统、订阅与资源 → 自研系统”，再确认负责人；有真实平台或管理账号时再补关联。缺少关联不需要创建占位对象。</p>
    </div>
  </details>
</template>
<style scoped>
.structure-guide { min-width:0; border:1px solid var(--border); border-radius:var(--radius); background:var(--surface); }
.structure-guide summary { padding:16px 20px; color:var(--text); font-weight:700; cursor:pointer; }
.structure-guide-body { display:grid; gap:16px; padding:0 20px 20px; }
.structure-guide-body > p { margin:0; color:var(--muted); line-height:1.7; }
.structure-guide-list article { display:grid; grid-template-columns:minmax(150px,.7fr) minmax(0,1.7fr) auto; gap:16px; align-items:center; padding:16px 0; border-top:1px solid var(--border); }
.structure-guide-list strong, .structure-guide-list small { display:block; }
.structure-guide-list small { margin-top:6px; color:var(--muted); }
.structure-guide-list p { margin:6px 0 0; color:var(--muted); line-height:1.6; }
.structure-guide-list > article > div { min-width:0; overflow-wrap:anywhere; }
.structure-guide .secondary-button { white-space:normal; text-align:center; }
.structure-example { padding:14px; border-radius:var(--radius); background:var(--surface-soft); }
@media(max-width:900px) { .structure-guide-list article { grid-template-columns:1fr; gap:10px; } .structure-guide .secondary-button { justify-self:start; } }
</style>
