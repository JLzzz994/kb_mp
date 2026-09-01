import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

import AppLayout from "@/components/layout/AppLayout.vue";
import { TOKEN_KEY } from "@/api/client";

const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: () => import("@/pages/LoginPage.vue"),
    meta: { public: true },
  },
  {
    path: "/",
    component: AppLayout,
    children: [
      { path: "", name: "dashboard", component: () => import("@/pages/DashboardPage.vue") },
      { path: "users", component: () => import("@/pages/UsersPage.vue") },
      { path: "roles", component: () => import("@/pages/RolesPage.vue") },
      { path: "departments", component: () => import("@/pages/DepartmentsPage.vue") },
      { path: "knowledge/import", component: () => import("@/pages/ImportPage.vue") },
      { path: "knowledge/units", component: () => import("@/pages/KnowledgeUnitsPage.vue") },
      { path: "chat", component: () => import("@/pages/ChatPage.vue") },
      { path: "faqs", component: () => import("@/pages/FaqsPage.vue") },
      { path: "gaps", component: () => import("@/pages/GapsPage.vue") },
      { path: "profile", component: () => import("@/pages/ProfilePage.vue") },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const authed = Boolean(localStorage.getItem(TOKEN_KEY));
  if (!to.meta.public && !authed) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.name === "login" && authed) {
    return "/";
  }
  return true;
});
