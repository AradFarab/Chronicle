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
		<div class="overflow-x-auto rounded-6 border border-outline-gray-1 bg-surface-base">
			<table class="w-full text-sm">
				<thead class="bg-surface-gray-1 text-ink-gray-5">
					<tr>
						<th class="px-3 py-2 text-start font-medium">{{ __("Personnel code") }}</th>
						<th class="px-3 py-2 text-start font-medium">{{ __("Name") }}</th>
						<th class="px-3 py-2 text-start font-medium">{{ __("Department") }}</th>
						<th class="px-3 py-2 text-start font-medium">{{ __("Designations") }}</th>
						<th class="px-3 py-2 text-start font-medium">{{ __("Status") }}</th>
					</tr>
				</thead>
				<tbody>
					<tr
						v-for="e in filtered"
						:key="e.id"
						class="cursor-pointer border-t border-outline-gray-1 hover:bg-surface-gray-1"
						:class="e.status === 'active' ? '' : 'text-ink-gray-4'"
						@click="router.push({ name: 'employee', params: { id: e.id } })"
					>
						<td class="hz-num px-3 py-2" dir="ltr">{{ fa(e.code) }}</td>
						<td class="px-3 py-2">{{ e.full_name }}</td>
						<td class="px-3 py-2">{{ refLabel("departments", e.department_id) }}</td>
						<td class="px-3 py-2">{{ designationNames(e) }}</td>
						<td class="px-3 py-2">{{ statusText(e.status) }}</td>
					</tr>
					<tr v-if="!loading && !filtered.length">
						<td colspan="5" class="px-3 py-6 text-center text-ink-gray-5">{{ __("Nothing here yet") }}</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, TextInput } from "frappe-ui"
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import ExcelImport from "@/components/ExcelImport.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { hasImport } from "@/lib/imports"
import { fa } from "@/lib/jalali"
import { refLabel } from "@/lib/refs"
import { employeeStatusOptions, type EmployeeRow } from "@/lib/people"

const router = useRouter()
const rows = ref<EmployeeRow[]>([])
const loading = ref(false)
const error = ref("")
const search = ref("")

function designationNames(e: EmployeeRow): string {
	return e.designations
		.filter((d) => d.current)
		.map((d) => refLabel("designations", d.designation_id))
		.join("، ")
}

function statusText(status: string): string {
	return employeeStatusOptions().find((o) => o.value === status)?.label ?? status
}

const filtered = computed(() => {
	const q = search.value.trim()
	if (!q) return rows.value
	return rows.value.filter((e) =>
		[e.code, e.full_name, refLabel("departments", e.department_id), designationNames(e), statusText(e.status)].some((text) =>
			fa(text).includes(fa(q))
		)
	)
})

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
