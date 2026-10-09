import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router"
import { session } from "./lib/session"

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
  // delegation of approvals: managers, the CEO and the system admin (the server checks again)
  { path: "/delegations", name: "delegations", component: () => import("./pages/Delegations.vue"), meta: { delegates: true } },
  // the system admin
  { path: "/manage", name: "manage", component: () => import("./pages/Manage.vue"), meta: admin },
  {
    path: "/manage/:resource",
    name: "resource",
    component: () => import("./pages/ResourceList.vue"),
    props: true,
    meta: admin,
  },
  { path: "/manage/employees", name: "employees", component: () => import("./pages/Employees.vue"), meta: admin },
  { path: "/manage/employees/new", name: "new-employee", component: () => import("./pages/EmployeeForm.vue"), meta: admin },
  {
    path: "/manage/employees/:id(\\d+)",
    name: "employee",
    component: () => import("./pages/EmployeeForm.vue"),
    props: (route) => ({ id: Number(route.params.id) }),
    meta: admin,
  },
  { path: "/manage/chart", name: "chart", component: () => import("./pages/OrgChart.vue"), meta: admin },
  { path: "/manage/organization", name: "organization", component: () => import("./pages/Organization.vue"), meta: admin },
  { path: "/manage/calendar", name: "calendar", component: () => import("./pages/Calendar.vue"), meta: admin },
  { path: "/manage/periods", name: "periods", component: () => import("./pages/Periods.vue"), meta: admin },
  { path: "/manage/users", name: "users", component: () => import("./pages/Users.vue"), meta: admin },
  { path: "/manage/settings", name: "settings", component: () => import("./pages/Settings.vue"), meta: admin },
  { path: "/manage/approval-defaults", name: "approval-defaults", component: () => import("./pages/ApprovalDefaults.vue"), meta: admin },
  { path: "/manage/audit", name: "audit", component: () => import("./pages/Audit.vue"), meta: admin },
  { path: "/devices", name: "devices", component: () => import("./pages/Devices.vue"), meta: admin },
  { path: "/devices/new", name: "new-device", component: () => import("./pages/DeviceForm.vue"), meta: admin },
  {
    path: "/devices/:id(\\d+)",
    name: "device",
    component: () => import("./pages/DeviceForm.vue"),
    props: (route) => ({ id: Number(route.params.id) }),
    meta: admin,
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
  if (to.meta.delegates && !(session.is_admin || session.is_manager || session.is_ceo)) return { name: "today" }
  if (to.meta.admin && !session.is_admin) return { name: "today" }
})
