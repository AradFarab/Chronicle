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
import { resourceDef } from "@/lib/resources"

interface Item {
	label: string
	icon: string
	to: RouteLocationRaw
	count?: number
}

// the hub is for the system admin only (the router guards it too)
const resource = (name: string): Item => {
	const r = resourceDef(name)!
	return { label: r.title, icon: r.icon, to: { name: "resource", params: { resource: r.name } } }
}

const groups = computed(() => {
	const list: { title: string; items: Item[] }[] = [
		{
			title: __("Organization"),
			items: [
				{ label: __("Company"), icon: "lucide-landmark", to: { name: "organization" } },
				resource("work-locations"),
				resource("departments"),
				resource("designations"),
				{ label: __("Organization chart"), icon: "lucide-git-fork", to: { name: "chart" } },
				resource("designation-assignments"),
				{ label: __("Employees"), icon: "lucide-users", to: { name: "employees" } },
			],
		},
		{
			title: __("Work schedules"),
			items: [resource("shifts"), resource("work-patterns"), resource("work-pattern-assignments"), resource("shift-overrides")],
		},
		{ title: __("Rules"), items: [resource("rule-sets"), resource("leave-types")] },
		{
			title: __("Approvals"),
			items: [
				resource("approval-processes"),
				resource("approval-overrides"),
				{ label: __("Default approval per request type"), icon: "lucide-list-checks", to: { name: "approval-defaults" } },
				{ label: __("Delegation of approvals"), icon: "lucide-users-round", to: { name: "delegations" } },
			],
		},
		{
			title: __("Calendar and periods"),
			items: [
				{ label: __("Holidays and yearly refresh"), icon: "lucide-calendar-days", to: { name: "calendar" } },
				{ label: __("Monthly period lock"), icon: "lucide-lock", to: { name: "periods" } },
			],
		},
		{
			title: __("Devices"),
			items: [
				{
					label: __("Attendance devices"),
					icon: "lucide-fingerprint",
					to: { name: "devices" },
					count: counts.unmappedUsers,
				},
			],
		},
		{
			title: __("System"),
			items: [
				{ label: __("Users and roles"), icon: "lucide-user-round-cog", to: { name: "users" } },
				{ label: __("Settings"), icon: "lucide-sliders-horizontal", to: { name: "settings" } },
				{ label: __("Change history"), icon: "lucide-history", to: { name: "audit" } },
				{ label: __("Backups"), icon: "lucide-database-backup", to: { name: "backups" } },
			],
		},
	]
	return list
})
</script>
