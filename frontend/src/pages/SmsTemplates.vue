<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('SMS templates')" back="sms">
			<Button variant="solid" icon-left="lucide-plus" @click="openNew">{{ __("New template") }}</Button>
		</PageHeader>
		<p class="text-sm text-ink-gray-6">
			{{
				__(
					"A template says how an event is sent through a panel: the full text, or the code of a pattern approved by the panel with the event's fields filling its variables."
				)
			}}
		</p>
		<ErrorMessage :message="error" />

		<DataTable :columns="columns" :rows="templates" :loading="loading" row-key="id" storage-key="sms-templates">
			<template #cell-state="{ row: t }">
				<Badge :theme="t.is_active ? 'green' : 'gray'" :label="t.is_active ? __('Active') : __('Inactive')" />
			</template>
			<template #cell-actions="{ row: t }">
				<span class="flex gap-1">
					<Button size="sm" icon="lucide-pencil" :aria-label="__('Edit')" @click="openEdit(t)" />
					<Button size="sm" theme="red" variant="subtle" icon="lucide-trash-2" :aria-label="__('Delete')" @click="remove(t)" />
				</span>
			</template>
		</DataTable>

		<section class="hz-card flex flex-col gap-3">
			<div>
				<h2 class="font-semibold">{{ __("Send a test") }}</h2>
				<p class="text-sm text-ink-gray-6">{{ __("Sends a real SMS now with sample values, through the active template of the event.") }}</p>
			</div>
			<div class="flex flex-wrap items-end gap-2">
				<Select v-model="testEvent" :label="__('Event')" :options="eventOptions" class="w-64" />
				<TextInput v-model="testNumber" dir="ltr" :label="__('Mobile number')" placeholder="09121234567" />
				<Button :loading="busy === 'test'" :disabled="!testEvent || !testNumber" @click="sendTest">{{ __("Send") }}</Button>
			</div>
			<p v-if="testResult" class="text-sm" :class="smsStatusClass(testResult.status)">
				{{ smsStatusLabel(testResult.status) }}<span v-if="testResult.error"> — {{ testResult.error }}</span>
			</p>
		</section>

		<section class="hz-card flex flex-col gap-3">
			<h2 class="font-semibold">{{ __("Events") }}</h2>
			<ul class="divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-1">
				<li v-for="e in events" :key="e.code" class="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm">
					<span class="min-w-0 flex-1">
						<span class="font-medium">{{ e.label }}</span>
						<span class="block text-xs text-ink-gray-5" dir="ltr">{{ e.code }} · {{ e.variables.join(", ") }}</span>
					</span>
					<Badge v-if="e.category === 'promotional'" theme="amber" :label="__('Promotional')" />
					<Badge v-if="e.bypasses_send_window" theme="blue" :label="__('Never held back')" />
					<Badge :theme="e.providers.length ? 'green' : 'gray'" :label="e.providers.length ? __('Has a template') : __('No template')" />
					<Switch :model-value="e.is_active" @update:model-value="toggle(e, $event)" />
				</li>
			</ul>
		</section>

		<Dialog v-model:open="dialog" :title="form.id ? __('Edit the template') : __('New template')" size="2xl">
			<div class="flex flex-col gap-4">
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
					<Select v-model="form.event" :label="__('Event') + ' *'" :options="eventOptions" :disabled="!!form.id" />
					<Select v-model="form.provider_code" :label="__('Panel') + ' *'" :options="driverOptions" />
					<Select v-model="form.mode" :label="__('Sent as') + ' *'" :options="modeOptions" />
				</div>
				<template v-if="event">
					<p class="text-xs text-ink-gray-5">
						{{ __("Fields of this event:") }} <span dir="ltr" class="font-mono">{{ event.variables.join("  ") }}</span>
					</p>
					<template v-if="form.mode === 'bulk'">
						<Textarea v-model="form.body" :rows="4" :label="__('Text of the message') + ' *'" />
						<p class="text-xs text-ink-gray-5" dir="ltr">{{ event.variables.map((v) => "{" + v + "}").join("  ") }}</p>
					</template>
					<template v-else>
						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
							<TextInput v-model="form.pattern_code" dir="ltr" :label="__('Pattern code') + ' *'" />
							<TextInput
								v-if="driver?.pattern_schema.requires_line_number"
								v-model="form.line_number"
								dir="ltr"
								:label="__('Service number') + ' *'"
							/>
						</div>
						<div class="flex flex-col gap-2">
							<p class="text-sm font-medium">
								{{
									named
										? __("The variables of the approved text, and the event field that fills each")
										: __("The event fields, in the order of the pattern's variables")
								}}
							</p>
							<div v-for="(row, i) in form.rows" :key="i" class="flex items-end gap-2">
								<TextInput v-if="named" v-model="row.name" dir="ltr" :label="i === 0 ? __('Variable name in the panel') : ''" placeholder="LINK" class="flex-1" />
								<span v-else class="hz-num w-6 pb-2 text-center text-sm text-ink-gray-5">{{ fa(i + 1) }}</span>
								<Select v-model="row.variable" :label="i === 0 ? __('Filled with') : ''" :options="variableOptions" class="flex-1" />
								<Button size="sm" icon="lucide-x" :aria-label="__('Remove')" @click="form.rows.splice(i, 1)" />
							</div>
							<div><Button size="sm" icon-left="lucide-plus" @click="form.rows.push({ name: '', variable: '' })">{{ __("Add a variable") }}</Button></div>
							<p v-if="named" class="text-xs text-ink-gray-5">
								{{ __("The name must be exactly the variable of the approved text (capitals count). The panel does not complain about a wrong name: it sends the text with the variable left in it.") }}
							</p>
						</div>
					</template>
				</template>
				<Switch v-model="form.is_active" :label="__('Active')" />
				<div v-if="shown" class="rounded-4 bg-surface-gray-2 p-3 text-sm">
					<p class="mb-1 font-medium">{{ __("This is exactly what is sent:") }}</p>
					<pre v-if="shown.text" class="whitespace-pre-wrap">{{ shown.text }}</pre>
					<pre v-else class="whitespace-pre-wrap text-xs" dir="ltr">{{ JSON.stringify(shown.request, null, 2) }}</pre>
					<p v-if="warnings.length" class="mt-2 text-ink-amber-7">
						{{ __("Fields not used by this template: {0}", [warnings.join(", ")]) }}
					</p>
				</div>
				<ErrorMessage :message="dialogError" />
			</div>
			<template #actions>
				<Button :loading="busy === 'preview'" @click="doPreview">{{ __("Preview") }}</Button>
				<Button variant="solid" :loading="busy === 'save'" @click="save">{{ __("Save") }}</Button>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, Dialog, ErrorMessage, Select, Switch, Textarea, TextInput, toast } from "frappe-ui"
