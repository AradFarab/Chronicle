import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router"
import { session } from "./lib/session"

const routes: RouteRecordRaw[] = [
  { path: "/", name: "today", component: () => import("./pages/Today.vue") },
  { path: "/month/:year(\\d+)?/:month(\\d+)?", name: "month", component: () => import("./pages/Month.vue") },
  { path: "/requests", name: "requests", component: () => import("./pages/Requests.vue") },
  { path: "/requests/new/:kind?", name: "new-request", component: () => import("./pages/NewRequest.vue") },
  { path: "/approvals", name: "approvals", component: () => import("./pages/Approvals.vue") },
  {
    path: "/devices",
    name: "devices",
    component: () => import("./pages/Devices.vue"),
    meta: { operator: true },
  },
  {
    path: "/devices/new",
    name: "new-device",
    component: () => import("./pages/DeviceForm.vue"),
    meta: { operator: true },
  },
  {
    path: "/devices/:name",
    name: "device",
    component: () => import("./pages/DeviceForm.vue"),
    props: true,
    meta: { operator: true },
  },
  { path: "/:pathMatch(.*)*", name: "not-found", component: () => import("./pages/NotFound.vue") },
]

export const router = createRouter({
  history: createWebHistory("/hozur"),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  if (to.meta.operator && !session.is_operator) return { name: "today" }
})
