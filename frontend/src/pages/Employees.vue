<template>
	<div class="flex flex-col gap-4">
		<div class="flex items-center gap-2">
			<Button :aria-label="__('Back')" icon="lucide-arrow-right" :route="{ name: 'manage' }" />
			<h1 class="flex-1 text-xl font-semibold">{{ __("Employees") }}</h1>
			<ExcelImport v-if="hasImport('employees')" name="employees" @done="load" />
			<Button variant="solid" icon-left="lucide-plus" :route="{ name: 'new-employee' }">{{ __("New") }}</Button>
		</div>
		<TextInput v-model="search" :placeholder="__('Search')" />
		<ErrorMessage :message="error" />
		<DataTable
			v-model:selected="selected"
			:columns="columns"
			:rows="rows"
			:search="search"
			:loading="loading"
			:row-class="(e) => (e.status === 'active' ? '' : 'text-ink-gray-4')"
			storage-key="employees"
			selectable
			@row-click="(e) => router.push({ name: 'employee', params: { id: e.id } })"
		>
			<template #toolbar>
				<Button icon-left="lucide-calendar-check" :disabled="!selected.length" @click="bulkOpen = true">{{
					__("Assign a work pattern ({0})", [fa(selected.length)])
				}}</Button>
			</template>
		</DataTable>
		<BulkAssignDialog v-model:open="bulkOpen" :employee-ids="selected.map(Number)" @done="selected = []" />
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, TextInput } from "frappe-ui"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import BulkAssignDialog from "@/components/BulkAssignDialog.vue"
import DataTable from "@/components/DataTable.vue"
import ExcelImport from "@/components/ExcelImport.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { hasImport } from "@/lib/imports"
import { fa } from "@/lib/jalali"
import { refLabel } from "@/lib/refs"
import { employeeStatusOptions, type EmployeeRow } from "@/lib/people"
import type { TableColumn } from "@/lib/table"

const router = useRouter()
const rows = ref<EmployeeRow[]>([])
const loading = ref(false)
const error = ref("")
const search = ref("")
const selected = ref<(string | number)[]>([])
const bulkOpen = ref(false)

function designationNames(e: EmployeeRow): string {
	return e.designations
		.filter((d) => d.current)
		.map((d) => refLabel("designations", d.designation_id))
		.join("، ")
}

function statusText(status: string): string {
	return employeeStatusOptions().find((o) => o.value === status)?.label ?? status
}

const columns: TableColumn<EmployeeRow>[] = [
	{ key: "code", label: __("Personnel code"), format: (e) => fa(e.code), class: "hz-num whitespace-nowrap" },
	{ key: "full_name", label: __("Name") },
	{ key: "department_id", label: __("Department"), value: (e) => refLabel("departments", e.department_id) },
	{
		key: "work_location_id",
		label: __("Work location"),
		value: (e) => refLabel("work-locations", e.work_location_id),
	},
	{ key: "designations", label: __("Designations"), value: designationNames },
	{ key: "status", label: __("Status"), value: (e) => statusText(e.status) },
]

async function load() {
	loading.value = true
	error.value = ""
	try {
		rows.value = await api.get<EmployeeRow[]>("/admin/employees")
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
