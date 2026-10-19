<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('SMS')" back="manage">
			<Button icon-left="lucide-file-text" :route="{ name: 'sms-templates' }">{{ __("Templates") }}</Button>
			<Button icon-left="lucide-history" :route="{ name: 'sms-messages' }">{{ __("History") }}</Button>
		</PageHeader>
		<p class="text-sm text-ink-gray-6">
			{{
				__(
					"Chronicle sends every SMS through a panel you set up here. The primary panel is tried first; the fallback only when the primary refuses for good."
				)
			}}
		</p>
		<ErrorMessage :message="error" />

		<section v-for="p in providers" :key="p.code" class="hz-card flex flex-col gap-4">
			<div class="flex flex-wrap items-center gap-2">
				<h2 class="flex-1 font-semibold">{{ p.label }}</h2>
				<Badge v-if="p.is_primary && p.is_active" theme="green" :label="__('Primary')" />
				<Badge v-else-if="p.is_fallback && p.is_active" theme="blue" :label="__('Fallback')" />
				<Badge v-else-if="p.configured" theme="gray" :label="p.is_active ? __('Not used') : __('Switched off')" />
				<Badge v-else theme="gray" :label="__('Not set up')" />
			</div>
			<div v-if="forms[p.code]" class="grid grid-cols-1 gap-4 sm:grid-cols-2">
				<template v-for="(spec, key) in schema(p.code)" :key="key">
					<Switch v-if="spec.type === 'boolean'" v-model="forms[p.code].config[key] as boolean" :label="__(spec.label)" />
					<TextInput
						v-else
						v-model="forms[p.code].config[key] as string"
						:type="spec.type === 'secret' ? 'password' : spec.type === 'integer' ? 'number' : 'text'"
						dir="ltr"
						autocomplete="off"
						:label="__(spec.label) + (spec.required ? ' *' : '')"
						:placeholder="spec.type === 'secret' && forms[p.code].has[key] ? __('A key is saved; type here only to replace it') : ''"
					/>
				</template>
				<Select v-model="forms[p.code].role" :label="__('Role')" :options="roleOptions" />
				<Switch v-model="forms[p.code].is_active" :label="__('Switched on')" class="self-end" />
			</div>
			<div class="flex flex-wrap items-center gap-2">
				<Button variant="solid" :loading="busy === 'save:' + p.code" @click="save(p)">{{ __("Save") }}</Button>
				<Button :disabled="!p.configured" :loading="busy === 'test:' + p.code" @click="test(p)">{{ __("Test connection") }}</Button>
				<Button v-if="p.configured" theme="red" variant="subtle" :loading="busy === 'del:' + p.code" @click="remove(p)">{{ __("Remove") }}</Button>
				<span v-if="tests[p.code]" :class="tests[p.code].ok ? 'text-ink-green-3' : 'text-ink-red-3'" class="hz-num text-sm">
					{{
						tests[p.code].ok
							? tests[p.code].credit !== null
								? __("Connected. Credit: {0}", [fa(tests[p.code].credit!)])
								: __("Connected")
							: tests[p.code].message
					}}
				</span>
			</div>
		</section>

		<section v-if="sendWindow" class="hz-card flex flex-col gap-4">
			<div>
				<h2 class="font-semibold">{{ __("Send window") }}</h2>
				<p class="text-sm text-ink-gray-6">
					{{ __("Outside these hours a message waits for the next morning. A one-time code is never held back.") }}
				</p>
			</div>
			<Switch v-model="sendWindow.window_enabled" :label="__('Hold messages outside the window')" />
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
				<Select v-model="sendWindow.window_start_hour" :label="__('From')" :options="hours" :disabled="!sendWindow.window_enabled" />
				<Select v-model="sendWindow.window_end_hour" :label="__('Until')" :options="hours" :disabled="!sendWindow.window_enabled" />
			</div>
			<div><Button variant="solid" :loading="busy === 'window'" @click="saveWindow">{{ __("Save") }}</Button></div>
		</section>

		<section class="hz-card flex flex-col gap-3">
			<div>
				<h2 class="font-semibold">{{ __("Numbers that opted out") }}</h2>
				<p class="text-sm text-ink-gray-6">{{ __("Promotional messages (such as birthdays) are not sent to these numbers.") }}</p>
			</div>
			<form class="flex flex-wrap items-end gap-2" @submit.prevent="addOptOut">
				<TextInput v-model="optMobile" dir="ltr" :label="__('Mobile number')" placeholder="09121234567" />
				<TextInput v-model="optReason" :label="__('Reason')" />
				<Button type="submit" :loading="busy === 'opt'">{{ __("Add") }}</Button>
			</form>
			<ul v-if="optOuts.length" class="divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-1">
				<li v-for="o in optOuts" :key="o.id" class="flex items-center gap-3 px-3 py-2 text-sm">
					<span dir="ltr" class="hz-num w-32">{{ fa(o.mobile) }}</span>
					<span class="flex-1 text-ink-gray-6">{{ o.reason }}</span>
					<Button size="sm" icon="lucide-trash-2" :aria-label="__('Delete')" @click="removeOptOut(o)" />
				</li>
			</ul>
		</section>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, ErrorMessage, Select, Switch, TextInput, toast } from "frappe-ui"
