<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('SMS history')" back="sms" />
		<ErrorMessage :message="error" />

		<section v-if="review.length" class="rounded-4 border border-outline-amber-2 bg-surface-amber-1 p-3 text-sm">
			<div class="mb-2 flex items-start gap-2">
				<span class="lucide-triangle-alert mt-0.5 size-4 shrink-0 text-ink-amber-7" />
				<p class="text-ink-gray-8">
					{{
						__(
							"{0} messages have an unknown outcome: the panel did not answer, so they may or may not have been sent. They are never sent again by themselves. Look at the panel's report and mark each one.",
							[fa(review.length)]
						)
					}}
				</p>
			</div>
			<ul class="flex flex-col gap-1">
				<li v-for="m in review" :key="m.id" class="flex flex-wrap items-center gap-2">
					<span dir="ltr" class="hz-num w-28">{{ fa(m.to) }}</span>
					<span class="flex-1">{{ m.event_label }} · {{ fa(m.queued_at ?? "") }}</span>
					<Button size="sm" @click="resolve(m, 'sent')">{{ __("It was sent") }}</Button>
					<Button size="sm" @click="resolve(m, 'failed')">{{ __("It was not sent") }}</Button>
				</li>
			</ul>
		</section>

		<div class="flex flex-wrap items-end gap-2">
			<Select v-model="filters.status" :label="__('Status')" :options="statusOptions" class="w-44" />
			<Select v-model="filters.event" :label="__('Event')" :options="eventOptions" class="w-56" />
			<TextInput v-model="filters.to" dir="ltr" :label="__('Mobile number')" placeholder="09121234567" />
			<Button :loading="loading" @click="load">{{ __("Search") }}</Button>
		</div>

		<DataTable :columns="columns" :rows="items" :loading="loading" row-key="id" storage-key="sms-messages" :on-row-click="open">
			<template #cell-status="{ row: m }">
				<span :class="smsStatusClass(m.status)">{{ smsStatusLabel(m.status) }}</span>
			</template>
		</DataTable>
		<p v-if="total > items.length" class="hz-num text-sm text-ink-gray-5">{{ __("{0} of {1}", [fa(items.length), fa(total)]) }}</p>

		<Dialog v-model:open="detailOpen" :title="__('Message')" size="2xl">
			<div v-if="detail" class="flex flex-col gap-3 text-sm">
				<dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
					<dt class="text-ink-gray-5">{{ __("To") }}</dt>
					<dd dir="ltr" class="hz-num">{{ fa(detail.to) }}</dd>
					<dt class="text-ink-gray-5">{{ __("Event") }}</dt>
					<dd>{{ detail.event_label }}</dd>
					<dt class="text-ink-gray-5">{{ __("Status") }}</dt>
					<dd :class="smsStatusClass(detail.status)">{{ smsStatusLabel(detail.status) }}</dd>
					<dt class="text-ink-gray-5">{{ __("Panel") }}</dt>
					<dd>{{ detail.provider_code ?? "—" }} <span v-if="detail.provider_message_id" dir="ltr">· {{ detail.provider_message_id }}</span></dd>
					<dt class="text-ink-gray-5">{{ __("Attempts") }}</dt>
					<dd class="hz-num">{{ fa(detail.attempts) }}</dd>
					<dt class="text-ink-gray-5">{{ __("Queued") }}</dt>
					<dd class="hz-num">{{ fa(detail.queued_at ?? "") }}</dd>
					<dt class="text-ink-gray-5">{{ __("Sent") }}</dt>
					<dd class="hz-num">{{ fa(detail.sent_at ?? "—") }}</dd>
				</dl>
				<p v-if="detail.error" class="rounded-4 bg-surface-red-1 p-2 text-ink-red-3">{{ detail.error }}</p>
				<div>
					<p class="mb-1 font-medium">{{ __("Values of the event") }}</p>
					<pre class="overflow-x-auto rounded-4 bg-surface-gray-2 p-2 text-xs" dir="ltr">{{ JSON.stringify(detail.context, null, 2) }}</pre>
				</div>
				<div v-if="detail.raw_request">
					<p class="mb-1 font-medium">{{ __("What was sent to the panel") }}</p>
					<pre class="overflow-x-auto rounded-4 bg-surface-gray-2 p-2 text-xs" dir="ltr">{{ JSON.stringify(detail.raw_request, null, 2) }}</pre>
				</div>
				<div v-if="detail.raw_response">
					<p class="mb-1 font-medium">{{ __("What the panel answered") }}</p>
					<pre class="overflow-x-auto rounded-4 bg-surface-gray-2 p-2 text-xs" dir="ltr">{{ JSON.stringify(detail.raw_response, null, 2) }}</pre>
				</div>
			</div>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { Button, Dialog, ErrorMessage, Select, TextInput, toast } from "frappe-ui"
import { computed, onMounted, reactive, ref } from "vue"
import DataTable from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import { smsStatusClass, smsStatusLabel } from "@/lib/sms"
import type { TableColumn } from "@/lib/table"
import type { SmsEvent, SmsMessage, SmsStatus } from "@/lib/types"

const items = ref<SmsMessage[]>([])
const total = ref(0)
const review = ref<SmsMessage[]>([])
const events = ref<SmsEvent[]>([])
const detail = ref<SmsMessage | null>(null)
const detailOpen = ref(false)
const loading = ref(false)
const error = ref("")
const filters = reactive({ status: "", event: "", to: "" })

const STATUSES: SmsStatus[] = ["queued", "sending", "sent", "delivered", "failed", "skipped", "unknown"]
const statusOptions = computed(() => [
	{ value: "", label: __("All") },
	...STATUSES.map((s) => ({ value: s, label: smsStatusLabel(s) })),
])
const eventOptions = computed(() => [{ value: "", label: __("All") }, ...events.value.map((e) => ({ value: e.code, label: e.label }))])

const columns: TableColumn<SmsMessage>[] = [
	{ key: "queued_at", label: __("Queued"), format: (m) => fa(m.queued_at ?? "") },
	{ key: "to", label: __("To"), format: (m) => fa(m.to), class: "font-medium" },
	{ key: "event_label", label: __("Event") },
	{ key: "status", label: __("Status"), value: (m) => smsStatusLabel(m.status) },
	{ key: "provider_code", label: __("Panel") },
	{ key: "attempts", label: __("Attempts"), type: "number", format: (m) => fa(m.attempts) },
	{ key: "error", label: __("Error"), class: "min-w-48" },
]

async function load() {
	loading.value = true
	error.value = ""
	try {
		const [list, due, ev] = await Promise.all([
			api.get<{ total: number; items: SmsMessage[] }>("/sms/messages", { ...filters, limit: 200 }),
			api.get<SmsMessage[]>("/sms/review"),
			events.value.length ? Promise.resolve(events.value) : api.get<SmsEvent[]>("/sms/events"),
		])
		items.value = list.items
		total.value = list.total
		review.value = due
		events.value = ev
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

async function open(m: SmsMessage) {
	try {
		detail.value = await api.get<SmsMessage>(`/sms/messages/${m.id}`)
		detailOpen.value = true
	} catch (e) {
		toast.error((e as Error).message)
	}
}

async function resolve(m: SmsMessage, outcome: "sent" | "failed") {
	const note = window.prompt(__("Note (what the panel's report says)")) ?? ""
	try {
		await api.post(`/sms/messages/${m.id}/resolve`, { outcome, note })
		await load()
	} catch (e) {
		toast.error((e as Error).message)
	}
}

onMounted(load)
</script>
