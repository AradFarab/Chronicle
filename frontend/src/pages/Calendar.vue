<template>
	<div class="flex flex-col gap-4">
		<div class="flex items-center gap-2">
			<Button :aria-label="__('Back')" icon="lucide-arrow-right" :route="{ name: 'manage' }" />
			<h1 class="flex-1 text-xl font-semibold">{{ __("Holidays") }}</h1>
			<ExcelImport v-if="hasImport('holidays')" name="holidays" @done="load" />
			<Button icon-left="lucide-refresh-cw" @click="refreshOpen = true">{{ __("Yearly refresh") }}</Button>
			<Button variant="solid" icon-left="lucide-plus" @click="edit(null)">{{ __("New") }}</Button>
		</div>

		<div class="flex items-center gap-2">
			<Button icon="lucide-chevron-right" :aria-label="__('Previous year')" @click="year--" />
			<span class="hz-num w-16 text-center font-semibold">{{ fa(year) }}</span>
			<Button icon="lucide-chevron-left" :aria-label="__('Next year')" @click="year++" />
			<span v-if="yearInfo" class="text-sm text-ink-gray-5">
				{{ label(holidayStatusOptions, yearInfo.status) }} ·
				{{ __("Source: {0}", [label(calendarSourceOptions, yearInfo.source)]) }}
				<template v-if="yearInfo.refreshed_at"> · {{ __("Refreshed {0}", [fa(yearInfo.refreshed_at)]) }}</template>
			</span>
		</div>
		<ErrorMessage :message="error" />

		<div class="overflow-x-auto rounded-6 border border-outline-gray-1 bg-surface-base">
			<table class="w-full text-sm">
				<thead class="bg-surface-gray-1 text-ink-gray-5">
					<tr>
						<th class="px-3 py-2 text-start font-medium">{{ __("Date") }}</th>
						<th class="px-3 py-2 text-start font-medium">{{ __("Title") }}</th>
						<th class="px-3 py-2 text-start font-medium">{{ __("Type") }}</th>
						<th class="px-3 py-2 text-start font-medium">{{ __("Applies to") }}</th>
						<th class="px-3 py-2 text-start font-medium">{{ __("Status") }}</th>
					</tr>
				</thead>
				<tbody>
					<tr
						v-for="h in holidays"
						:key="h.id"
						class="cursor-pointer border-t border-outline-gray-1 hover:bg-surface-gray-1"
						@click="edit(h)"
					>
						<td class="hz-num whitespace-nowrap px-3 py-2">{{ displayLong(h.jdate) }}</td>
						<td class="px-3 py-2">{{ h.title }}</td>
						<td class="px-3 py-2">{{ label(holidayTypeOptions, h.holiday_type) }}</td>
						<td class="px-3 py-2">{{ label(holidayScopeOptions, h.scope) }}</td>
						<td class="px-3 py-2">
							<Badge :theme="h.status === 'confirmed' ? 'green' : 'amber'">{{
								label(holidayStatusOptions, h.status)
							}}</Badge>
						</td>
					</tr>
					<tr v-if="!holidays.length">
						<td colspan="5" class="px-3 py-6 text-center text-ink-gray-5">{{ __("No holidays for this year") }}</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- one holiday -->
		<Dialog v-model:open="formOpen" :title="current ? __('Holiday') : __('New holiday')">
			<div class="flex flex-col gap-4">
				<JalaliDatePicker v-model="form.jdate" :label="__('Date')" />
				<TextInput v-model="form.title" :label="__('Title')" />
				<Select v-model="form.holiday_type" :label="__('Type')" :options="holidayTypeOptions()" />
				<Select
					v-if="form.holiday_type === 'office_closure'"
					v-model="form.closure_pay_mode"
					:label="__('How is it paid?')"
					:options="closurePayOptions()"
				/>
				<Select v-model="form.scope" :label="__('Applies to')" :options="holidayScopeOptions()" />
				<Combobox
					v-if="form.scope === 'province'"
					v-model="form.province_id"
					:label="__('Province')"
					:options="refOptions('provinces')"
				/>
				<Combobox
					v-if="form.scope === 'work_location'"
					v-model="form.work_location_id"
					:label="__('Work location')"
					:options="refOptions('work-locations')"
				/>
				<Select v-model="form.status" :label="__('Status')" :options="holidayStatusOptions()" />
				<Textarea :model-value="form.note ?? ''" @update:model-value="(v: string) => (form.note = v)" :label="__('Note')" :rows="2" />
				<Textarea v-if="current" v-model="form.reason" :label="__('Reason for the change') + ' *'" :rows="2" />
				<ErrorMessage :message="formError" />
			</div>
			<template #actions>
				<div class="flex gap-2">
					<Button variant="solid" :loading="busy" @click="save">{{ __("Save") }}</Button>
					<Button v-if="current" theme="red" :loading="busy" @click="remove">{{ __("Delete") }}</Button>
				</div>
			</template>
		</Dialog>

		<!-- yearly refresh: preview, then apply -->
		<Dialog v-model:open="refreshOpen" :title="__('Refresh the holidays of a year')" size="3xl">
			<div class="flex flex-col gap-4">
				<p class="text-sm text-ink-gray-6">
					{{
						__(
							"Once a year, load the next year's official holidays. You see every change first; dates you edited by hand and closed months are never changed."
						)
					}}
				</p>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<TextInput v-model="refreshYear" type="number" dir="ltr" :label="__('Year')" />
					<Select v-model="source" :label="__('Source')" :options="calendarSourceOptions()" />
				</div>
				<input v-if="source === 'file'" type="file" accept=".json,.csv" @change="pickFile" />
				<Button :loading="busy" @click="preview">{{ __("Show the changes") }}</Button>
				<ErrorMessage :message="refreshError" />
				<div v-if="plan" class="flex flex-col gap-2">
					<p class="text-sm">
						{{ __("{0} changes · {1} unchanged · {2} edited by hand (kept)", [fa(plan.items.length), fa(plan.unchanged), fa(plan.kept_edits)]) }}
					</p>
					<div class="max-h-80 overflow-y-auto rounded-4 border border-outline-gray-1">
						<label
							v-for="item in plan.items"
							:key="item.key"
							class="flex items-center gap-3 border-b border-outline-gray-1 px-3 py-2 text-sm last:border-0"
						>
							<input v-model="chosen" type="checkbox" :value="item.key" :disabled="item.locked" />
							<Badge :theme="item.action === 'add' ? 'green' : item.action === 'remove' ? 'red' : 'blue'">{{
								actionLabel(item.action)
							}}</Badge>
							<span class="hz-num whitespace-nowrap">{{ display(item.jdate) }}</span>
							<span class="flex-1"
								>{{ item.title }}<template v-if="item.new_title && item.new_title !== item.title">
									→ {{ item.new_title }}</template
								></span
							>
							<span v-if="item.locked" class="text-xs text-ink-gray-5">{{ __("closed month") }}</span>
						</label>
					</div>
				</div>
			</div>
			<template #actions>
				<Button v-if="plan" variant="solid" :loading="busy" @click="apply">{{ __("Apply the chosen changes") }}</Button>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, Combobox, Dialog, ErrorMessage, Select, Textarea, TextInput, toast } from "frappe-ui"
