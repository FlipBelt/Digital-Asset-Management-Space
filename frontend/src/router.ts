import { createRouter, createWebHistory } from "vue-router";

import AdminPage from "./pages/AdminPage.vue";
import AccountsPage from "./pages/AccountsPage.vue";
import AssetMapPage from "./pages/AssetMapPage.vue";
import AssetsPage from "./pages/AssetsPage.vue";
import AssetDetailPage from "./pages/AssetDetailPage.vue";
import DashboardPage from "./pages/DashboardPage.vue";
import DirectoryDetailPage from "./pages/DirectoryDetailPage.vue";
import DepartmentAssetsPage from "./pages/DepartmentAssetsPage.vue";
import GovernancePage from "./pages/GovernancePage.vue";
import ImportWorkbenchPage from "./pages/ImportWorkbenchPage.vue";
import IntakePage from "./pages/IntakePage.vue";
import MyUsagePage from "./pages/MyUsagePage.vue";
import OrganizationPage from "./pages/OrganizationPage.vue";
import PlatformUsageDetailPage from "./pages/PlatformUsageDetailPage.vue";
import UsageMonitoringPage from "./pages/UsageMonitoringPage.vue";
import ServicesPage from "./pages/ServicesPage.vue";
import ScenarioWorkspacePage from "./pages/ScenarioWorkspacePage.vue";
import HuduWorkspacePage from "./pages/HuduWorkspacePage.vue";
import HuduAssetDetailPage from "./pages/HuduAssetDetailPage.vue";
import HuduExpirationsPage from "./pages/HuduExpirationsPage.vue";
import HuduIntakePage from "./pages/HuduIntakePage.vue";
import LoginPage from "./pages/LoginPage.vue";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: "/", name: "dashboard", component: DashboardPage },
    { path: "/login", name: "login", component: LoginPage },
    { path: "/hudu", name: "hudu-workspace", component: HuduWorkspacePage },
    { path: "/hudu/assets/:id", name: "hudu-asset-detail", component: HuduAssetDetailPage },
    { path: "/hudu/expirations", name: "hudu-expirations", component: HuduExpirationsPage },
    { path: "/hudu/intake", name: "hudu-intake", component: HuduIntakePage },
    { path: "/my", name: "my-usage", component: MyUsagePage },
    { path: "/department", name: "department-assets", component: DepartmentAssetsPage },
    { path: "/map", name: "asset-map", component: AssetMapPage },
    { path: "/intake", name: "intake", component: IntakePage },
    { path: "/imports", name: "imports", component: ImportWorkbenchPage },
    { path: "/assets", name: "assets", component: AssetsPage },
    { path: "/assets/:id", name: "asset-detail", component: AssetDetailPage },
    { path: "/directory/:kind(entity|platform|grant)/:id", name: "directory-detail", component: DirectoryDetailPage },
    { path: "/accounts", name: "accounts", component: AccountsPage },
    { path: "/organization", name: "organization", component: OrganizationPage },
    { path: "/services", name: "services", component: ServicesPage },
    { path: "/scenarios", name: "scenarios", component: ScenarioWorkspacePage },
    { path: "/services/alerts", name: "usage-monitoring", component: UsageMonitoringPage },
    { path: "/services/:platformCode(deepseek|minimax|aliyun)", name: "platform-usage-detail", component: PlatformUsageDetailPage },
    { path: "/governance", name: "governance", component: GovernancePage },
    { path: "/admin", name: "admin", component: AdminPage },
  ],
});

export default router;
