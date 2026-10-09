<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Reports')" />

		<div class="flex flex-col gap-3 rounded-6 border border-outline-gray-1 bg-surface-base p-4">
			<Select v-model="templateId" :label="__('Report')" :options="templateOptions" />
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
				<JalaliDatePicker v-model="fromDate" :label="__('From')" />
				<JalaliDatePicker v-model="toDate" :label="__('Until')" />
				<Combobox v-model="workLocationId" :label="__('Work location')" :options="refOptions('work-locations')" />
				<Combobox v-model="departmentId" :label="__('Department')" :options="refOptions('departments')" />
				<Combobox v-model="employeeId" :label="__('Employee')" :options="refOptions('employees')" />
			</div>

			<!-- ad-hoc report (system admin) -->
			<div v-if="templateId === CUSTOM" class="flex flex-col gap-3 border-t border-outline-gray-1 pt-3">
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
					<Select v-model="spec.source" :label="__('Rows')" :options="sourceOptions" />
					<Select
						v-if="spec.source === 'daily'"
						v-model="spec.group_by"
						:label="__('Group by')"
						:options="groupOptions"
					/>
					<Select v-model="spec.time_unit" :label="__('Show times as')" :options="unitOptions" />
				</div>
				<div class="flex flex-col gap-2">
					<p class="text-sm font-medium">{{ __("Columns") }}</p>
					<div v-for="group in fieldGroups" :key="group.name">
						<p class="mb-1 text-xs text-ink-gray-5">{{ group.name }}</p>
						<div class="flex flex-wrap gap-1">
							<button
								v-for="f in group.fields"
								:key="f.key"
								type="button"
								class="rounded-full border px-3 py-1 text-xs"
								:class="
									spec.columns.includes(f.key)
										? 'border-outline-gray-5 bg-surface-gray-3 font-medium'
										: 'border-outline-gray-2 text-ink-gray-6'
								"
								@click="toggle(f.key)"
							>
								{{ f.label }}
							</button>
						</div>
					</div>
				</div>
				<div class="flex gap-2">
					<TextInput v-model="saveName" class="flex-1" :placeholder="__('Name to save this report')" />
					<Button :disabled="!saveName || !spec.columns.length" @click="saveTemplate">{{ __("Save as a report") }}</Button>
				</div>
			</div>

			<ErrorMessage :message="error" />
			<div class="flex flex-wrap gap-2">
				<Button variant="solid" icon-left="lucide-eye" :loading="busy === 'preview'" @click="preview">{{
					__("Show")
				}}</Button>
				<Button
					v-for="f in formats"
					:key="f.value"
					:icon-left="f.icon"
					:loading="busy === f.value"
					@click="exportAs(f.value)"
					>{{ f.label }}</Button
				>
			</div>
		</div>

		<div v-if="result" class="flex flex-col gap-2">
			<p class="text-sm text-ink-gray-5">
				{{ __("{0} rows · {1} to {2}", [fa(result.total_rows), display(result.from_date), display(result.to_date)]) }}
			</p>
			<div class="overflow-x-auto rounded-6 border border-outline-gray-1 bg-surface-base">
				<table class="w-full text-sm">
					<thead class="bg-surface-gray-1 text-ink-gray-5">
						<tr>
							<th v-for="c in result.columns" :key="c.key" class="whitespace-nowrap px-3 py-2 text-start font-medium">
								{{ c.label }}
							</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(row, i) in result.rows" :key="i" class="border-t border-outline-gray-1">
							<td v-for="c in result.columns" :key="c.key" class="hz-num whitespace-nowrap px-3 py-2">
								{{ cell(c, row[c.key]) }}
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { Button, Combobox, ErrorMessage, Select, TextInput, toast } from "frappe-ui"
import { computed, onMounted, reactive, ref, watch } from "vue"
import JalaliDatePicker from "@/components/JalaliDatePicker.vue"
import PageHeader from "@/components/PageHeader.vue"
import { api, download } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { display, fa, hm, monthLength } from "@/lib/jalali"
import { refOptions } from "@/lib/refs"
import { session } from "@/lib/session"

interface Template {
	id: number
	name: string
	default_range: string
}

interface CatalogField {
	key: string
	label: string
	group: string
	kind: string
}

interface Column {
	key: string
	label: string
	kind: string
}

interface Result {
	columns: Column[]
	rows: Record<string, unknown>[]
	total_rows: number
	from_date: string
	to_date: string
	time_unit: string
}

