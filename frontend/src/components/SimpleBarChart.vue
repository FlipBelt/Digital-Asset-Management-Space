<script setup lang="ts">
import { computed } from "vue";
import type { ChartDatum } from "../lib/api";

const props = defineProps<{ data: ChartDatum[]; emptyText?: string }>();
const max = computed(() => Math.max(1, ...props.data.map((item) => item.value)));
</script>

<template>
  <div v-if="data.length" class="simple-chart" role="img" aria-label="数据条形图">
    <div v-for="item in data" :key="item.label" class="bar-row">
      <span class="bar-label" :title="item.label">{{ item.label }}</span>
      <div class="bar-track"><i :style="{ width: `${Math.max(3, item.value / max * 100)}%` }" /></div>
      <strong>{{ item.value }}</strong>
    </div>
  </div>
  <div v-else class="mini-empty">{{ emptyText ?? "暂无可视化数据" }}</div>
</template>
