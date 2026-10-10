<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import type { CurrentUser } from "../lib/api";
import { managementItems, managementSection } from "../lib/managementWorkspace";
const props = defineProps<{ user: CurrentUser }>();
const route = useRoute();
const items = computed(() => managementItems(props.user));
const active = computed(() => managementSection(route.path, route.query));
</script>
<template>
  <div class="management-navigation">
    <nav class="management-nav-links" aria-label="公司资产管理事项">
      <RouterLink v-for="item in items" :key="item.key" :to="item.to" active-class="" exact-active-class=""
        :class="{ 'is-current': active === item.key }" :aria-current="active === item.key ? 'page' : undefined">{{ item.label }}</RouterLink>
    </nav>
  </div>
</template>
