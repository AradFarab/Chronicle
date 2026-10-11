<template>
	<Dialog v-model:open="open" :title="__('Give a work pattern to several people')" :size="picking ? '4xl' : 'xl'">
		<div class="flex flex-col gap-4">
			<!-- the people, when the page did not choose them already -->
			<div v-if="picking" class="flex flex-col gap-2">
				<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
					<TextInput v-model="search" :placeholder="__('Search')" />
					<Combobox
						v-model="departmentId"
						:options="refOptions('departments')"
						:placeholder="__('Every department')"
					/>
				</div>
				<DataTable
					v-model:selected="picked"
					:columns="peopleColumns"
					:rows="people"
					:search="search"
					:loading="peopleLoading"
					selectable
					scroll-class="max-h-72"
					@row-click="togglePerson"
				/>
			</div>

			<p class="hz-num flex items-center gap-2 text-sm" :class="ids.length ? 'text-ink-gray-7' : 'text-ink-amber-7'">
				<span class="lucide-users size-4" />
				{{ ids.length ? __("{0} people selected", [fa(ids.length)]) : __("No one is selected yet") }}
			</p>

			<Combobox
				v-model="form.work_pattern_id"
				:label="__('Work pattern') + ' *'"
				:options="refOptions('work-patterns')"
				:placeholder="__('Choose')"
			/>
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
				<JalaliDatePicker v-model="form.valid_from" :label="__('From') + ' *'" />
				<JalaliDatePicker v-model="form.valid_to" :label="__('Until')" clearable :min="form.valid_from" />
			</div>
			<div v-if="rotating" class="flex flex-col gap-1">
				<TextInput
					v-model="form.cycle_offset_days"
					type="number"
					dir="ltr"
					min="0"
					:label="__('Start the cycle later by (days)')"
				/>
				<p class="text-xs text-ink-gray-5">
					{{
						__(
							"For a rotating pattern: moves this group along the cycle by this many days, so two groups can follow one pattern half a cycle apart"
						)
					}}
				</p>
			</div>
			<Textarea v-model="form.note" :label="__('Note')" :rows="2" />
			<p class="text-xs text-ink-gray-5">
				{{ __("Everyone gets the pattern or no one does: if one of them cannot get it, nothing is saved.") }}
			</p>
			<ErrorMessage :message="error" />
		</div>
		<template #actions>
			<Button variant="solid" class="w-full sm:w-auto" :loading="busy" @click="save">{{
				ids.length ? __("Give it to {0} people", [fa(ids.length)]) : __("Save")
			}}</Button>
		</template>
	</Dialog>
</template>

<script setup lang="ts">
import { Button, Combobox, Dialog, ErrorMessage, Textarea, TextInput, toast } from "frappe-ui"
import { computed, reactive, ref, watch } from "vue"
import DataTable from "@/components/DataTable.vue"
import JalaliDatePicker from "@/components/JalaliDatePicker.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import { invalidateRef, refLabel, refOptions, refRows } from "@/lib/refs"
import { session } from "@/lib/session"
import type { TableColumn } from "@/lib/table"
import type { Employee } from "@/lib/types"

// Gives one work pattern to many employees in one go (POST /admin/work-pattern-assignments/bulk,
// all or nothing). Without `employeeIds` the dialog shows its own people picker.
const props = defineProps<{ employeeIds?: number[] }>()
const emit = defineEmits<{ done: [rows: Record<string, unknown>[]] }>()
const open = defineModel<boolean>("open", { default: false })

const form = reactive({
	work_pattern_id: null as number | null,
	valid_from: null as string | null,
	valid_to: null as string | null,
	cycle_offset_days: "0",
	note: "",
})
const error = ref("")
const busy = ref(false)

const picking = computed(() => !props.employeeIds)
const picked = ref<(string | number)[]>([])
const search = ref("")
const departmentId = ref<number | null>(null)
const employees = ref<Employee[]>([])
const peopleLoading = ref(false)

const ids = computed(() => (picking.value ? picked.value.map(Number) : props.employeeIds ?? []))
const rotating = computed(
	() => refRows("work-patterns").find((p) => p.id === form.work_pattern_id)?.pattern_type === "rotating"
)

// active people only; the department box narrows the list (the table's own filters work too)
const people = computed(() =>
	employees.value.filter(
		(e) => e.status === "active" && (!departmentId.value || e.department_id === departmentId.value)
	)
)
const peopleColumns: TableColumn<Employee>[] = [
	{ key: "code", label: __("Personnel code"), format: (e) => fa(e.code), class: "hz-num whitespace-nowrap" },
	{ key: "full_name", label: __("Name") },
	{ key: "department_id", label: __("Department"), value: (e) => refLabel("departments", e.department_id) },
	{
		key: "work_location_id",
		label: __("Work location"),
		value: (e) => refLabel("work-locations", e.work_location_id),
	},
]

function togglePerson(e: Employee) {
	picked.value = picked.value.includes(e.id) ? picked.value.filter((id) => id !== e.id) : [...picked.value, e.id]
}

async function loadPeople() {
	peopleLoading.value = true
	try {
		employees.value = await api.get<Employee[]>("/admin/employees")
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		peopleLoading.value = false
	}
}

watch(open, (value) => {
	if (!value) return
	error.value = ""
	Object.assign(form, {
		work_pattern_id: null,
		valid_from: session.today,
		valid_to: null,
		cycle_offset_days: "0",
		note: "",
	})
	if (picking.value) {
		picked.value = []
		search.value = ""
		departmentId.value = null
		loadPeople()
	}
})

async function save() {
	error.value = ""
	if (!ids.value.length) error.value = __("Choose at least one person")
	else if (!form.work_pattern_id) error.value = __("Choose the work pattern")
	else if (!form.valid_from) error.value = __("Choose the first day")
	if (error.value) return
	busy.value = true
	try {
		const rows = await api.post<Record<string, unknown>[]>("/admin/work-pattern-assignments/bulk", {
			employee_ids: ids.value,
			work_pattern_id: form.work_pattern_id,
			valid_from: form.valid_from,
			valid_to: form.valid_to || null,
			cycle_offset_days: rotating.value ? Number(form.cycle_offset_days) || 0 : null,
			note: form.note.trim() || null,
		})
		invalidateRef("work-pattern-assignments")
		toast.success(fa(__("The work pattern was given to {0} people", [rows.length])))
		open.value = false
		emit("done", rows)
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = false
	}
}
</script>
