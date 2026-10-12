<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Backups')" back="manage" />
		<div class="space-y-1 text-sm text-ink-gray-6">
			<p>{{ __("A backup holds the whole database and the uploaded files in one .zip file.") }}</p>
			<p v-if="data">
				{{ __("Backups are kept on the server in this folder:") }}
				<code class="rounded-2 bg-surface-gray-2 px-1.5 py-0.5 text-xs" dir="ltr">{{ data.folder }}</code>
			</p>
			<p>{{ __("If the server's disk fails, these copies are lost with it: download a copy now and then and keep it somewhere else.") }}</p>
		</div>

		<ErrorMessage :message="error" />
		<p v-if="data && !data.available" class="flex gap-2 rounded-4 bg-surface-amber-1 p-3 text-sm text-ink-amber-7">
			<span class="lucide-triangle-alert mt-0.5 size-4 shrink-0" />
			{{
				__(
					"pg_dump is not installed on the server, so no backup can be taken. Install the PostgreSQL client tools (the Docker image already has them)."
				)
			}}
		</p>

		<section class="hz-card flex flex-col gap-3">
			<div class="flex flex-wrap items-center gap-3">
				<h2 class="flex-1 font-semibold">{{ __("Backups on the server") }}</h2>
				<Button
					variant="solid"
					icon-left="lucide-database-backup"
					:disabled="!data?.available"
					:loading="busy === 'create'"
					@click="create"
					>{{ __("Take a backup now") }}</Button
				>
			</div>
			<p v-if="busy === 'create'" class="text-sm text-ink-gray-5">
				{{ __("Taking the backup. This can take a few minutes for a large database; keep this page open.") }}
			</p>
			<p v-if="loading && !data" class="text-sm text-ink-gray-5">{{ __("Loading...") }}</p>
			<p v-else-if="data && !data.backups.length" class="text-sm text-ink-gray-5">{{ __("There is no backup yet.") }}</p>
			<ul v-else-if="data" class="divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-1">
				<li
					v-for="b in data.backups"
					:key="b.name"
					class="flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-center sm:gap-3"
				>
					<span class="flex min-w-0 flex-1 items-center gap-3">
						<span class="lucide-archive size-4 shrink-0 text-ink-gray-5" />
						<span class="min-w-0">
							<span class="hz-num block text-sm font-medium">{{ displayLong(b.jdate) }} · {{ fa(b.time) }}</span>
							<span class="block truncate text-xs text-ink-gray-5" dir="ltr">{{ b.name }}</span>
						</span>
					</span>
					<span class="flex items-center gap-3">
						<Badge :theme="b.automatic ? 'blue' : 'gray'" :label="b.automatic ? __('Automatic') : __('Manual')" />
						<span class="hz-num flex-1 text-sm text-ink-gray-6 sm:w-20 sm:flex-none sm:text-end">{{ size(b.size) }}</span>
						<Button
							icon="lucide-download"
							:aria-label="__('Download')"
							:tooltip="__('Download')"
							:loading="busy === 'get:' + b.name"
							@click="download(b)"
						/>
						<Button
							icon="lucide-trash-2"
							theme="red"
							variant="subtle"
							:aria-label="__('Delete')"
							:tooltip="__('Delete')"
							:loading="busy === 'del:' + b.name"
							@click="remove(b)"
						/>
					</span>
				</li>
			</ul>
		</section>

		<section v-if="data" class="hz-card flex flex-col gap-4">
			<h2 class="font-semibold">{{ __("Automatic backup") }}</h2>
			<Switch
				v-model="schedule.enabled"
				:label="__('Take a backup automatically every night')"
				:description="__('The worker process takes it; automatic backups beyond the number to keep are deleted, the oldest first.')"
			/>
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
				<Select v-model="schedule.hour" :label="__('At this hour')" :options="hours" :disabled="!schedule.enabled" />
				<TextInput
					v-model="schedule.keep"
					type="number"
					min="1"
					max="365"
					dir="ltr"
					:label="__('Automatic backups to keep')"
					:disabled="!schedule.enabled"
				/>
			</div>
			<div>
				<Button variant="solid" :loading="busy === 'schedule'" @click="saveSchedule">{{ __("Save") }}</Button>
			</div>
		</section>

		<section class="hz-card flex flex-col gap-2 text-sm">
			<h2 class="font-semibold">{{ __("Restoring a backup") }}</h2>
			<p class="text-ink-gray-6">
				{{
					__(
						"Restoring replaces everything (all data and uploaded files) with the contents of the backup. It is done on the server, not here: stop the worker first, then run:"
					)
				}}
			</p>
			<pre class="overflow-x-auto rounded-4 bg-surface-gray-2 p-3 text-xs" dir="ltr">chronicle backup restore &lt;file&gt;</pre>
			<p class="text-ink-gray-6">{{ __("With Docker:") }}</p>
			<pre class="overflow-x-auto rounded-4 bg-surface-gray-2 p-3 text-xs" dir="ltr">
docker compose -f docker/compose.yml --env-file docker/.env stop worker
docker compose -f docker/compose.yml --env-file docker/.env exec app chronicle backup restore &lt;name&gt;
docker compose -f docker/compose.yml --env-file docker/.env start worker</pre
			>
		</section>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, ErrorMessage, Select, Switch, TextInput, toast } from "frappe-ui"
import { computed, onMounted, reactive, ref } from "vue"
import PageHeader from "@/components/PageHeader.vue"
import { api, downloadGet } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { displayLong, fa } from "@/lib/jalali"
import type { Backup, BackupSchedule } from "@/lib/types"

interface Backups {
	backups: Backup[]
	schedule: BackupSchedule
	available: boolean
	folder: string
}

const data = ref<Backups | null>(null)
const loading = ref(false)
const busy = ref("")
const error = ref("")
const schedule = reactive({ enabled: false, hour: 2 as number | string, keep: 7 as number | string })

const hours = computed(() =>
	Array.from({ length: 24 }, (_, h) => ({ value: h, label: fa(`${String(h).padStart(2, "0")}:00`) }))
)

function size(bytes: number): string {
	if (bytes >= 1024 * 1024) return fa(__("{0} MB", [(bytes / 1024 / 1024).toFixed(1)]))
	return fa(__("{0} KB", [Math.max(1, Math.round(bytes / 1024))]))
}

async function load() {
	loading.value = true
	error.value = ""
	try {
		data.value = await api.get<Backups>("/admin/backups")
		Object.assign(schedule, data.value.schedule)
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

async function create() {
	busy.value = "create"
	error.value = ""
	try {
		await api.post<Backup>("/admin/backups")
		toast.success(__("The backup was taken"))
		await load()
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

async function download(b: Backup) {
	busy.value = "get:" + b.name
	try {
		await downloadGet(`/admin/backups/${encodeURIComponent(b.name)}`, undefined, b.name)
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

async function remove(b: Backup) {
	if (!window.confirm(__("Delete the backup of {0}? It cannot be brought back.", [`${displayLong(b.jdate)} ${fa(b.time)}`])))
		return
	busy.value = "del:" + b.name
	try {
		await api.del(`/admin/backups/${encodeURIComponent(b.name)}`)
		toast.success(__("Deleted"))
		await load()
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

async function saveSchedule() {
	busy.value = "schedule"
	try {
		const saved = await api.put<BackupSchedule>("/admin/backups/schedule", {
			enabled: schedule.enabled,
			hour: Number(schedule.hour),
			keep: Number(schedule.keep),
		})
		Object.assign(schedule, saved)
		toast.success(__("Saved"))
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

onMounted(load)
</script>
