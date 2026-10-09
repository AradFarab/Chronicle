<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Default approval per request type')" back="manage" />
		<p class="text-sm text-ink-gray-6">
			{{ __("Which approval process each kind of request follows. Exceptions for one person are set under Approval exceptions.") }}
		</p>
		<ErrorMessage :message="error" />
		<div class="flex flex-col gap-3 rounded-6 border border-outline-gray-1 bg-surface-base p-4">
			<Select
				v-for="row in rows"
				:key="row.request_type"
				:model-value="row.process_id"
				:label="typeLabel(row.request_type)"
				:options="refOptions('approval-processes')"
				@update:model-value="(v) => v && save(row, Number(v))"
			/>
		</div>
	</div>
</template>

<script setup lang="ts">
import { ErrorMessage, Select, toast } from "frappe-ui"
import { onMounted, ref } from "vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { refOptions } from "@/lib/refs"
import { requestTypeOptions } from "@/lib/resources"

interface Row {
	request_type: string
	process_id: number | null
}

const rows = ref<Row[]>([])
const error = ref("")

function typeLabel(type: string) {
	if (type === "admin_entry") return __("Entered by the system admin for someone")
	return requestTypeOptions().find((o) => o.value === type)?.label ?? type
}

async function save(row: Row, processId: number) {
	try {
		await api.put(`/admin/approval-defaults/${row.request_type}`, { process_id: processId })
		row.process_id = processId
		toast.success(__("Saved"))
	} catch (e) {
		toast.error((e as Error).message)
	}
}

onMounted(async () => {
	try {
		rows.value = await api.get<Row[]>("/admin/approval-defaults")
	} catch (e) {
		error.value = (e as Error).message
	}
})
</script>
