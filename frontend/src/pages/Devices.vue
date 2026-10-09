<template>
	<div class="space-y-4">
		<div class="flex items-center gap-2">
			<h1 class="flex-1 text-lg font-bold">{{ __("Attendance devices") }}</h1>
			<ExcelImport v-if="hasImport('devices')" name="devices" @done="load" />
			<Button variant="solid" icon-left="lucide-plus" :route="{ name: 'new-device' }">{{
				__("Add a device")
			}}</Button>
		</div>

		<ErrorMessage v-if="error" :message="error" />
		<p v-if="loading" class="text-center text-sm text-ink-gray-5">{{ __("Loading...") }}</p>
		<div v-else-if="!devices.length" class="hz-card space-y-2 text-center">
			<p class="text-ink-gray-7">{{ __("No device yet.") }}</p>
			<p class="text-sm text-ink-gray-5">
				{{ __("Add the device with its IP address and port; you can test the connection right away.") }}
			</p>
		</div>

		<ul class="space-y-3">
			<li v-for="d in devices" :key="d.id" class="hz-card space-y-3">
				<RouterLink :to="{ name: 'device', params: { id: d.id } }" class="flex items-start gap-3">
					<span class="flex size-10 shrink-0 items-center justify-center rounded-4 bg-surface-gray-2">
						<span
							:class="isNetwork(d) ? 'lucide-fingerprint' : 'lucide-file-up'"
							class="size-5"
						/>
					</span>
					<span class="min-w-0 flex-1">
						<span class="flex flex-wrap items-center gap-2">
							<span class="font-semibold">{{ d.name }}</span>
							<Badge v-if="!d.enabled" theme="gray" :label="__('Disabled')" />
							<StatusBadge v-if="d.last_sync_status" :status="d.last_sync_status" />
						</span>
						<span class="mt-0.5 block text-sm text-ink-gray-5">
							{{ adapterLabel(d.adapter_type) }}
							<template v-if="d.host">
								· <span dir="ltr" class="hz-num">{{ d.host }}:{{ d.port }}</span></template
							>
							<template v-if="d.work_location_id && locations[d.work_location_id]"> · {{ locations[d.work_location_id] }}</template>
						</span>
					</span>
					<span class="lucide-chevron-left size-4 text-ink-gray-4" />
				</RouterLink>
				<dl class="hz-num grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
					<div>
						<dt class="text-xs text-ink-gray-5">{{ __("Last Read") }}</dt>
						<dd>{{ d.last_sync_at ? fa(d.last_sync_at) : "—" }}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-gray-5">{{ __("Users on Device") }}</dt>
						<dd>{{ fa(d.user_count || 0) }}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-gray-5">{{ __("Log Records on Device") }}</dt>
						<dd>{{ fa(d.record_count || 0) }}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-gray-5">{{ __("Unmapped users") }}</dt>
						<dd :class="unmapped[d.id] ? 'font-semibold text-ink-amber-7' : ''">
							{{ fa(unmapped[d.id] || 0) }}
						</dd>
					</div>
				</dl>
				<p
					v-if="d.last_sync_status === 'error' && d.last_error"
					class="rounded-4 bg-surface-red-1 p-2 text-sm text-ink-red-7"
				>
					{{ d.last_error }}
				</p>
				<div v-if="isNetwork(d)" class="flex flex-wrap gap-2">
					<Button icon-left="lucide-plug-zap" :loading="busy === d.id + 'test'" @click="test(d)">
						{{ __("Test Connection") }}
					</Button>
					<Button icon-left="lucide-refresh-cw" :loading="busy === d.id + 'sync'" @click="sync(d)">
						{{ __("Read punches now") }}
					</Button>
				</div>
			</li>
		</ul>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, ErrorMessage, toast } from "frappe-ui"
import { onMounted, ref } from "vue"
import ExcelImport from "@/components/ExcelImport.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { api } from "@/lib/api"
import { refreshCounts } from "@/lib/counts"
import { __ } from "@/lib/i18n"
import { hasImport } from "@/lib/imports"
import { fa } from "@/lib/jalali"

interface Device {
	id: number
	name: string
	adapter_type: string
	work_location_id: number | null
	enabled: boolean
	host: string | null
	port: number | null
	last_sync_at: string | null
	last_sync_status: string | null // ok | error
	last_error: string | null
	user_count: number | null
	record_count: number | null
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

const devices = ref<Device[]>([])
const adapters = ref<Record<string, Adapter>>({})
const locations = ref<Record<number, string>>({})
const unmapped = ref<Record<number, number>>({}) // device id -> device users with punches but no employee
const loading = ref(false)
const error = ref("")
const busy = ref("")

function isNetwork(d: Device) {
	return adapters.value[d.adapter_type]?.network ?? d.adapter_type !== "file_import"
}

function adapterLabel(code: string) {
	const adapter = adapters.value[code]
	return adapter ? __(adapter.label) : code
}

async function load() {
	loading.value = !devices.value.length
	error.value = ""
	try {
		const [rows, types, locationRows, unmappedRows] = await Promise.all([
			api.get<Device[]>("/devices"),
			api.get<Adapter[]>("/devices/adapters"),
			api.get<{ id: number; name: string }[]>("/admin/work-locations"),
			api.get<{ device_id: number }[]>("/devices/users/unmapped"),
		])
		devices.value = rows
		adapters.value = Object.fromEntries(types.map((a) => [a.code, a]))
		locations.value = Object.fromEntries(locationRows.map((b) => [b.id, b.name]))
		const perDevice: Record<number, number> = {}
		for (const u of unmappedRows) perDevice[u.device_id] = (perDevice[u.device_id] || 0) + 1
		unmapped.value = perDevice
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

async function test(d: Device) {
	busy.value = d.id + "test"
	try {
		const r = await api.post<{ model: string | null; user_count: number; record_count: number }>(
			`/devices/${d.id}/test`
		)
		toast.success(__("Connected: {0}", [r.model || d.name]), {
			description: fa(__("{0} users, {1} records", [r.user_count ?? 0, r.record_count ?? 0])),
		})
		await load()
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

async function sync(d: Device) {
	busy.value = d.id + "sync"
	try {
		const r = await api.post<SyncResult>(`/devices/${d.id}/sync`)
		if (r.ok) toast.success(fa(__("{0} new punches", [r.created])))
		else toast.error(r.message || __("Error"), { duration: 10000 })
		await load()
		refreshCounts(true)
	} catch (e) {
		toast.error((e as Error).message)
		await load()
	} finally {
		busy.value = ""
	}
}

onMounted(load)
</script>
