<template>
	<div class="space-y-4">
		<div class="flex items-center gap-2">
			<Button :aria-label="__('Back')" icon="lucide-arrow-right" :route="{ name: 'devices' }" />
			<h1 class="flex-1 truncate text-lg font-bold">{{ isNew ? __("Add a device") : title }}</h1>
		</div>

		<!-- settings: everything about a device is data, edited here (no code change) -->
		<form class="hz-card space-y-4" @submit.prevent="save">
			<h2 class="font-semibold">{{ __("Settings") }}</h2>
			<TextInput
				v-model="form.name"
				:label="__('Device Name')"
				:placeholder="__('e.g. Main entrance')"
				required
			/>
			<div class="grid gap-4 sm:grid-cols-2">
				<Select v-model="form.adapter_type" :label="__('Device Type')" :options="adapterOptions" />
				<Select v-model="form.branch_id" :label="__('Branch')" :options="branchOptions" />
			</div>
			<div>
				<Select
					v-model="form.direction_mode"
					:label="__('Punch Direction')"
					:options="directionModes"
				/>
				<p class="mt-1.5 text-xs text-ink-gray-5">
					{{
						__(
							"Use Always In / Always Out for separate entry and exit devices. If people do not choose in/out on the device, use Pair by order."
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
						:placeholder="hasCommKey ? __('Stored; leave empty to keep it') : undefined"
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
				<p v-if="!templateOptions.length" class="text-xs text-ink-amber-7">
					{{ __("Define an import template first (Manage > Import Templates).") }}
				</p>
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
					<li v-for="u in users" :key="u.id ?? 'new-' + u.device_user_id" class="flex flex-wrap items-center gap-2 py-2">
						<span class="hz-num w-14 font-semibold" dir="ltr">{{ fa(u.device_user_id) }}</span>
						<span class="min-w-0 flex-1 truncate text-sm text-ink-gray-6" dir="auto">
							{{ u.device_user_name || "—" }}
							<span v-if="u.valid_from || u.valid_to" class="hz-num block text-xs text-ink-gray-5">
								{{ __("From {0} to {1}", [fa(u.valid_from || "…"), fa(u.valid_to || "…")]) }}
							</span>
						</span>
						<select
							class="h-8 w-full rounded-3 border border-transparent bg-surface-gray-2 px-2 text-sm sm:w-56"
							:class="u.employee_id ? '' : 'ring-1 ring-outline-amber-3'"
							:value="u.employee_id ?? ''"
							@change="mapUser(u, ($event.target as HTMLSelectElement).value)"
						>
							<option value="">{{ __("— no employee —") }}</option>
							<option v-for="e in employees" :key="e.id" :value="e.id">
								{{ e.full_name }} ({{ fa(e.code) }})
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
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import JalaliDatePicker from "@/components/JalaliDatePicker.vue"
import { api } from "@/lib/api"
import { refreshCounts } from "@/lib/counts"
import { directionModeLabel } from "@/lib/format"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import type { Employee } from "@/lib/types"

const props = defineProps<{ id?: number }>()
const router = useRouter()
const isNew = computed(() => !props.id)

interface Device {
	id: number
	name: string
	adapter_type: string
	branch_id: number | null
	enabled: boolean
	direction_mode: string
	host: string | null
	port: number
	has_comm_key: boolean
	polling_interval_minutes: number
	timeout_seconds: number
	use_udp: boolean
}

interface Adapter {
	code: string
	label: string
	network: boolean
}

interface SyncResult {
	ok: boolean
	created: number
	existing: number
	duplicates: number
	message: string | null
}

const form = reactive({
	name: "",
	adapter_type: "zkteco",
	branch_id: "" as number | "",
	enabled: true,
	direction_mode: "from_device",
	host: "",
	port: 4370,
	comm_key: "", // write-only: sent only when typed
	polling_interval_minutes: 5,
	timeout_seconds: 10,
	use_udp: false,
})
const title = ref("")
const hasCommKey = ref(false)
const enabled = computed({ get: () => form.enabled, set: (v: boolean) => (form.enabled = v) })
const useUdp = computed({ get: () => form.use_udp, set: (v: boolean) => (form.use_udp = v) })

const adapters = ref<Adapter[]>([])
const branches = ref<{ id: number; name: string }[]>([])
const templates = ref<{ id: number; name: string }[]>([])
const isNetwork = computed(
	() => adapters.value.find((a) => a.code === form.adapter_type)?.network ?? form.adapter_type !== "file_import"
)
const adapterOptions = computed(() => adapters.value.map((a) => ({ value: a.code, label: __(a.label) })))
const directionModes = computed(() =>
	["from_device", "always_in", "always_out", "pair_by_order"].map((m) => ({ value: m, label: directionModeLabel(m) }))
)
const branchOptions = computed(() => [
	{ value: "", label: __("All branches") },
	...branches.value.map((b) => ({ value: b.id, label: b.name })),
])
const templateOptions = computed(() => templates.value.map((t) => ({ value: t.id, label: t.name })))

const saving = ref(false)
const error = ref("")
const busy = ref("")

function fill(d: Device) {
	Object.assign(form, {
		name: d.name,
		adapter_type: d.adapter_type,
		branch_id: d.branch_id ?? "",
		enabled: d.enabled,
		direction_mode: d.direction_mode,
		host: d.host ?? "",
		port: d.port,
		comm_key: "",
		polling_interval_minutes: d.polling_interval_minutes,
		timeout_seconds: d.timeout_seconds,
		use_udp: d.use_udp,
	})
	title.value = d.name
	hasCommKey.value = d.has_comm_key
}

async function loadDevice() {
	if (!props.id) return
	// there is no single-device endpoint: the list is small
	const device = (await api.get<Device[]>("/devices")).find((d) => d.id === props.id)
	if (!device) throw new Error(__("Not found"))
	fill(device)
}

async function save() {
	saving.value = true
	error.value = ""
	try {
		const { comm_key, ...values } = form
		const body = { ...values, branch_id: form.branch_id || null, ...(comm_key ? { comm_key } : {}) }
		const device = props.id
			? await api.patch<Device>(`/devices/${props.id}`, body)
			: await api.post<Device>("/devices", body)
		toast.success(__("Saved"))
		if (isNew.value) router.replace({ name: "device", params: { id: device.id } })
		else fill(device)
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
		{ label: __("Device Time"), value: h.device_time ? fa(h.device_time.join(" ").slice(0, 16)) : "—" },
		{ label: __("Clock Difference (Seconds)"), value: fa(h.clock_drift_seconds ?? 0) },
	]
})
const resyncFrom = ref<string | null>(null)

async function run(action: "test" | "users" | "sync" | "clock" | "resync") {
	if (!props.id) return
	busy.value = action
	const path = `/devices/${props.id}`
	try {
		if (action === "test") {
			health.value = await api.post<Health>(`${path}/test`)
			toast.success(__("Connected: {0}", [health.value.model || title.value]))
		} else if (action === "users") {
			const r = await api.post<{ users: number; created: number; auto_mapped: number }>(`${path}/read-users`)
			toast.success(
				fa(__("{0} users read, {1} new, {2} mapped automatically", [r.users, r.created, r.auto_mapped]))
			)
			await loadUsers()
			refreshCounts(true)
		} else if (action === "sync" || action === "resync") {
			const r =
				action === "sync"
					? await api.post<SyncResult>(`${path}/sync`)
					: await api.post<SyncResult>(`${path}/resync`, { jdate: resyncFrom.value })
			if (r.ok) toast.success(fa(__("{0} new punches", [r.created])))
			else toast.error(r.message || __("Error"), { duration: 10000 })
			await loadUsers()
			refreshCounts(true)
		} else {
			const r = await api.post<{ set_to: [string, string] }>(`${path}/set-clock`)
			toast.success(fa(__("Device clock set to {0} {1}", [r.set_to[0], r.set_to[1].slice(0, 5)])))
		}
	} catch (e) {
		toast.error((e as Error).message, { duration: 10000 })
	} finally {
		busy.value = ""
	}
}

// file import ------------------------------------------------------------------------------
const importTemplate = ref<number | null>(null)
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement>()
const importResult = ref<{
	status: string
	total_rows: number
	created_count: number
	existing_count: number
	duplicate_count: number
	error_count: number
	error_log: string | null
} | null>(null)

const importSummary = computed(() => {
	const r = importResult.value
	if (!r) return ""
	const counts = [r.total_rows, r.created_count, r.existing_count, r.duplicate_count, r.error_count]
	return fa(__("{0} rows: {1} new, {2} already stored, {3} duplicates, {4} errors", counts))
})

async function importFile() {
	if (!props.id || !file.value || !importTemplate.value) return
	busy.value = "import"
	importResult.value = null
	try {
		const data = new FormData()
		data.append("template_id", String(importTemplate.value))
		data.append("file", file.value)
		importResult.value = await api.upload(`/devices/${props.id}/import`, data)
		file.value = null
		if (fileInput.value) fileInput.value.value = ""
		await loadUsers()
		refreshCounts(true)
	} catch (e) {
		toast.error((e as Error).message, { duration: 10000 })
	} finally {
		busy.value = ""
	}
}

// device users -----------------------------------------------------------------------------
interface DeviceUser {
	id: number | null // null: punches arrived for this device user but nobody mapped it yet
	device_user_id: string
	device_user_name: string | null
	employee_id: number | null
	valid_from: string | null
	valid_to: string | null
}
const users = ref<DeviceUser[]>([])
const employees = ref<Employee[]>([])
const unmappedCount = computed(() => users.value.filter((u) => !u.employee_id).length)

async function loadUsers() {
	if (!props.id) return
	const [mapped, unmapped] = await Promise.all([
		api.get<DeviceUser[]>(`/devices/${props.id}/users`),
		api.get<{ device_id: number; device_user_id: string }[]>("/devices/users/unmapped"),
	])
	const known = new Set(mapped.map((u) => u.device_user_id))
	const waiting = unmapped
		.filter((u) => u.device_id === props.id && !known.has(u.device_user_id))
		.map((u) => ({
			id: null,
			device_user_id: u.device_user_id,
			device_user_name: null,
			employee_id: null,
			valid_from: null,
			valid_to: null,
		}))
	users.value = [...mapped, ...waiting]
}

async function mapUser(u: DeviceUser, employee: string) {
	const employee_id = employee ? Number(employee) : null
	try {
		const r = u.id
			? await api.patch<DeviceUser>(`/devices/users/${u.id}`, { employee_id })
			: await api.post<DeviceUser>("/devices/users", {
					device_id: props.id,
					device_user_id: u.device_user_id,
					employee_id,
			  })
		u.id = r.id
		u.employee_id = r.employee_id
		toast.success(__("Saved"))
		refreshCounts(true)
	} catch (e) {
		toast.error((e as Error).message)
		await loadUsers()
	}
}

// the device's own data; runs again when a new device is saved (same page, new id)
async function loadExisting() {
	if (!props.id) return
	const [templateRows, employeeRows] = await Promise.all([
		api.get<{ id: number; name: string }[]>("/devices/import-templates"),
		api.get<Employee[]>("/admin/employees"),
		loadDevice(),
		loadUsers(),
	])
	templates.value = templateRows
	importTemplate.value = templateRows[0]?.id ?? null
	employees.value = employeeRows
}

watch(
	() => props.id,
	() => loadExisting().catch((e) => (error.value = (e as Error).message))
)

onMounted(async () => {
	try {
		const [adapterRows, branchRows] = await Promise.all([
			api.get<Adapter[]>("/devices/adapters"),
			api.get<{ id: number; name: string }[]>("/admin/branches"),
		])
		adapters.value = adapterRows
		branches.value = branchRows
		await loadExisting()
	} catch (e) {
		error.value = (e as Error).message
	}
})
</script>