const CUSTOM = -1
const templates = ref<Template[]>([])
const templateId = ref<number>(CUSTOM)
const year = Number((session.today || "1405/01").slice(0, 4))
const month = Number((session.today || "1405/01").slice(5, 7))
const pad = (n: number) => String(n).padStart(2, "0")
const fromDate = ref<string | null>(`${year}/${pad(month)}/01`)
const toDate = ref<string | null>(`${year}/${pad(month)}/${pad(monthLength(year, month))}`)
const workLocationId = ref<number | null>(null)
const departmentId = ref<number | null>(null)
const employeeId = ref<number | null>(null)
const spec = reactive({ source: "summary", group_by: null as string | null, time_unit: "hours_minutes", columns: [] as string[] })
const fields = ref<CatalogField[]>([])
const saveName = ref("")
const result = ref<Result | null>(null)
const error = ref("")
const busy = ref("")

const templateOptions = computed(() => [
	...templates.value.map((t) => ({ value: t.id, label: t.name })),
	...(session.is_admin ? [{ value: CUSTOM, label: __("A new report…") }] : []),
])
const sourceOptions = [
	{ value: "summary", label: __("One row per person") },
	{ value: "daily", label: __("One row per day") },
]
const groupOptions = [
	{ value: "", label: __("No grouping") },
	{ value: "employee", label: __("Person") },
	{ value: "department", label: __("Department") },
	{ value: "day", label: __("Day") },
]
const unitOptions = [
	{ value: "hours_minutes", label: __("Hours:minutes") },
	{ value: "decimal_hours", label: __("Decimal hours") },
	{ value: "days", label: __("Days") },
]
const formats = [
	{ value: "excel", label: __("Excel"), icon: "lucide-sheet" },
	{ value: "pdf", label: __("PDF"), icon: "lucide-file-text" },
	{ value: "csv", label: __("Text (CSV)"), icon: "lucide-file-code" },
]

const fieldGroups = computed(() => {
	const groups = new Map<string, CatalogField[]>()
	for (const f of fields.value) groups.set(f.group, [...(groups.get(f.group) ?? []), f])
	return [...groups.entries()].map(([name, list]) => ({ name, fields: list }))
})

function toggle(key: string) {
	spec.columns = spec.columns.includes(key) ? spec.columns.filter((k) => k !== key) : [...spec.columns, key]
}

function body(exportFormat?: string) {
	return {
		template_id: templateId.value === CUSTOM ? null : templateId.value,
		spec:
			templateId.value === CUSTOM
				? { ...spec, group_by: spec.group_by || null, columns: spec.columns.map((field) => ({ field })) }
				: null,
		filters: {
			from_date: fromDate.value,
			to_date: toDate.value,
			work_location_id: workLocationId.value,
			department_id: departmentId.value,
			employee_id: employeeId.value,
		},
		export_format: exportFormat,
	}
}

function cell(c: Column, value: unknown): string {
	if (value === null || value === undefined) return ""
	if (c.kind === "minutes") {
		const unit = result.value?.time_unit
		if (unit === "decimal_hours") return fa((Number(value) / 60).toFixed(2))
		return hm(Number(value))
	}
	if (c.kind === "date") return display(String(value))
	return fa(String(value))
}

async function preview() {
	busy.value = "preview"
	error.value = ""
	try {
		result.value = await api.post<Result>("/reports/preview", body())
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

async function exportAs(format: string) {
	busy.value = format
	error.value = ""
	try {
		await download("/reports/export", body(format))
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

async function saveTemplate() {
	try {
		const t = await api.post<Template>("/admin/report-templates", {
			name: saveName.value,
			source: spec.source,
			group_by: spec.source === "daily" ? spec.group_by || null : null,
			time_unit: spec.time_unit,
			columns: spec.columns.map((field) => ({ field })),
		})
		templates.value = [...templates.value, t]
		templateId.value = t.id
		saveName.value = ""
		toast.success(__("Saved"))
	} catch (e) {
		toast.error((e as Error).message)
	}
}

watch(
	() => spec.source,
	async (source) => {
		fields.value = await api.get<CatalogField[]>("/reports/fields", { source })
		spec.columns = spec.columns.filter((k) => fields.value.some((f) => f.key === k))
	},
	{ immediate: true }
)

onMounted(async () => {
	try {
		templates.value = await api.get<Template[]>("/reports/templates")
		if (templates.value.length) templateId.value = templates.value[0].id
	} catch (e) {
		error.value = (e as Error).message
	}
})
</script>
