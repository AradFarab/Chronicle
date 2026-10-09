<template>
	<Dialog v-model:open="open" :title="mode === 'give' ? __('Give a designation') : __('Take the designation away')">
		<div class="flex flex-col gap-4">
			<template v-if="mode === 'give'">
				<p v-if="summary" class="text-sm text-ink-gray-6">{{ summary }}</p>
				<Combobox
					v-if="!employeeId"
					v-model="form.employee_id"
					:label="__('Employee') + ' *'"
					:options="refOptions('employees')"
					:placeholder="__('Choose')"
				/>
				<Combobox
					v-if="!designationId"
					v-model="form.designation_id"
					:label="__('Designation') + ' *'"
					:options="refOptions('designations')"
					:placeholder="__('Choose')"
				/>
				<JalaliDatePicker v-model="form.valid_from" :label="__('From') + ' *'" />
				<JalaliDatePicker v-model="form.valid_to" :label="__('Until')" />
				<Textarea v-model="form.note" :label="__('Note')" :rows="2" />
			</template>
			<template v-else>
				<p v-if="summary" class="text-sm text-ink-gray-6">{{ summary }}</p>
				<JalaliDatePicker v-model="form.valid_to" :label="__('Until') + ' *'" />
				<p class="text-xs text-ink-gray-5">{{ __("The history stays; the designation simply ends on this day.") }}</p>
			</template>
			<ErrorMessage :message="error" />
		</div>
		<template #actions>
			<Button variant="solid" :loading="busy" @click="save">{{ __("Save") }}</Button>
		</template>
	</Dialog>
</template>

<script setup lang="ts">
import { Button, Combobox, Dialog, ErrorMessage, Textarea, toast } from "frappe-ui"
import { reactive, ref, watch } from "vue"
import JalaliDatePicker from "@/components/JalaliDatePicker.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { invalidateRef, refOptions } from "@/lib/refs"
import { session } from "@/lib/session"

// give: adds a row to the designation history; take: sets the end date of an existing row.
const props = defineProps<{
	mode: "give" | "take"
	employeeId?: number | null // fixed when given (otherwise a picker is shown)
	designationId?: number | null
	assignmentId?: number | null // take only
	summary?: string
}>()
const emit = defineEmits<{ saved: [] }>()
const open = defineModel<boolean>("open", { default: false })

const form = reactive({
	employee_id: null as number | null,
	designation_id: null as number | null,
	valid_from: null as string | null,
	valid_to: null as string | null,
	note: "",
})
const error = ref("")
const busy = ref(false)

watch(open, (value) => {
	if (!value) return
	error.value = ""
	Object.assign(form, {
		employee_id: props.employeeId ?? null,
		designation_id: props.designationId ?? null,
		valid_from: session.today,
		valid_to: props.mode === "take" ? session.today : null,
		note: "",
	})
})

async function save() {
	busy.value = true
	error.value = ""
	try {
		if (props.mode === "give") {
			await api.post("/admin/designation-assignments", {
				employee_id: form.employee_id,
				designation_id: form.designation_id,
				valid_from: form.valid_from,
				valid_to: form.valid_to,
				note: form.note || null,
			})
		} else {
			await api.patch(`/admin/designation-assignments/${props.assignmentId}`, { valid_to: form.valid_to })
		}
		invalidateRef("employees")
		invalidateRef("designation-assignments")
		toast.success(__("Saved"))
		open.value = false
		emit("saved")
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = false
	}
}
</script>
