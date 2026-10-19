<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Payslip settings')" back="payslips" />
		<ErrorMessage :message="error" />

		<section v-if="sms" class="hz-card flex flex-col gap-4">
			<div>
				<h2 class="font-semibold">{{ __("SMS connection") }}</h2>
				<p class="text-sm text-ink-gray-6">
					{{ __("The payslip links are sent through this account. The key is kept encrypted on the server.") }}
				</p>
			</div>
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
				<Select v-model="smsForm.provider" :label="__('Provider')" :options="providers" />
				<TextInput v-model="smsForm.line_number" dir="ltr" :label="__('Sender line number')" />
			</div>
			<TextInput
				v-model="smsForm.api_key"
				type="password"
				dir="ltr"
				autocomplete="off"
				:label="__('API key')"
				:placeholder="sms.has_key ? __('A key is saved; type here only to replace it') : ''"
			/>
			<div class="flex flex-wrap items-center gap-2">
				<Button variant="solid" :loading="busy === 'sms'" @click="saveSms">{{ __("Save") }}</Button>
				<Button :loading="busy === 'test'" :disabled="!sms.has_key" @click="testSms">{{ __("Test connection") }}</Button>
				<span v-if="test" :class="test.ok ? 'text-ink-green-3' : 'text-ink-red-3'" class="hz-num text-sm">
					{{
						test.ok
							? test.credit !== null
								? __("Connected. Credit: {0}", [fa(test.credit)])
								: __("Connected")
							: test.message
					}}
				</span>
			</div>
		</section>

		<section class="hz-card flex flex-col gap-4">
			<h2 class="font-semibold">{{ __("Links and message") }}</h2>
			<TextInput
				v-model="values.base_url"
				dir="ltr"
				placeholder="https://chronicle.example.ir"
				:label="__('Address of this site')"
				:description="__('The links in the SMS start with this address. It must reach this server from outside the company network.')"
			/>
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
			<Textarea v-model="values.message" :rows="4" :label="__('Text of the SMS')" />
			<p class="text-xs text-ink-gray-5" dir="ltr">{name} {month} {link} {expires}</p>
			<div>
				<Button variant="solid" :loading="busy === 'settings'" @click="saveSettings">{{ __("Save") }}</Button>
			</div>
		</section>
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, Select, Textarea, TextInput, toast } from "frappe-ui"
import { computed, onMounted, reactive, ref } from "vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import type { PayslipSettings, SmsSettings } from "@/lib/types"

const sms = ref<SmsSettings | null>(null)
const values = reactive<PayslipSettings>({
	base_url: "",
	link_expiry_days: 14,
	link_max_views: 5,
	max_failed_attempts: 5,
	message: "",
})
const smsForm = reactive({ provider: "smsir", line_number: "", api_key: "" })
const test = ref<{ ok: boolean; message: string; credit: number | null } | null>(null)
const error = ref("")
const busy = ref("")

const providers = computed(() => (sms.value?.providers ?? []).map((p) => ({ value: p.code, label: p.label })))

function applySms(saved: SmsSettings) {
	sms.value = saved
	smsForm.provider = saved.provider
	smsForm.line_number = saved.line_number
	smsForm.api_key = ""
}

onMounted(async () => {
	try {
		const [s, v] = await Promise.all([api.get<SmsSettings>("/payslips/sms"), api.get<PayslipSettings>("/payslips/settings")])
		applySms(s)
		Object.assign(values, v)
	} catch (e) {
		error.value = (e as Error).message
	}
})

async function saveSms() {
	busy.value = "sms"
	error.value = ""
	try {
		applySms(await api.put<SmsSettings>("/payslips/sms", { ...smsForm }))
		test.value = null
		toast.success(__("Saved"))
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

async function testSms() {
	busy.value = "test"
	error.value = ""
	try {
		test.value = await api.post("/payslips/sms/test")
	} catch (e) {
		test.value = { ok: false, message: (e as Error).message, credit: null }
	} finally {
		busy.value = ""
	}
}

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