import { computed, onMounted, reactive, ref, watch } from "vue"
import ExcelImport from "@/components/ExcelImport.vue"
import JalaliDatePicker from "@/components/JalaliDatePicker.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { hasImport } from "@/lib/imports"
import { display, displayLong, fa } from "@/lib/jalali"
import {
	calendarSourceOptions,
	closurePayOptions,
	holidayScopeOptions,
	holidayStatusOptions,
	holidayTypeOptions,
	label,
} from "@/lib/labels"
import { refOptions } from "@/lib/refs"
import { session } from "@/lib/session"

interface Holiday {
	id: number
	jdate: string
	title: string
	holiday_type: string
	status: string
	scope: string
	province_id: number | null
	work_location_id: number | null
	closure_pay_mode: string | null
	note: string | null
}

interface YearInfo {
	jyear: number
	status: string
	source: string
	refreshed_at: string | null
}

interface PlanItem {
	key: string
	action: string
	jdate: string
	title: string
	new_title: string | null
	locked: boolean
}

interface Plan {
	items: PlanItem[]
	unchanged: number
	kept_edits: number
}

const year = ref(Number((session.today || "1405").slice(0, 4)))
const holidays = ref<Holiday[]>([])
const years = ref<YearInfo[]>([])
const error = ref("")
const busy = ref(false)

