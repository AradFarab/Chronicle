<template>
	<div class="space-y-4">
		<div class="flex items-center gap-2">
			<Button :aria-label="__('Back')" icon="lucide-arrow-right" :route="{ name: 'devices' }" />
			<h1 class="flex-1 truncate text-lg font-bold">{{ isNew ? __("Add a device") : name }}</h1>
		</div>

		<!-- settings: everything about a device is data, edited here (no code change) -->
		<form class="hz-card space-y-4" @submit.prevent="save">
			<h2 class="font-semibold">{{ __("Settings") }}</h2>
			<TextInput
				v-if="isNew"
				v-model="form.device_name"
				:label="__('Device Name')"
				:placeholder="__('e.g. Main entrance')"
				required
			/>
			<div class="grid gap-4 sm:grid-cols-2">
				<Select v-model="form.adapter_type" :label="__('Device Type')" :options="options.adapter_types" />
				<Select v-model="form.branch" :label="__('Branch')" :options="branchOptions" />
			</div>
			<div>
				<Select
					v-model="form.direction_mode"
					:label="__('Punch Direction')"
					:options="options.direction_modes"
				/>
				<p class="mt-1.5 text-xs text-ink-gray-5">
					{{
						__(
							"Use Always In / Always Out for separate entry and exit devices. If people do not choose in/out on the device, use Ignore: punches are then paired by order."
						)
					}}
				</p>
			</div>
			<template v-if="isNetwork">
				<h3 class="pt-2 text-sm font-semibold text-ink-gray-7">{{ __("Connection") }}</h3>
				<div class="grid gap-4 sm:grid-cols-[2fr_1fr]">
					<TextInput v-model="form.host" dir="ltr" :label="__('IP Address')" placeholder="192.168.1.201" />
					<TextInput v-model.number="form.port" dir="ltr" type="number" :label="__('Port')" />
				</div>
				<div>
					<TextInput
						v-model="form.comm_key"
						dir="ltr"
						type="password"
						autocomplete="new-password"
						:label="__('Comm Key')"
					/>
					<p class="mt-1.5 text-xs text-ink-gray-5">
						{{ __("Device communication password (Menu > Comm. > Comm Key). Leave empty if not set.") }}
					</p>
				</div>
				<div class="grid grid-cols-2 gap-4">
					<TextInput
						v-model.number="form.polling_interval_minutes"
						type="number"
						:label="__('Read Every (Minutes)')"
					/>
					<TextInput v-model.number="form.timeout_seconds" type="number" :label="__('Timeout (Seconds)')" />
				</div>
				<Switch v-model="useUdp" :label="__('Use UDP')" :description="__('Only for older firmware')" />
			</template>
			<Switch v-model="enabled" :label="__('Enabled')" />
			<ErrorMessage v-if="error" :message="error" />
			<Button type="submit" variant="solid" size="md" class="w-full" :loading="saving">{{ __("Save") }}</Button>
		</form>

		<template v-if="!isNew">
			<!-- network device tools -->
			<section v-if="isNetwork" class="hz-card space-y-3">
				<h2 class="font-semibold">{{ __("Device tools") }}</h2>
				<div class="flex flex-wrap gap-2">
					<Button icon-left="lucide-plug-zap" :loading="busy === 'test'" @click="run('test')">
						{{ __("Test Connection") }}
					</Button>
					<Button icon-left="lucide-users" :loading="busy === 'users'" @click="run('users')">
						{{ __("Read Users from Device") }}
					</Button>
					<Button icon-left="lucide-refresh-cw" :loading="busy === 'sync'" @click="run('sync')">
						{{ __("Read punches now") }}
					</Button>
					<Button icon-left="lucide-clock" :loading="busy === 'clock'" @click="run('clock')">
						{{ __("Set Device Clock") }}
					</Button>
				</div>
				<div class="flex flex-wrap items-end gap-2">
					<JalaliDatePicker v-model="resyncFrom" class="min-w-56 flex-1" :label="__('Read again from')" />
					<Button
						icon-left="lucide-history"
						:disabled="!resyncFrom"
						:loading="busy === 'resync'"
						@click="run('resync')"
					>
						{{ __("Read again") }}
					</Button>
				</div>
				<dl
					v-if="health"
					class="hz-num grid grid-cols-2 gap-2 rounded-4 bg-surface-gray-1 p-3 text-sm sm:grid-cols-3"
				>
					<div v-for="item in healthItems" :key="item.label">
						<dt class="text-xs text-ink-gray-5">{{ item.label }}</dt>
						<dd dir="auto">{{ item.value }}</dd>
					</div>
				</dl>
				<p class="text-xs text-ink-gray-5">
					{{ __("The app only reads from the device; it never clears the device logs.") }}
				</p>
			</section>

			<!-- file import (USB export, Excel, CSV) -->
			<section class="hz-card space-y-3">
				<h2 class="font-semibold">{{ __("Import a punch file") }}</h2>
				<p class="text-sm text-ink-gray-5">
					{{
						__(
							"For a USB export or an Excel/CSV file from another program. Punches already stored are skipped."
						)
					}}
				</p>
				<Select v-model="importTemplate" :label="__('Import Template')" :options="templateOptions" />
				<input
					ref="fileInput"
					type="file"
					accept=".dat,.txt,.csv,.xlsx,.xls"
					class="block w-full text-sm text-ink-gray-7 file:me-3 file:rounded-3 file:border-0 file:bg-surface-gray-2 file:px-3 file:py-1.5 file:text-ink-gray-8"
					@change="file = ($event.target as HTMLInputElement).files?.[0] ?? null"
				/>
				<Button
					icon-left="lucide-upload"
					:disabled="!file || !importTemplate"
					:loading="busy === 'import'"
					@click="importFile"
				>
					{{ __("Import") }}
				</Button>
				<div v-if="importResult" class="hz-num rounded-4 bg-surface-gray-1 p-3 text-sm">
					<p>{{ importSummary }}</p>
					<pre
						v-if="importResult.error_log"
						class="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs text-ink-red-6"
						dir="ltr"
						>{{ importResult.error_log }}</pre
					>
				</div>
			</section>

			<!-- device users → employees -->
			<section class="hz-card space-y-3">
				<div class="flex items-center gap-2">
					<h2 class="flex-1 font-semibold">{{ __("Device users") }}</h2>
					<span v-if="unmappedCount" class="text-sm text-ink-amber-7">
						{{ fa(__("{0} without an employee", [unmappedCount])) }}
					</span>
				</div>
				<p class="text-sm text-ink-gray-5">
					{{
						__(
							"Each device user must point to an employee; users whose ID equals an employee code are mapped automatically."
						)
					}}
				</p>
				<p v-if="!users.length" class="text-center text-sm text-ink-gray-5">
					{{ isNetwork ? __("Press “Read Users from Device”.") : __("Users appear after the first import.") }}
				</p>
				<ul class="divide-y divide-outline-gray-1">
					<li v-for="u in users" :key="u.name" class="flex flex-wrap items-center gap-2 py-2">
						<span class="hz-num w-14 font-semibold" dir="ltr">{{ fa(u.device_user_id) }}</span>
						<span class="min-w-0 flex-1 truncate text-sm text-ink-gray-6" dir="auto">{{
							u.device_user_name || "—"
						}}</span>
						<select
							class="h-8 w-full rounded-3 border border-transparent bg-surface-gray-2 px-2 text-sm sm:w-56"
							:class="u.employee ? '' : 'ring-1 ring-outline-amber-3'"
							:value="u.employee ?? ''"
							@change="mapUser(u, ($event.target as HTMLSelectElement).value)"
						>
							<option value="">{{ __("— no employee —") }}</option>
							<option v-for="e in employees" :key="e.name" :value="e.name">
								{{ e.full_name }} ({{ fa(e.name) }})
							</option>
						</select>
					</li>
				</ul>
			</section>
		</template>
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, Select, Switch, TextInput, toast } from "frappe-ui"
import { computed, onMounted, reactive, ref } from "vue"
import { useRouter } from "vue-router"
import JalaliDatePicker from "@/components/JalaliDatePicker.vue"
import { call, uploadFile } from "@/lib/api"
import { refreshCounts } from "@/lib/counts"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import type { Option } from "@/lib/types"

