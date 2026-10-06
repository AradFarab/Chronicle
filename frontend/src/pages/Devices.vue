<template>
	<div class="space-y-4">
		<div class="flex items-center gap-2">
			<h1 class="flex-1 text-lg font-bold">{{ __("Attendance devices") }}</h1>
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
			<li v-for="d in devices" :key="d.name" class="hz-card space-y-3">
				<RouterLink :to="{ name: 'device', params: { name: d.name } }" class="flex items-start gap-3">
					<span class="flex size-10 shrink-0 items-center justify-center rounded-4 bg-surface-gray-2">
						<span
							:class="d.adapter_type === 'File Import' ? 'lucide-file-up' : 'lucide-fingerprint'"
							class="size-5"
						/>
					</span>
					<span class="min-w-0 flex-1">
						<span class="flex flex-wrap items-center gap-2">
							<span class="font-semibold">{{ d.name }}</span>
							<Badge v-if="!d.enabled" theme="gray" :label="__('Disabled')" />
							<StatusBadge
								v-if="d.last_sync_status"
								:status="d.last_sync_status"
								:label="__(d.last_sync_status)"
							/>
						</span>
						<span class="mt-0.5 block text-sm text-ink-gray-5">
							{{ __(d.adapter_type) }}
							<template v-if="d.host">
								· <span dir="ltr" class="hz-num">{{ d.host }}:{{ d.port }}</span></template
							>
							<template v-if="d.branch"> · {{ d.branch }}</template>
						</span>
					</span>
					<span class="lucide-chevron-left size-4 text-ink-gray-4" />
				</RouterLink>
				<dl class="hz-num grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
					<div>
						<dt class="text-xs text-ink-gray-5">{{ __("Last Read") }}</dt>
						<dd>{{ d.last_sync ? fa(d.last_sync) : "—" }}</dd>
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
						<dd :class="d.unmapped_users ? 'font-semibold text-ink-amber-7' : ''">
							{{ fa(d.unmapped_users) }}
						</dd>
					</div>
				</dl>
				<p
					v-if="d.last_sync_status === 'Error' && d.last_error"
					class="rounded-4 bg-surface-red-1 p-2 text-sm text-ink-red-7"
				>
					{{ d.last_error }}
				</p>
				<div v-if="d.adapter_type !== 'File Import'" class="flex flex-wrap gap-2">
					<Button icon-left="lucide-plug-zap" :loading="busy === d.name + 'test'" @click="test(d)">
						{{ __("Test Connection") }}
					</Button>
					<Button icon-left="lucide-refresh-cw" :loading="busy === d.name + 'sync'" @click="sync(d)">
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
import StatusBadge from "@/components/StatusBadge.vue"
import { call } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"

interface Device {
	name: string
	adapter_type: string
	branch: string | null
	enabled: number
	host: string | null
	port: number | null
	last_sync: string | null
	last_sync_status: string | null
	last_error: string | null
	user_count: number | null
	record_count: number | null
	unmapped_users: number
}

const devices = ref<Device[]>([])
const loading = ref(false)
const error = ref("")
const busy = ref("")

async function load() {
	loading.value = true
	error.value = ""
	try {
		devices.value = await call<Device[]>("hozur.api.pwa.devices")
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

async function test(d: Device) {
	busy.value = d.name + "test"
	try {
		const r = await call<{ model: string; user_count: number; record_count: number }>(
			"hozur.devices.service.test_connection",
			{ device: d.name }
		)
		toast.success(__("Connected: {0}", [r.model || d.name]), {
			description: fa(__("{0} users, {1} records", [r.user_count, r.record_count])),
		})
		await load()
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

async function sync(d: Device) {
	busy.value = d.name + "sync"
	try {
		const r = await call<{ created: number; existing: number }>("hozur.devices.service.sync_now", {
			device: d.name,
		})
		toast.success(fa(__("{0} new punches", [r.created])))
		await load()
	} catch (e) {
		toast.error((e as Error).message)
		await load()
	} finally {
		busy.value = ""
	}
}

onMounted(load)
</script>