import { computed, onMounted, reactive, ref } from "vue"
import DataTable from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import { smsStatusClass, smsStatusLabel } from "@/lib/sms"
import type { TableColumn } from "@/lib/table"
import type { SmsDriver, SmsEvent, SmsMessage, SmsSample, SmsTemplate } from "@/lib/types"

interface Form {
	id: number | null
	event: string
	provider_code: string
	mode: "bulk" | "pattern"
	body: string
	pattern_code: string
	line_number: string
	rows: { name: string; variable: string }[]
	is_active: boolean
}

const blank = (): Form => ({
	id: null,
	event: "",
	provider_code: "",
	mode: "bulk",
	body: "",
	pattern_code: "",
	line_number: "",
	rows: [{ name: "", variable: "" }],
	is_active: true,
})

const templates = ref<SmsTemplate[]>([])
const events = ref<SmsEvent[]>([])
const drivers = ref<SmsDriver[]>([])
const loading = ref(false)
const error = ref("")
const dialog = ref(false)
const dialogError = ref("")
const busy = ref("")
const form = reactive<Form>(blank())
const shown = ref<SmsSample | null>(null)
const warnings = ref<string[]>([])
const testEvent = ref("")
const testNumber = ref("")
const testResult = ref<SmsMessage | null>(null)

const event = computed(() => events.value.find((e) => e.code === form.event))
const driver = computed(() => drivers.value.find((d) => d.code === form.provider_code))
const named = computed(() => (driver.value?.pattern_schema.param_style ?? "named") === "named")
const eventOptions = computed(() => events.value.map((e) => ({ value: e.code, label: e.label })))
const driverOptions = computed(() => drivers.value.map((d) => ({ value: d.code, label: d.label })))
const variableOptions = computed(() => (event.value?.variables ?? []).map((v) => ({ value: v, label: v })))
const modeOptions = computed(() =>
	(driver.value?.capabilities ?? ["bulk", "pattern"]).map((m) => ({
		value: m,
		label: m === "bulk" ? __("A full text") : __("A pattern approved by the panel"),
	}))
)

