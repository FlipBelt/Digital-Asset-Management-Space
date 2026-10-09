import { computed, ref } from "vue";

export type ThemeId = "asset-center";
const theme = ref<ThemeId>("asset-center");
function applyTheme(value: ThemeId) {
  theme.value = value;
  document.documentElement.dataset.theme = value;
  localStorage.setItem("account-center-theme", value);
}
applyTheme("asset-center");
export function useTheme() {
  return { theme, label: computed(() => "资产中心统一设计"), applyTheme };
}
