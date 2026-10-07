import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router"
import { session } from "./lib/session"

const operator = { operator: true }
const admin = { admin: true }

const routes: RouteRecordRaw[] = [
  { path: "/login", name: "login", component: () => import("./pages/Login.vue"), meta: { public: true } },
  { path: "/", name: "today", component: () => import("./pages/Today.vue") },
  { path: "/month/:year(\\d+)?/:month(\\d+)?", name: "month", component: () => import("./pages/Month.vue") },
  { path: "/requests", name: "requests", component: () => import("./pages/Requests.vue") },
  { path: "/requests/new/:kind?", name: "new-request", component: () => import("./pages/NewRequest.vue") },
  { path: "/approvals", name: "approvals", component: () => import("./pages/Approvals.vue") },
  { path: "/account", name: "account", component: () => import("./pages/Account.vue") },
  { path: "/reports", name: "reports", component: () => import("./pages/Reports.vue") },
  // operators and admins
  { path: "/manage", name: "manage", component: () => import("./pages/Manage.vue"), meta: operator },
  {
    path: "/manage/:resource",
    name: "resource",
    component: () => import("./pages/ResourceList.vue"),
    props: true,
    meta: operator,
  },
  { path: "/manage/organization", name: "organization", component: () => import("./pages/Organization.vue"), meta: admin },
  { path: "/manage/calendar", name: "calendar", component: () => import("./pages/Calendar.vue"), meta: operator },
  { path: "/manage/periods", name: "periods", component: () => import("./pages/Periods.vue"), meta: operator },
  { path: "/manage/users", name: "users", component: () => import("./pages/Users.vue"), meta: admin },
  { path: "/manage/settings", name: "settings", component: () => import("./pages/Settings.vue"), meta: admin },
  { path: "/manage/approval-defaults", name: "approval-defaults", component: () => import("./pages/ApprovalDefaults.vue"), meta: admin },
  { path: "/manage/audit", name: "audit", component: () => import("./pages/Audit.vue"), meta: admin },
  { path: "/devices", name: "devices", component: () => import("./pages/Devices.vue"), meta: operator },
  { path: "/devices/new", name: "new-device", component: () => import("./pages/DeviceForm.vue"), meta: operator },
  {
    path: "/devices/:id(\\d+)",
    name: "device",
    component: () => import("./pages/DeviceForm.vue"),
    props: (route) => ({ id: Number(route.params.id) }),
    meta: operator,
  },
  { path: "/:pathMatch(.*)*", name: "not-found", component: () => import("./pages/NotFound.vue") },
]

export const router = createRouter({
  history: createWebHistory("/"),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  if (!to.meta.public && !session.user) return { name: "login", query: { next: to.fullPath } }
  if (to.meta.operator && !session.is_operator) return { name: "today" }
  if (to.meta.admin && !session.is_admin) return { name: "today" }
})
