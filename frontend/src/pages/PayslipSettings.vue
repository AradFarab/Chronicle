<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Payslip settings')" back="payslips" />
		<ErrorMessage :message="error" />

		<p class="text-sm text-ink-gray-6">
			{{ __("The SMS panel and the text of the message are set in the SMS section; here only the links.") }}
			<RouterLink :to="{ name: 'sms-templates' }" class="underline">{{ __("Open the SMS section") }}</RouterLink>
		</p>

		<section class="hz-card flex flex-col gap-4">
			<h2 class="font-semibold">{{ __("Links") }}</h2>
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
				<TextInput v-model.number="values.link_expiry_days" type="number" dir="ltr" :label="__('Days a link works')" />
				<TextInput v-model.number="values.link_max_views" type="number" dir="ltr" :label="__('Times a link can be opened')" />
				<TextInput
					v-model.number="values.max_failed_attempts"
					type="number"
					dir="ltr"
					:label="__('Wrong answers before a link locks')"
				/>
			</div>
			<div>
				<Button variant="solid" :loading="busy === 'settings'" @click="saveSettings">{{ __("Save") }}</Button>
			</div>
		</section>
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, TextInput, toast } from "frappe-ui"
import { onMounted, reactive, ref } from "vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import type { PayslipSettings } from "@/lib/types"

const values = reactive<PayslipSettings>({ link_expiry_days: 14, link_max_views: 5, max_failed_attempts: 5 })
const error = ref("")
const busy = ref("")

onMounted(async () => {
	try {
		Object.assign(values, await api.get<PayslipSettings>("/payslips/settings"))
	} catch (e) {
		error.value = (e as Error).message
	}
})

async function saveSettings() {
	busy.value = "settings"
	error.value = ""
	try {
		Object.assign(values, await api.put<PayslipSettings>("/payslips/settings", { ...values }))
		toast.success(__("Saved"))
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}
</script>
