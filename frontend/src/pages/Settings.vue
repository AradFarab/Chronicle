<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Settings')" back="manage" />
		<form class="flex flex-col gap-4 rounded-6 border border-outline-gray-1 bg-surface-base p-4" @submit.prevent="save">
			<TextInput
				v-model.number="values.dedup_window_seconds"
				type="number"
				dir="ltr"
				:label="__('Punches closer than this are duplicates (seconds)')"
			/>
			<TextInput
				v-model.number="values.clock_drift_warning_seconds"
				type="number"
				dir="ltr"
				:label="__('Warn when a device clock is off by more than (seconds)')"
			/>
			<TextInput
				v-model.number="values.absence_warning_days"
				type="number"
				dir="ltr"
				:label="__('Warn after this many absent days in a row (0 = never)')"
				:description="__('Only a warning: nothing happens automatically (Article 27).')"
			/>
			<Switch v-model="values.allow_negative_leave_balance" :label="__('Allow leave beyond the balance')" />
			<Select v-model="values.calendar_source" :label="__('Default calendar source')" :options="calendarSourceOptions()" />
			<TextInput v-model="values.time_ir_url" dir="ltr" :label="__('time.ir address')" />
			<TextInput v-model="values.time_ir_api_key" dir="ltr" :label="__('time.ir key')" />
			<ErrorMessage :message="error" />
			<Button type="submit" variant="solid" :loading="busy">{{ __("Save") }}</Button>
		</form>
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, Select, Switch, TextInput, toast } from "frappe-ui"
import { onMounted, reactive, ref } from "vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { calendarSourceOptions } from "@/lib/labels"

interface AppSettings {
	dedup_window_seconds: number
	clock_drift_warning_seconds: number
	absence_warning_days: number
	allow_negative_leave_balance: boolean
	calendar_source: string
	time_ir_url: string
	time_ir_api_key: string
}

const values = reactive<AppSettings>({
	dedup_window_seconds: 30,
	clock_drift_warning_seconds: 60,
	absence_warning_days: 3,
	allow_negative_leave_balance: false,
	calendar_source: "time_ir",
	time_ir_url: "",
	time_ir_api_key: "",
})
const error = ref("")
const busy = ref(false)

onMounted(async () => {
	try {
		Object.assign(values, await api.get<AppSettings>("/admin/settings"))
	} catch (e) {
		error.value = (e as Error).message
	}
})

async function save() {
	busy.value = true
	error.value = ""
	try {
		Object.assign(values, await api.put<AppSettings>("/admin/settings", { ...values }))
		toast.success(__("Saved"))
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = false
	}
}
</script>