const yearInfo = computed(() => years.value.find((y) => y.jyear === year.value))

const formOpen = ref(false)
const current = ref<Holiday | null>(null)
const formError = ref("")
interface HolidayForm {
	jdate: string | null
	title: string
	holiday_type: string
	scope: string
	status: string
	closure_pay_mode?: string | null
	province_id?: number | null
	work_location_id?: number | null
	note?: string | null
	reason?: string
}

const blank: HolidayForm = {
	jdate: null,
	title: "",
	holiday_type: "company_internal",
	scope: "company",
	status: "confirmed",
	closure_pay_mode: null,
	province_id: null,
	work_location_id: null,
	note: "",
	reason: "",
}
const form = reactive<HolidayForm>({ ...blank })

const refreshOpen = ref(false)
const refreshYear = ref(String(year.value + 1))
const source = ref("time_ir")
const file = ref<File | null>(null)
const plan = ref<Plan | null>(null)
const chosen = ref<string[]>([])
const refreshError = ref("")

function actionLabel(action: string) {
	return { add: __("Add"), remove: __("Remove"), change: __("Change") }[action] ?? action
}

async function load() {
	error.value = ""
	try {
		;[holidays.value, years.value] = await Promise.all([
			api.get<Holiday[]>("/calendar/holidays", { year: year.value }),
			api.get<YearInfo[]>("/calendar/years"),
		])
	} catch (e) {
		error.value = (e as Error).message
	}
}

function edit(h: Holiday | null) {
	current.value = h
	formError.value = ""
	Object.assign(form, blank, h ?? {}, { reason: "" })
	formOpen.value = true
}

async function save() {
	busy.value = true
	formError.value = ""
	try {
		const { reason, ...values } = form
		if (current.value) await api.patch(`/calendar/holidays/${current.value.id}`, { values, reason })
		else await api.post("/calendar/holidays", values)
		toast.success(__("Saved"))
		formOpen.value = false
		load()
	} catch (e) {
		formError.value = (e as Error).message
	} finally {
		busy.value = false
	}
}

async function remove() {
	if (!current.value) return
	const reason = window.prompt(__("Reason for deleting"))
	if (!reason) return
	busy.value = true
	try {
		await api.post(`/calendar/holidays/${current.value.id}/delete`, { reason })
		formOpen.value = false
		load()
	} catch (e) {
		formError.value = (e as Error).message
	} finally {
		busy.value = false
	}
}

function pickFile(event: Event) {
	file.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

function refreshForm(): FormData {
	const data = new FormData()
	data.append("year", refreshYear.value)
	data.append("source", source.value)
	if (source.value === "file" && file.value) data.append("file", file.value)
	return data
}

async function preview() {
	busy.value = true
	refreshError.value = ""
	plan.value = null
	try {
		plan.value = await api.upload<Plan>("/calendar/refresh/preview", refreshForm())
		chosen.value = plan.value.items.filter((i) => !i.locked).map((i) => i.key)
	} catch (e) {
		refreshError.value = (e as Error).message
	} finally {
		busy.value = false
	}
}

async function apply() {
	if (!plan.value) return
	busy.value = true
	refreshError.value = ""
	try {
		const data = refreshForm()
		for (const item of plan.value.items) if (!chosen.value.includes(item.key)) data.append("skip", item.key)
		await api.upload("/calendar/refresh/apply", data)
		toast.success(__("The calendar was refreshed"))
		refreshOpen.value = false
		plan.value = null
		year.value = Number(refreshYear.value)
		load()
	} catch (e) {
		refreshError.value = (e as Error).message
	} finally {
		busy.value = false
	}
}

watch(year, load)
onMounted(load)
</script>
