import { computed, ref } from "vue";

export type ThemeId = "boss-v4";

// The product has one visual language now. Keep the theme id in the composable
// so existing components remain compatible, but always start in the FlipBelt v4
// visual system instead of exposing a second user-facing mode.
const theme = ref<ThemeId>("boss-v4");

function applyTheme(value: ThemeId) {
  theme.value = value;
  document.documentElement.dataset.theme = value;
  localStorage.setItem("account-center-theme", value);
}

applyTheme("boss-v4");

export function useTheme() {
  const label = computed(() => "FlipBelt v4式");
  return { theme, label, applyTheme };
}
