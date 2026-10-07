<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Change history')" back="manage" />
		<div class="flex gap-2">
			<TextInput v-model="entity" dir="ltr" :placeholder="__('Table, e.g. employee')" @keyup.enter="load" />
			<TextInput v-model="entityId" dir="ltr" :placeholder="__('Record id')" @keyup.enter="load" />
			<Button @click="load">{{ __("Show") }}</Button>
		</div>
		<ErrorMessage :message="error" />
		<div class="flex flex-col gap-2">
			<details v-for="e in entries" :key="e.id" class="rounded-6 border border-outline-gray-1 bg-surface-base px-4 py-2">
				<summary class="flex cursor-pointer flex-wrap items-center gap-2 text-sm">
					<Badge>{{ actionLabel(e.action) }}</Badge>
					<span dir="ltr" class="font-mono text-xs">{{ e.entity }} #{{ e.entity_id }}</span>
					<span class="flex-1">{{ e.user || __("System") }}</span>
					<span class="hz-num text-xs text-ink-gray-5">{{ fa(e.at) }}</span>
				</summary>
				<p v-if="e.reason" class="mt-2 text-sm">{{ __("Reason") }}: {{ e.reason }}</p>
				<table v-if="e.changed_fields.length" class="mt-2 w-full text-xs">
					<tr v-for="f in e.changed_fields" :key="f" class="border-t border-outline-gray-1">
						<td dir="ltr" class="py-1 font-mono">{{ f }}</td>
						<td dir="ltr" class="py-1 text-ink-red-4">{{ show(e.before?.[f]) }}</td>
						<td dir="ltr" class="py-1 text-ink-green-4">{{ show(e.after?.[f]) }}</td>
					</tr>
				</table>
			</details>
		</div>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, ErrorMessage, TextInput } from "frappe-ui"
import { onMounted, ref } from "vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"

interface Entry {
	id: number
	entity: string
	entity_id: string
	action: string
	user: string | null
	at: string
	reason: string | null
	changed_fields: string[]
	before: Record<string, unknown> | null
	after: Record<string, unknown> | null
}

const entries = ref<Entry[]>([])
const entity = ref("")
const entityId = ref("")
const error = ref("")

function actionLabel(action: string) {
	return (
		{
			insert: __("Created"),
			update: __("Changed"),
			delete: __("Deleted"),
			submit: __("Submitted"),
			cancel: __("Cancelled"),
			approve: __("Approved"),
			reject: __("Rejected"),
			lock: __("Closed"),
			reopen: __("Reopened"),
			refresh: __("Refreshed"),
		}[action] ?? action
	)
}

function show(value: unknown): string {
	if (value === null || value === undefined) return "—"
	return typeof value === "object" ? JSON.stringify(value) : String(value)
}

async function load() {
	error.value = ""
	try {
		entries.value = await api.get<Entry[]>("/admin/audit", {
			entity: entity.value,
			entity_id: entityId.value,
			limit: 200,
		})
	} catch (e) {
		error.value = (e as Error).message
	}
}

onMounted(load)
</script>
