<template>
	<div class="min-h-screen bg-surface-gray-1 text-ink-gray-8 md:flex">
		<!-- desktop: navigation on the start side (right, in RTL) -->
		<aside class="hidden w-60 shrink-0 border-e border-outline-gray-1 bg-surface-base md:flex md:flex-col">
			<div class="flex items-center gap-2 px-4 py-4">
				<span class="hz-brand flex size-9 items-center justify-center rounded-4 text-lg font-bold">C</span>
				<div class="min-w-0">
					<p class="truncate font-semibold">{{ __("Chronicle") }}</p>
					<p class="truncate text-xs text-ink-gray-5">{{ session.organization }}</p>
				</div>
			</div>
			<nav class="flex flex-1 flex-col gap-1 px-2">
				<RouterLink
					v-for="item in items"
					:key="item.name"
					:to="{ name: item.name }"
					class="flex items-center gap-3 rounded-4 px-3 py-2 text-sm"
					:class="
						isActive(item)
							? 'bg-surface-gray-3 font-medium text-ink-gray-9'
							: 'text-ink-gray-6 hover:bg-surface-gray-2'
					"
				>
					<span :class="item.icon" class="size-4" />
					<span class="flex-1">{{ item.label }}</span>
					<span v-if="item.count" class="hz-brand rounded-full px-2 text-xs">{{ fa(item.count) }}</span>
				</RouterLink>
			</nav>
			<div class="border-t border-outline-gray-1 p-2">
				<UserMenu />
			</div>
		</aside>

		<div class="flex min-w-0 flex-1 flex-col">
			<!-- mobile header -->
			<header
				class="sticky top-0 z-20 flex items-center gap-2 border-b border-outline-gray-1 bg-surface-base/95 px-4 py-3 backdrop-blur md:hidden"
			>
				<span class="hz-brand flex size-8 items-center justify-center rounded-4 font-bold">C</span>
				<p class="flex-1 truncate font-semibold">{{ title }}</p>
				<UserMenu compact />
			</header>

			<main class="mx-auto w-full max-w-3xl flex-1 px-4 pb-28 pt-4 md:pb-10 md:pt-8">
				<slot />
			</main>

			<!-- mobile bottom navigation -->
			<nav
				class="fixed inset-x-0 bottom-0 z-20 flex border-t border-outline-gray-1 bg-surface-base md:hidden"
				:style="{ paddingBottom: 'var(--hz-safe-bottom)' }"
			>
				<RouterLink
					v-for="item in items"
					:key="item.name"
					:to="{ name: item.name }"
					class="relative flex flex-1 flex-col items-center gap-1 py-2 text-[11px]"
					:class="isActive(item) ? 'font-medium text-ink-gray-9' : 'text-ink-gray-5'"
				>
					<span :class="item.icon" class="size-5" />
					<span>{{ item.label }}</span>
					<span
						v-if="item.count"
						class="hz-brand absolute top-1 min-w-[1.1rem] rounded-full px-1 text-center text-[10px] leading-4"
						style="inset-inline-start: calc(50% + 0.4rem)"
						>{{ fa(item.count) }}</span
					>
				</RouterLink>
			</nav>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from "vue"
import { useRoute } from "vue-router"
import { counts, refreshCounts } from "@/lib/counts"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import { session } from "@/lib/session"
import UserMenu from "./UserMenu.vue"

interface NavItem {
	name: string
	label: string
	icon: string
	match: string[]
	count?: number
}

const route = useRoute()

const items = computed<NavItem[]>(() => {
	const list: NavItem[] = [
		{ name: "today", label: __("Today"), icon: "lucide-clock-3", match: ["today"] },
		{ name: "month", label: __("Month"), icon: "lucide-calendar-days", match: ["month"] },
		{ name: "requests", label: __("Requests"), icon: "lucide-file-text", match: ["requests", "new-request"] },
		{
			name: "approvals",
			label: __("Approvals"),
			icon: "lucide-inbox",
			match: ["approvals", "delegations"],
			count: counts.approvals,
		},
	]
	if (session.is_admin || session.is_manager || session.is_ceo) {
		list.push({ name: "reports", label: __("Reports"), icon: "lucide-chart-column", match: ["reports"] })
	}
	if (session.is_admin) {
		list.push({
			name: "manage",
			label: __("Manage"),
			icon: "lucide-settings",
			match: [
				"manage",
				"resource",
				"organization",
				"employees",
				"employee",
				"new-employee",
				"chart",
				"calendar",
				"periods",
				"users",
				"settings",
				"approval-defaults",
				"audit",
				"devices",
				"device",
				"new-device",
			],
			count: counts.unmappedUsers,
		})
	}
	return list
})

function isActive(item: NavItem) {
	return item.match.includes(String(route.name))
}

const title = computed(() => items.value.find(isActive)?.label ?? __("Chronicle"))

onMounted(() => refreshCounts())
watch(
	() => route.name,
	() => refreshCounts()
)
</script>