import { computed, onMounted, reactive, ref } from "vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import type { SmsDriver, SmsOptOut, SmsProvider, SmsWindow } from "@/lib/types"

const MASK = "••••••••"
interface Form {
	config: Record<string, string | number | boolean>
	has: Record<string, boolean>
	role: "primary" | "fallback" | "none"
	is_active: boolean
}

const drivers = ref<SmsDriver[]>([])
const providers = ref<SmsProvider[]>([])
const forms = reactive<Record<string, Form>>({})
const tests = reactive<Record<string, { ok: boolean; message: string; credit: number | null }>>({})
const sendWindow = ref<SmsWindow | null>(null)
const optOuts = ref<SmsOptOut[]>([])
const optMobile = ref("")
const optReason = ref("")
const error = ref("")
const busy = ref("")

const roleOptions = computed(() => [
	{ value: "primary", label: __("Primary") },
	{ value: "fallback", label: __("Fallback") },
	{ value: "none", label: __("Not used") },
])
const hours = Array.from({ length: 25 }, (_, h) => ({ value: h, label: fa(`${String(h).padStart(2, "0")}:00`) }))

function schema(code: string) {
	return drivers.value.find((d) => d.code === code)?.config_schema ?? {}
}

function fill(p: SmsProvider) {
	const has: Record<string, boolean> = {}
	const config: Record<string, string | number | boolean> = {}
	for (const [key, spec] of Object.entries(schema(p.code))) {
		const value = p.config[key]
		if (spec.type === "secret") {
			has[key] = value === MASK
			config[key] = ""
		} else config[key] = spec.type === "boolean" ? Boolean(value) : (value ?? "")
	}
	forms[p.code] = {
		config,
		has,
		role: p.is_primary ? "primary" : p.is_fallback ? "fallback" : "none",
		is_active: p.configured ? p.is_active : true,
	}
}

async function load() {
	error.value = ""
	try {
		const [d, p, w, o] = await Promise.all([
			api.get<SmsDriver[]>("/sms/drivers"),
			api.get<SmsProvider[]>("/sms/providers"),
			api.get<SmsWindow>("/sms/settings"),
			api.get<SmsOptOut[]>("/sms/opt-outs"),
		])
		drivers.value = d
		providers.value = p
		p.forEach(fill)
		sendWindow.value = w
		optOuts.value = o
	} catch (e) {
		error.value = (e as Error).message
	}
}

async function save(p: SmsProvider) {
	const f = forms[p.code]
	busy.value = "save:" + p.code
	error.value = ""
	try {
		await api.put(`/sms/providers/${p.code}`, {
			config: f.config,
			is_primary: f.role === "primary",
			is_fallback: f.role === "fallback",
			is_active: f.is_active,
		})
		toast.success(__("Saved"))
		await load()
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

async function test(p: SmsProvider) {
	busy.value = "test:" + p.code
	try {
		tests[p.code] = await api.post(`/sms/providers/${p.code}/test`)
	} catch (e) {
		tests[p.code] = { ok: false, message: (e as Error).message, credit: null }
	} finally {
		busy.value = ""
	}
}

async function remove(p: SmsProvider) {
	if (!window.confirm(__("Remove the settings of {0}?", [p.label]))) return
	busy.value = "del:" + p.code
	try {
		await api.del(`/sms/providers/${p.code}`)
		await load()
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

async function saveWindow() {
	busy.value = "window"
	try {
		sendWindow.value = await api.put<SmsWindow>("/sms/settings", { ...sendWindow.value })
		toast.success(__("Saved"))
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

async function addOptOut() {
	busy.value = "opt"
	try {
		await api.post("/sms/opt-outs", { mobile: optMobile.value, category: "promotional", reason: optReason.value })
		optMobile.value = optReason.value = ""
		optOuts.value = await api.get<SmsOptOut[]>("/sms/opt-outs")
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

async function removeOptOut(o: SmsOptOut) {
	try {
		await api.del(`/sms/opt-outs/${o.id}`)
		optOuts.value = await api.get<SmsOptOut[]>("/sms/opt-outs")
	} catch (e) {
		toast.error((e as Error).message)
	}
}

onMounted(load)
</script>
