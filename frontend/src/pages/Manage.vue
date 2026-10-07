<template>
	<div class="flex flex-col gap-6">
		<h1 class="text-xl font-semibold">{{ __("Manage") }}</h1>
		<section v-for="group in groups" :key="group.title" class="flex flex-col gap-2">
			<h2 class="text-sm font-medium text-ink-gray-5">{{ group.title }}</h2>
			<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
				<RouterLink
					v-for="item in group.items"
					:key="item.label"
					:to="item.to"
					class="flex items-center gap-3 rounded-6 border border-outline-gray-1 bg-surface-base px-4 py-3 hover:bg-surface-gray-1"
				>
					<span :class="item.icon" class="size-5 text-ink-gray-6" />
					<span class="flex-1 text-sm font-medium">{{ item.label }}</span>
					<span v-if="item.count" class="hz-brand rounded-full px-2 text-xs">{{ fa(item.count) }}</span>
					<span class="lucide-chevron-left size-4 text-ink-gray-4" />
				</RouterLink>
			</div>
		</section>
	</div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import type { RouteLocationRaw } from "vue-router"
import { counts } from "@/lib/counts"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import { RESOURCES } from "@/lib/resources"
import { session } from "@/lib/session"

interface Item {
	label: string
	icon: string
	to: RouteLocationRaw
	count?: number
}

const groups = computed(() => {
	const byGroup = new Map<string, Item[]>()
	const add = (group: string, item: Item) => byGroup.set(group, [...(byGroup.get(group) ?? []), item])
	if (session.is_admin) add(__("Organization"), { label: __("Company"), icon: "lucide-landmark", to: { name: "organization" } })
	for (const r of RESOURCES) {
		add(r.group, { label: r.title, icon: r.icon, to: { name: "resource", params: { resource: r.name } } })
	}
	add(__("Calendar and periods"), { label: __("Holidays and yearly refresh"), icon: "lucide-calendar-days", to: { name: "calendar" } })
	add(__("Calendar and periods"), { label: __("Monthly period lock"), icon: "lucide-lock", to: { name: "periods" } })
	add(__("Devices"), {
		label: __("Attendance devices"),
		icon: "lucide-fingerprint",
		to: { name: "devices" },
		count: counts.unmappedUsers,
	})
	if (session.is_admin) {
		add(__("Approvals"), { label: __("Default approval per request type"), icon: "lucide-list-checks", to: { name: "approval-defaults" } })
		add(__("System"), { label: __("Users and roles"), icon: "lucide-user-round-cog", to: { name: "users" } })
		add(__("System"), { label: __("Settings"), icon: "lucide-sliders-horizontal", to: { name: "settings" } })
		add(__("System"), { label: __("Change history"), icon: "lucide-history", to: { name: "audit" } })
	}
	return [...byGroup.entries()].map(([title, items]) => ({ title, items }))
})
</script>
