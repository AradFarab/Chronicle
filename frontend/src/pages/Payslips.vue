<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Payslips')" back="manage">
			<Button icon-left="lucide-settings" :route="{ name: 'payslip-settings' }">{{ __("Settings") }}</Button>
		</PageHeader>
		<p class="text-sm text-ink-gray-6">
			{{
				__(
					"Upload the PDF of the payroll software: each page is matched to an employee by the personnel code printed on it. Then send every employee a private link by SMS."
				)
			}}
		</p>

		<div class="flex flex-wrap items-center gap-2">
			<Button icon="lucide-chevron-right" :aria-label="__('Previous year')" @click="year--" />
			<span class="hz-num w-16 text-center font-semibold">{{ fa(year) }}</span>
			<Button icon="lucide-chevron-left" :aria-label="__('Next year')" @click="year++" />
			<Select v-model="month" :options="monthOptions" class="w-40" />
		</div>
		<ErrorMessage :message="error" />

		<section class="hz-card flex flex-col gap-3">
			<h2 class="font-semibold">{{ __("1. Upload the payslips of {0}", [MONTHS[month - 1]]) }}</h2>
			<input ref="picker" type="file" accept="application/pdf,.pdf" multiple class="text-sm" @change="chosen = picker?.files?.length ?? 0" />
			<div>
				<Button variant="solid" icon-left="lucide-upload" :disabled="!chosen" :loading="busy === 'upload'" @click="upload">{{
					__("Upload and match")
				}}</Button>
			</div>
			<div v-if="data?.rejections.length" class="rounded-4 border border-outline-amber-2 bg-surface-amber-1 p-3 text-sm">
				<div class="mb-2 flex items-center gap-2">
					<span class="lucide-triangle-alert size-4 text-ink-amber-7" />
					<span class="flex-1 font-medium">{{ __("{0} pages could not be used", [fa(data.rejections.length)]) }}</span>
					<Button size="sm" @click="clearRejections">{{ __("Clear this list") }}</Button>
				</div>
				<ul class="flex flex-col gap-1 text-ink-gray-7">
					<li v-for="r in data.rejections" :key="r.id">
						<span dir="ltr" class="font-medium">{{ r.source_name }}</span>
						<span v-if="r.page_no" class="hz-num"> · {{ __("page {0}", [fa(r.page_no)]) }}</span>
						— {{ r.reason }}
					</li>
				</ul>
			</div>
		</section>

		<section class="hz-card flex flex-col gap-3">
			<div class="flex flex-wrap items-center gap-3">
				<h2 class="flex-1 font-semibold">{{ __("2. Check and send") }}</h2>
				<Select v-model="mode" :options="modeOptions" class="w-64" />
				<Button variant="solid" icon-left="lucide-send" :loading="busy === 'preview'" @click="openPreview">{{
					__("Preview the SMS")
				}}</Button>
			</div>
			<div v-if="data" class="hz-num flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-gray-6">
				<span>{{ __("Employees: {0}", [fa(data.counts.employees)]) }}</span>
				<span>{{ __("With a payslip: {0}", [fa(data.counts.payslips)]) }}</span>
				<span>{{ __("Without: {0}", [fa(data.counts.missing)]) }}</span>
				<span>{{ __("Blocked: {0}", [fa(data.counts.blocked)]) }}</span>
				<span>{{ __("SMS sent: {0}", [fa(data.counts.sent)]) }}</span>
				<span>{{ __("SMS failed: {0}", [fa(data.counts.failed)]) }}</span>
				<span>{{ __("Opened: {0}", [fa(data.counts.viewed)]) }}</span>
			</div>
			<DataTable :columns="columns" :rows="data?.rows ?? []" :loading="loading" row-key="employee_id" storage-key="payslips">
				<template #cell-problem="{ row: r }">
					<span v-if="r.problem" class="text-ink-amber-7">{{ problemLabel(r.problem) }}</span>
					<span v-else class="lucide-check size-4 text-ink-green-3" />
				</template>
				<template #cell-sms="{ row: r }">
					<span v-if="r.link" :class="smsClass(r.link.sms_status)" :title="r.link.sms_error ?? ''">{{ smsLabel(r.link.sms_status) }}</span>
				</template>
				<template #cell-actions="{ row: r }">
					<span class="flex items-center gap-1">
						<Button v-if="r.payslip" size="sm" icon="lucide-eye" :aria-label="__('View')" :tooltip="__('View')" @click="view(r)" />
						<Button
							v-if="r.link && r.link.state === 'active'"
							size="sm"
							icon="lucide-link-2-off"
							:aria-label="__('Void the link')"
							:tooltip="__('Void the link')"
							@click="voidLink(r)"
						/>
						<Button
							v-if="r.payslip"
							size="sm"
							theme="red"
							variant="subtle"
							icon="lucide-trash-2"
							:aria-label="__('Delete')"
							:tooltip="__('Delete')"
							@click="remove(r)"
						/>
					</span>
				</template>
			</DataTable>
		</section>

		<Dialog v-model:open="previewOpen" :title="__('Send the payslip links')" size="lg">
			<div v-if="preview" class="flex flex-col gap-3 text-sm">
				<p v-if="preview.unavailable" class="flex gap-2 rounded-4 bg-surface-amber-1 p-3 text-ink-amber-7">
					<span class="lucide-triangle-alert mt-0.5 size-4 shrink-0" />{{ preview.unavailable }}
				</p>
				<p class="hz-num font-medium">{{ __("{0} people will get an SMS now.", [fa(preview.count)]) }}</p>
				<p v-if="preview.replacing" class="hz-num text-ink-amber-7">
					{{ __("{0} of them already have a link; it stops working and the new one replaces it.", [fa(preview.replacing)]) }}
				</p>
				<div v-if="preview.sample">
					<p class="mb-1 text-ink-gray-5">{{ __("The first message:") }}</p>
					<pre class="whitespace-pre-wrap rounded-4 bg-surface-gray-2 p-3 text-xs">{{ preview.sample }}</pre>
				</div>
				<div v-if="preview.blocked.length">
					<p class="mb-1 text-ink-gray-5">{{ __("Left out ({0}):", [fa(preview.blocked.length)]) }}</p>
					<ul class="max-h-40 overflow-y-auto text-ink-gray-7">
						<li v-for="b in preview.blocked" :key="b.employee_id">
							<span dir="ltr">{{ b.code }}</span> {{ b.full_name }} — {{ problemLabel(b.problem) }}
						</li>
					</ul>
				</div>
			</div>
			<template #actions>
				<Button variant="solid" :disabled="!preview || !preview.count || !!preview.unavailable" :loading="busy === 'send'" @click="send">{{
					__("Send")
				}}</Button>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { Button, Dialog, ErrorMessage, Select, toast } from "frappe-ui"
