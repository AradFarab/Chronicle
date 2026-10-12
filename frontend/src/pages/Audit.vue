<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Change history')" back="manage" />
		<div class="flex gap-2">
			<TextInput v-model="entity" dir="ltr" :placeholder="__('Table, e.g. employee')" @keyup.enter="load" />
			<TextInput v-model="entityId" dir="ltr" :placeholder="__('Record id')" @keyup.enter="load" />
			<Button @click="load">{{ __("Show") }}</Button>
		</div>
		<ErrorMessage :message="error" />
		<DataTable :columns="columns" :rows="entries" :loading="loading" storage-key="audit" @row-click="openEntry">
			<template #cell-action="{ row }"><Badge>{{ actionLabel(row.action) }}</Badge></template>
			<template #cell-entity="{ row }"><span dir="ltr" class="font-mono text-xs">{{ row.entity }}</span></template>
			<template #cell-entity_id="{ text }">
				<span dir="ltr" class="block max-w-48 truncate text-right font-mono text-xs" :title="text">{{ text }}</span>
			</template>
			<template #cell-reason="{ text }">
				<span class="line-clamp-2 min-w-40 max-w-72" :title="text">{{ text }}</span>
			</template>
			<template #cell-changed_fields="{ text }">
				<span dir="ltr" class="block max-w-64 truncate text-right font-mono text-xs" :title="text">{{ text }}</span>
			</template>
		</DataTable>

		<Dialog v-model:open="entryOpen" :title="current ? actionLabel(current.action) : ''" size="2xl">
			<div v-if="current" class="flex flex-col gap-3 text-sm">
				<p class="flex flex-wrap items-center gap-2">
					<span dir="ltr" class="font-mono text-xs">{{ current.entity }} #{{ current.entity_id }}</span>
					<span class="flex-1">{{ current.user || __("System") }}</span>
					<span class="hz-num text-xs text-ink-gray-5">{{ fa(current.at) }}</span>
				</p>
				<p v-if="current.reason">{{ __("Reason") }}: {{ current.reason }}</p>
				<div v-if="current.changed_fields.length" class="overflow-x-auto">
					<table class="w-full text-xs">
						<tr v-for="f in current.changed_fields" :key="f" class="border-t border-outline-gray-1">
							<td dir="ltr" class="py-1 pe-2 font-mono">{{ f }}</td>
							<td dir="ltr" class="py-1 pe-2 text-ink-red-4">{{ show(current.before?.[f]) }}</td>
							<td dir="ltr" class="py-1 text-ink-green-4">{{ show(current.after?.[f]) }}</td>
						</tr>
					</table>
				</div>
			</div>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, Dialog, ErrorMessage, TextInput } from "frappe-ui"
import { onMounted, ref } from "vue"
import DataTable from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import type { TableColumn } from "@/lib/table"

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
const loading = ref(false)
const entryOpen = ref(false)
const current = ref<Entry | null>(null)

const columns: TableColumn<Entry>[] = [
	{ key: "at", label: __("When"), type: "date", format: (e) => fa(e.at) },
	{ key: "action", label: __("Action"), value: (e) => actionLabel(e.action) },
	{ key: "entity", label: __("Table") },
	{ key: "entity_id", label: __("Record id"), type: "number", format: (e) => e.entity_id },
	{ key: "user", label: __("By"), value: (e) => e.user || __("System") },
	{ key: "reason", label: __("Reason") },
	{
		key: "changed_fields",
		label: __("Changed fields"),
		value: (e) => e.changed_fields.join(", "),
	},
]

function openEntry(e: Entry) {
	current.value = e
	entryOpen.value = true
}

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
	loading.value = true
	try {
		entries.value = await api.get<Entry[]>("/admin/audit", {
			entity: entity.value,
			entity_id: entityId.value,
			limit: 200,
		})
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
