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
		<DataTable
			:columns="columns"
			:rows="rows"
			:search="search"
			:loading="loading"
			:storage-key="`resource.${def.name}`"
			@row-click="edit"
		>
			<template v-if="canWrite && def.name === 'work-pattern-assignments'" #toolbar>
				<Button icon-left="lucide-users" @click="bulkOpen = true">{{ __("Assign to several people") }}</Button>
			</template>
		</DataTable>
		<ResourceForm v-model:open="formOpen" :def="def" :row="current" :read-only="!canWrite" @saved="load" />
		<BulkAssignDialog v-if="def.name === 'work-pattern-assignments'" v-model:open="bulkOpen" @done="load" />
	</div>
	<p v-else class="text-ink-gray-5">{{ __("Not found") }}</p>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, TextInput } from "frappe-ui"
import { computed, ref, watch } from "vue"
import BulkAssignDialog from "@/components/BulkAssignDialog.vue"
import DataTable from "@/components/DataTable.vue"
import ExcelImport from "@/components/ExcelImport.vue"
import ResourceForm from "@/components/ResourceForm.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { hasImport } from "@/lib/imports"
import { display, fa } from "@/lib/jalali"
import { refLabel } from "@/lib/refs"
import { resourceDef, type FieldDef } from "@/lib/resources"
import { session } from "@/lib/session"
import type { ColumnType, TableColumn } from "@/lib/table"

const props = defineProps<{ resource: string }>()

const def = computed(() => resourceDef(props.resource))
const rows = ref<Record<string, unknown>[]>([])
const loading = ref(false)
const error = ref("")
const search = ref("")
const formOpen = ref(false)
const current = ref<Record<string, unknown> | null>(null)

const canWrite = computed(() => session.is_admin)
const bulkOpen = ref(false)

type Row = Record<string, unknown>

const TYPES: Partial<Record<FieldDef["type"], ColumnType>> = {
	number: "number",
	jdate: "date",
	bool: "bool",
	badge: "bool",
}

// sorting uses what people see for references and choices, the stored value for the rest
const columns = computed<TableColumn<Row>[]>(() =>
	(def.value?.fields.filter((f) => f.list) ?? []).map((f) => ({
		key: f.key,
		label: f.label,
		type: TYPES[f.type] ?? "text",
		value: f.type === "ref" || f.type === "select" ? (row: Row) => cell(f, row) : undefined,
		format: (row: Row) => cell(f, row),
		class: f.type === "textarea" ? "min-w-48" : "hz-num",
	}))
)

function cell(field: FieldDef, row: Record<string, unknown>): string {
	const value = row[field.key]
	if (value === null || value === undefined || value === "") return ""
	if (field.type === "bool" || field.type === "badge") return value ? "✓" : ""
	if (field.type === "jdate") return display(String(value))
	if (field.type === "ref") return fa(refLabel(field.ref!, value))
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