const columns: TableColumn<SmsTemplate>[] = [
	{ key: "event_label", label: __("Event"), class: "font-medium" },
	{ key: "provider_code", label: __("Panel"), format: (t) => drivers.value.find((d) => d.code === t.provider_code)?.label ?? t.provider_code },
	{ key: "mode", label: __("Sent as"), format: (t) => (t.mode === "bulk" ? __("A full text") : __("Pattern {0}", [t.pattern_code ?? ""])) },
	{ key: "state", label: __("Status"), value: (t) => (t.is_active ? __("Active") : __("Inactive")) },
	{ key: "actions", label: "", sortable: false, filterable: false },
]

async function load() {
	loading.value = true
	error.value = ""
	try {
		;[templates.value, events.value, drivers.value] = await Promise.all([
			api.get<SmsTemplate[]>("/sms/templates"),
			api.get<SmsEvent[]>("/sms/events"),
			api.get<SmsDriver[]>("/sms/drivers"),
		])
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

function openNew() {
	Object.assign(form, blank(), { provider_code: drivers.value[0]?.code ?? "" })
	shown.value = null
	dialogError.value = ""
	dialog.value = true
}

function openEdit(t: SmsTemplate) {
	const map = t.param_map
	const rows = Array.isArray(map)
		? map.map((variable) => ({ name: "", variable }))
		: Object.entries(map ?? {}).map(([name, variable]) => ({ name, variable }))
	Object.assign(form, blank(), {
		id: t.id,
		event: t.event,
		provider_code: t.provider_code,
		mode: t.mode,
		body: t.body ?? "",
		pattern_code: t.pattern_code ?? "",
		line_number: t.line_number ?? "",
		rows: rows.length ? rows : [{ name: "", variable: "" }],
		is_active: t.is_active,
	})
	shown.value = null
	dialogError.value = ""
	dialog.value = true
}

function payload() {
	const filled = form.rows.filter((r) => r.variable)
	return {
		event: form.event,
		provider_code: form.provider_code,
		mode: form.mode,
		body: form.mode === "bulk" ? form.body : null,
		pattern_code: form.mode === "pattern" ? form.pattern_code : null,
		line_number: form.line_number || null,
		param_map:
			form.mode !== "pattern" ? null : named.value ? Object.fromEntries(filled.map((r) => [r.name, r.variable])) : filled.map((r) => r.variable),
		is_active: form.is_active,
	}
}

async function doPreview() {
	busy.value = "preview"
	dialogError.value = ""
	try {
		const r = await api.post<SmsSample & { warnings: string[] }>("/sms/templates/preview", payload())
		shown.value = r
		warnings.value = r.warnings
	} catch (e) {
		shown.value = null
		dialogError.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

async function save() {
	busy.value = "save"
	dialogError.value = ""
	try {
		const saved = form.id
			? await api.patch<SmsTemplate>(`/sms/templates/${form.id}`, payload())
			: await api.post<SmsTemplate>("/sms/templates", payload())
		toast.success(__("Saved"))
		if (saved.warnings?.length) toast.warning(__("Fields not used by this template: {0}", [saved.warnings.join(", ")]))
		dialog.value = false
		await load()
	} catch (e) {
		dialogError.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

async function remove(t: SmsTemplate) {
	if (!window.confirm(__("Delete this template? Messages of {0} cannot be sent until a new one is made.", [t.event_label]))) return
	try {
		await api.del(`/sms/templates/${t.id}`)
		await load()
	} catch (e) {
		toast.error((e as Error).message)
	}
}

async function toggle(e: SmsEvent, active: boolean) {
	try {
		await api.put(`/sms/events/${e.code}`, { is_active: active })
		await load()
	} catch (err) {
		toast.error((err as Error).message)
	}
}

async function sendTest() {
	busy.value = "test"
	testResult.value = null
	try {
		testResult.value = await api.post<SmsMessage>("/sms/test-send", { event: testEvent.value, to: testNumber.value })
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

onMounted(load)
</script>