import { computed, onMounted, ref, watch } from "vue"
import DataTable from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa, MONTHS } from "@/lib/jalali"
import { session } from "@/lib/session"
import type { TableColumn } from "@/lib/table"
import type { PayslipMonth, PayslipPreview, PayslipRow } from "@/lib/types"

const today = session.today || "1405/01/01"
const year = ref(Number(today.slice(0, 4)))
const month = ref(Number(today.slice(5, 7)))
const data = ref<PayslipMonth | null>(null)
const preview = ref<PayslipPreview | null>(null)
const previewOpen = ref(false)
const mode = ref("unsent")
const loading = ref(false)
const busy = ref("")
const error = ref("")
const picker = ref<HTMLInputElement | null>(null)
const chosen = ref(0)

const monthOptions = MONTHS.map((label, i) => ({ value: i + 1, label }))
const modeOptions = computed(() => [
	{ value: "unsent", label: __("People without a working link") },
	{ value: "all", label: __("Everyone (replaces the old links)") },
])

function problemLabel(code: NonNullable<PayslipRow["problem"]>): string {
	switch (code) {
		case "no_payslip":
			return __("No payslip uploaded")
		case "not_active":
			return __("Not an active employee")
		case "national_mismatch":
			return __("The national id on the page is not theirs")
		case "no_national_id":
			return __("The employee has no national id")
		case "bad_mobile":
			return __("The mobile number is missing or wrong")
	}
}

function smsLabel(status: string): string {
	return status === "sent" ? __("Sent") : status === "failed" ? __("Failed") : __("Waiting")
}

