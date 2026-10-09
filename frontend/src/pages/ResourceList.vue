<template>
	<div v-if="def" class="flex flex-col gap-4">
		<div class="flex items-center gap-2">
			<Button :aria-label="__('Back')" icon="lucide-arrow-right" :route="{ name: 'manage' }" />
			<h1 class="flex-1 text-xl font-semibold">{{ def.title }}</h1>
			<ExcelImport v-if="canWrite && hasImport(def.name)" :name="def.name" @done="load" />
			<Button v-if="canWrite" variant="solid" icon-left="lucide-plus" @click="edit(null)">{{ __("New") }}</Button>
		</div>
		<TextInput v-model="search" :placeholder="__('Search')" />
		<ErrorMessage :message="error" />
		<div class="overflow-x-auto rounded-6 border border-outline-gray-1 bg-surface-base">
			<table class="w-full text-sm">
				<thead class="bg-surface-gray-1 text-ink-gray-5">
					<tr>
						<th v-for="c in columns" :key="c.key" class="px-3 py-2 text-start font-medium">{{ c.label }}</th>
					</tr>
				</thead>
				<tbody>
					<tr
						v-for="row in filtered"
						:key="String(row.id)"
						class="cursor-pointer border-t border-outline-gray-1 hover:bg-surface-gray-1"
						@click="edit(row)"
					>
						<td v-for="c in columns" :key="c.key" class="hz-num px-3 py-2">{{ cell(c, row) }}</td>
					</tr>
					<tr v-if="!loading && !filtered.length">
						<td :colspan="columns.length" class="px-3 py-6 text-center text-ink-gray-5">{{ __("Nothing here yet") }}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<ResourceForm v-model:open="formOpen" :def="def" :row="current" :read-only="!canWrite" @saved="load" />
	</div>
	<p v-else class="text-ink-gray-5">{{ __("Not found") }}</p>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, TextInput } from "frappe-ui"
import { computed, ref, watch } from "vue"
import ExcelImport from "@/components/ExcelImport.vue"
import ResourceForm from "@/components/ResourceForm.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { hasImport } from "@/lib/imports"
import { display, fa } from "@/lib/jalali"
import { refLabel } from "@/lib/refs"
import { resourceDef, type FieldDef } from "@/lib/resources"
import { session } from "@/lib/session"

const props = defineProps<{ resource: string }>()

const def = computed(() => resourceDef(props.resource))
const rows = ref<Record<string, unknown>[]>([])
const loading = ref(false)
const error = ref("")
const search = ref("")
const formOpen = ref(false)
const current = ref<Record<string, unknown> | null>(null)

const canWrite = computed(() => session.is_admin)
const columns = computed(() => def.value?.fields.filter((f) => f.list) ?? [])

const filtered = computed(() => {
	const q = search.value.trim()
	if (!q) return rows.value
	return rows.value.filter((r) => columns.value.some((c) => cell(c, r).includes(q)))
})

function cell(field: FieldDef, row: Record<string, unknown>): string {
	const value = row[field.key]
	if (value === null || value === undefined || value === "") return ""
	if (field.type === "bool" || field.type === "badge") return value ? "✓" : ""
	if (field.type === "jdate") return display(String(value))
	if (field.type === "ref") return refLabel(field.ref!, value)
	if (field.type === "select") {
		const option = field.options?.().find((o) => o.value === value)
		return option ? option.label : String(value)
	}
	return fa(String(value))
}

function edit(row: Record<string, unknown> | null) {
	if (row?.is_legal_baseline) return // the law itself is read-only
	current.value = row
	formOpen.value = true
}

async function load() {
	if (!def.value) return
	loading.value = true
	error.value = ""
	try {
		rows.value = await api.get<Record<string, unknown>[]>(`/admin/${def.value.name}`)
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

watch(() => props.resource, load, { immediate: true })
</script>