const props = defineProps<{ name?: string }>()
const router = useRouter()
const isNew = computed(() => !props.name)

const form = reactive({
	device_name: "",
	adapter_type: "ZKTeco",
	branch: "" as string | null,
	enabled: 1,
	direction_mode: "From Device",
	host: "",
	port: 4370,
	comm_key: "",
	polling_interval_minutes: 5,
	timeout_seconds: 10,
	use_udp: 0,
})
const enabled = computed({ get: () => !!form.enabled, set: (v: boolean) => (form.enabled = v ? 1 : 0) })
const useUdp = computed({ get: () => !!form.use_udp, set: (v: boolean) => (form.use_udp = v ? 1 : 0) })
const isNetwork = computed(() => form.adapter_type !== "File Import")

const options = reactive({
	adapter_types: [] as Option[],
	direction_modes: [] as Option[],
	branches: [] as string[],
	import_templates: [] as string[],
})
const branchOptions = computed(() => [
	{ value: "", label: __("All branches") },
	...options.branches.map((b) => ({ value: b, label: b })),
])
const templateOptions = computed(() => options.import_templates.map((t) => ({ value: t, label: t })))

const saving = ref(false)
const error = ref("")
const busy = ref("")

async function loadDevice() {
	if (!props.name) return
	Object.assign(form, await call("hozur.api.pwa.device", { name: props.name }))
	form.branch = form.branch || ""
}

async function save() {
	saving.value = true
	error.value = ""
	try {
		const result = await call<{ name: string }>("hozur.api.pwa.save_device", {
			values: { ...form, name: props.name, branch: form.branch || null },
		})
		toast.success(__("Saved"))
		if (isNew.value) router.replace({ name: "device", params: { name: result.name } })
		else await loadDevice()
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		saving.value = false
	}
}