function smsClass(status: string): string {
	return status === "sent" ? "text-ink-green-3" : status === "failed" ? "text-ink-red-3" : "text-ink-gray-5"
}

function stateLabel(state: string): string {
	switch (state) {
		case "active":
			return __("Works")
		case "expired":
			return __("Expired")
		case "exhausted":
			return __("Opened the most times")
		case "voided":
			return __("Replaced or voided")
		default:
			return __("Locked after wrong answers")
	}
}

const columns: TableColumn<PayslipRow>[] = [
	{ key: "code", label: __("Code"), class: "font-medium" },
	{ key: "full_name", label: __("Name"), class: "min-w-40" },
	{ key: "mobile", label: __("Mobile"), format: (r) => fa(r.mobile ?? "") },
	{ key: "problem", label: __("Ready"), value: (r) => (r.problem ? problemLabel(r.problem) : __("Ready")) },
	{ key: "sms", label: __("SMS"), value: (r) => (r.link ? smsLabel(r.link.sms_status) : "") },
	{ key: "link_state", label: __("Link"), value: (r) => (r.link ? stateLabel(r.link.state) : "") },
	{
		key: "views",
		label: __("Opened"),
		type: "number",
		value: (r) => r.link?.view_count ?? 0,
		format: (r) => (r.link ? fa(`${r.link.view_count}/${r.link.max_views}`) : ""),
	},
	{ key: "actions", label: "", sortable: false, filterable: false },
]

async function load() {
	error.value = ""
	loading.value = true
	try {
		data.value = await api.get<PayslipMonth>(`/payslips/${year.value}/${month.value}`)
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

async function upload() {
	const files = picker.value?.files
	if (!files?.length) return
	busy.value = "upload"
	error.value = ""
	try {
		const form = new FormData()
		for (const f of Array.from(files)) form.append("files", f)
		const r = await api.upload<{ created: number; replaced: number; rejected: number; mismatch: number }>(
			`/payslips/${year.value}/${month.value}/upload`,
			form
		)
		toast.success(__("{0} new, {1} replaced, {2} not used", [fa(r.created), fa(r.replaced), fa(r.rejected)]))
		if (picker.value) picker.value.value = ""
		chosen.value = 0
		await load()
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

async function clearRejections() {
	try {
		await api.del(`/payslips/${year.value}/${month.value}/rejections`)
		await load()
	} catch (e) {
		toast.error((e as Error).message)
	}
}

async function view(r: PayslipRow) {
	// open the tab first: a browser blocks a window opened after an await
	const tab = window.open("", "_blank")
	try {
		const pdf = await api.get<Blob>(`/payslips/item/${r.payslip!.id}`)
		const url = URL.createObjectURL(new Blob([pdf], { type: "application/pdf" }))
		if (tab) tab.location.href = url
		else window.location.href = url
	} catch (e) {
		tab?.close()
		toast.error((e as Error).message)
	}
}

async function voidLink(r: PayslipRow) {
	if (!window.confirm(__("Stop the link of {0} from working?", [r.full_name]))) return
	try {
		await api.post(`/payslips/link/${r.link!.id}/void`)
		await load()
	} catch (e) {
		toast.error((e as Error).message)
	}
}

async function remove(r: PayslipRow) {
	if (!window.confirm(__("Delete the payslip of {0}? Its link stops working.", [r.full_name]))) return
	try {
		await api.del(`/payslips/item/${r.payslip!.id}`)
		await load()
	} catch (e) {
		toast.error((e as Error).message)
	}
}

async function openPreview() {
	busy.value = "preview"
	error.value = ""
	try {
		preview.value = await api.post<PayslipPreview>(`/payslips/${year.value}/${month.value}/send-preview`, { mode: mode.value })
		previewOpen.value = true
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

async function send() {
	busy.value = "send"
	try {
		const r = await api.post<{ queued: number }>(`/payslips/${year.value}/${month.value}/send`, { mode: mode.value })
		toast.success(__("{0} SMS were queued; the server sends them in a moment", [fa(r.queued)]))
		previewOpen.value = false
		await load()
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

watch([year, month], load)
onMounted(load)
</script>