// tools ------------------------------------------------------------------------------------
interface Health {
	model: string | null
	serial_number: string | null
	firmware: string | null
	user_count: number
	record_count: number
	record_capacity: number
	device_time: [string, string] | null
	clock_drift_seconds: number | null
}
const health = ref<Health | null>(null)
const healthItems = computed(() => {
	const h = health.value
	if (!h) return []
	return [
		{ label: __("Model"), value: h.model || "—" },
		{ label: __("Serial Number"), value: h.serial_number || "—" },
		{ label: __("Firmware"), value: h.firmware || "—" },
		{ label: __("Users on Device"), value: fa(h.user_count ?? 0) },
		{ label: __("Log Records on Device"), value: fa(`${h.record_count ?? 0} / ${h.record_capacity || "?"}`) },
		{ label: __("Device Time"), value: h.device_time ? fa(h.device_time.join(" ")) : "—" },
		{ label: __("Clock Difference (Seconds)"), value: fa(h.clock_drift_seconds ?? 0) },
	]
})
const resyncFrom = ref<string | null>(null)

async function run(action: "test" | "users" | "sync" | "clock" | "resync") {
	busy.value = action
	const device = props.name
	try {
		if (action === "test") {
			health.value = await call<Health>("hozur.devices.service.test_connection", { device })
			toast.success(__("Connected: {0}", [health.value.model || device || ""]))
		} else if (action === "users") {
			const r = await call<{ users: number; created: number; auto_mapped: number }>(
				"hozur.devices.service.read_device_users",
				{ device }
			)
			toast.success(
				fa(__("{0} users read, {1} new, {2} mapped automatically", [r.users, r.created, r.auto_mapped]))
			)
			await loadUsers()
		} else if (action === "sync" || action === "resync") {
			const r = await call<{ created: number }>(
				action === "sync" ? "hozur.devices.service.sync_now" : "hozur.devices.service.resync_from",
				action === "sync" ? { device } : { device, jdate: resyncFrom.value }
			)
			toast.success(fa(__("{0} new punches", [r.created])))
			await loadUsers()
		} else {
			const r = await call<{ set_to: [string, string] }>("hozur.devices.service.set_device_clock", { device })
			toast.success(fa(__("Device clock set to {0} {1}", r.set_to)))
		}
	} catch (e) {
		toast.error((e as Error).message, { duration: 10000 })
	} finally {
		busy.value = ""
	}
}

// file import ------------------------------------------------------------------------------
const importTemplate = ref<string | null>(null)
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement>()
const importResult = ref<{
	total_rows: number
	created: number
	existing: number
	duplicates: number
	errors: number
	error_log: string
} | null>(null)

const importSummary = computed(() => {
	const r = importResult.value
	if (!r) return ""
	const counts = [r.total_rows, r.created, r.existing, r.duplicates, r.errors]
	return fa(__("{0} rows: {1} new, {2} already stored, {3} duplicates, {4} errors", counts))
})

async function importFile() {
	if (!file.value || !importTemplate.value) return
	busy.value = "import"
	importResult.value = null
	try {
		const fileUrl = await uploadFile(file.value)
		importResult.value = await call("hozur.api.pwa.import_punches", {
			device: props.name,
			template: importTemplate.value,
			file_url: fileUrl,
		})
		file.value = null
		if (fileInput.value) fileInput.value.value = ""
		await loadUsers()
	} catch (e) {
		toast.error((e as Error).message, { duration: 10000 })
	} finally {
		busy.value = ""
	}
}

// device users -----------------------------------------------------------------------------
interface DeviceUser {
	name: string
	device_user_id: string
	device_user_name: string | null
	employee: string | null
}
const users = ref<DeviceUser[]>([])
const employees = ref<{ name: string; full_name: string }[]>([])
const unmappedCount = computed(() => users.value.filter((u) => !u.employee).length)

async function loadUsers() {
	if (!props.name) return
	users.value = await call<DeviceUser[]>("hozur.api.pwa.device_users", { device: props.name })
}

async function mapUser(u: DeviceUser, employee: string) {
	try {
		const r = await call<{ employee: string | null }>("hozur.api.pwa.map_device_user", {
			name: u.name,
			employee: employee || null,
		})
		u.employee = r.employee
		toast.success(__("Saved"))
		refreshCounts(true)
	} catch (e) {
		toast.error((e as Error).message)
		await loadUsers()
	}
}

onMounted(async () => {
	try {
		Object.assign(options, await call("hozur.api.pwa.device_options"))
		importTemplate.value = options.import_templates[0] ?? null
		await loadDevice()
		if (props.name) {
			await loadUsers()
			employees.value = await call("hozur.api.pwa.employees", { limit: 1000 })
		}
	} catch (e) {
		error.value = (e as Error).message
	}
})
</script>
