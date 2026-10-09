<template>
	<div class="space-y-4">
		<div class="flex items-center gap-2">
			<Button :aria-label="__('Previous month')" icon="lucide-chevron-right" @click="go(-1)" />
			<h1 class="flex-1 text-center text-lg font-bold">{{ MONTHS[jm - 1] }} {{ fa(jy) }}</h1>
			<Button :aria-label="__('Next month')" icon="lucide-chevron-left" @click="go(1)" />
		</div>

		<EmployeePicker
			v-if="session.is_manager || session.is_admin"
			v-model="employee"
			:label="__('Employee')"
			:placeholder="session.employee ? undefined : __('Choose an employee')"
		/>

		<ErrorMessage v-if="error" :message="error" />

		<section v-if="days.length" class="grid grid-cols-2 gap-3 sm:grid-cols-4">
			<div v-for="s in summary" :key="s.label" class="hz-card !p-3">
				<p class="text-xs text-ink-gray-5">{{ s.label }}</p>
				<p class="hz-num mt-1 text-lg font-bold" :class="s.class">{{ s.value }}</p>
			</div>
		</section>

		<section class="hz-card !p-2 sm:!p-4">
			<div class="grid grid-cols-7 gap-1 text-center text-xs text-ink-gray-5">
				<span v-for="(w, i) in WEEKDAYS_SHORT" :key="i" class="py-1" :class="i === 6 ? 'text-ink-red-5' : ''">{{
					w
				}}</span>
			</div>
			<div class="grid grid-cols-7 gap-1">
				<span v-for="n in offset" :key="'b' + n" />
				<button
					v-for="d in days"
					:key="d.jdate"
					type="button"
					class="relative flex aspect-square flex-col items-center justify-center rounded-4 border text-sm sm:aspect-[4/3]"
					:class="cellClass(d)"
					@click="open(d)"
				>
					<span class="hz-num font-semibold">{{ fa(Number(d.jdate.slice(8))) }}</span>
					<span v-if="d.attendance?.worked_minutes" class="hz-num hidden text-[11px] opacity-80 sm:block">{{
						duration(d.attendance.worked_minutes)
					}}</span>
					<span
						v-if="d.attendance && dotClass(d)"
						class="absolute bottom-1 size-1.5 rounded-full sm:bottom-1.5"
						:class="dotClass(d)"
					/>
					<span v-if="d.predicted" class="absolute top-0.5 text-[10px]" style="inset-inline-end: 0.25rem"
						>*</span
					>
				</button>
			</div>
			<div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 px-1 text-xs text-ink-gray-5">
				<span v-for="l in legend" :key="l.label" class="flex items-center gap-1">
					<span class="size-2 rounded-full" :class="l.class" />{{ l.label }}
				</span>
				<span v-if="days.some((d) => d.predicted)">* {{ __("Predicted holiday") }}</span>
			</div>
		</section>

		<Dialog v-model:open="dialogOpen" :title="selected ? displayLong(selected.jdate) : ''">
			<div v-if="selected" class="space-y-4">
				<div class="flex flex-wrap items-center gap-2">
					<StatusBadge :status="selected.attendance?.status || dayStatus(selected)" />
					<span v-if="selected.holiday" class="text-sm text-ink-red-6">{{ selected.holiday }}</span>
				</div>
				<p v-if="loadingDay" class="text-sm text-ink-gray-5">{{ __("Loading...") }}</p>
				<template v-else-if="dayData">
					<DayNumbers v-if="dayData.attendance" :attendance="dayData.attendance" />
					<ul v-if="dayWarnings.length" class="space-y-1 text-sm text-ink-amber-7">
						<li v-for="w in dayWarnings" :key="w">{{ w }}</li>
					</ul>
					<PunchList :punches="dayPunches(dayData)" />
				</template>
			</div>
			<template #actions>
				<div class="flex flex-wrap gap-2">
					<Button
						v-if="canCorrect"
						variant="solid"
						icon-left="lucide-pencil"
						:route="{
							name: 'new-request',
							params: { kind: 'correction' },
							query: { date: selected?.jdate, employee: employee || undefined },
						}"
					>
						{{ __("Manual entry") }}
					</Button>
					<Button
						v-if="canCorrect"
						icon-left="lucide-plane"
						:route="{
							name: 'new-request',
							params: { kind: 'leave' },
							query: { date: selected?.jdate, employee: employee || undefined },
						}"
					>
						{{ __("Leave") }}
					</Button>
				</div>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { Button, Dialog, ErrorMessage } from "frappe-ui"
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import DayNumbers from "@/components/DayNumbers.vue"
import EmployeePicker from "@/components/EmployeePicker.vue"
import PunchList from "@/components/PunchList.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { api } from "@/lib/api"
import { dayPunches, duration } from "@/lib/format"
import { __ } from "@/lib/i18n"
import {
	MONTHS,
	WEEKDAYS_SHORT,
	addMonths,
	displayLong,
	fa,
	format,
	monthLength,
	parse,
	today,
	weekday,
} from "@/lib/jalali"
import { session } from "@/lib/session"
import type { Attendance, DayDetails } from "@/lib/types"
import { warningMessages } from "@/lib/warnings"

interface Day {
	jdate: string
	day_type: string
	holiday: string
	predicted: boolean
	attendance: Attendance | null
}

interface Holiday {
	jdate: string
	title: string
	holiday_type: string
	status: string
	scope: string
	work_location_id: number | null
	closure_pay_mode: string | null
}

const route = useRoute()
const router = useRouter()
const now = parse(session.today) ?? today()
const jy = computed(() => Number(route.params.year) || now.jy)
const jm = computed(() => Number(route.params.month) || now.jm)
const employee = ref<number | null>(Number(route.query.employee) || session.employee?.id || null)

const days = ref<Day[]>([])
const error = ref("")

const offset = computed(() => {
	const first = days.value[0] && parse(days.value[0].jdate)
	return first ? weekday(first) : 0
})

// holidays of a year, for the days the engine has not calculated yet
const holidayCache = new Map<number, Promise<Holiday[]>>()
function holidaysOf(year: number): Promise<Holiday[]> {
	if (!holidayCache.has(year)) {
		const request = api.get<Holiday[]>("/calendar/holidays", { year })
		request.catch(() => holidayCache.delete(year))
		holidayCache.set(year, request)
	}
	return holidayCache.get(year)!
}

/** Same rule as the server (hozur.jalali.holidays.day_off_kind); null = not a day off. */
function dayOffKind(h: Holiday): string | null {
	if (h.holiday_type === "office_closure")
		return { paid_holiday: "official_holiday", employer_paid: "company_holiday" }[h.closure_pay_mode ?? ""] ?? null
	return h.holiday_type === "company_internal" ? "company_holiday" : "official_holiday"
}

function holidayApplies(h: Holiday): boolean {
	if (h.scope === "country" || h.scope === "company") return true
	// a work-location holiday is known here only for your own work location; calculated days carry the truth
	return (
		h.scope === "work_location" &&
		employee.value === session.employee?.id &&
		h.work_location_id === session.employee?.work_location_id
	)
}

async function load() {
	error.value = ""
	days.value = []
	if (!employee.value) return
	const year = jy.value
	const month = jm.value
	const first = format({ jy: year, jm: month, jd: 1 })
	const last = format({ jy: year, jm: month, jd: monthLength(year, month) })
	try {
		const [rows, holidays] = await Promise.all([
			api.get<Attendance[]>("/attendance", { from_date: first, to_date: last, employee_id: employee.value }),
			holidaysOf(year).catch(() => [] as Holiday[]),
		])
		const byDate = new Map(rows.map((r) => [r.jdate, r]))
		const list: Day[] = []
		for (let jd = 1; jd <= monthLength(year, month); jd++) {
			const date = { jy: year, jm: month, jd }
			const jdate = format(date)
			const offs = holidays.filter((h) => h.jdate === jdate && dayOffKind(h) && holidayApplies(h))
			const kind = offs.some((h) => dayOffKind(h) === "official_holiday")
				? "official_holiday"
				: offs.length
				? "company_holiday"
				: weekday(date) === 6
				? "friday"
				: "workday"
			const attendance = byDate.get(jdate) ?? null
			list.push({
				jdate,
				day_type: attendance?.day_type || kind,
				holiday: attendance?.holiday_title || [...new Set(offs.map((h) => h.title))].join(" / "),
				predicted: offs.some((h) => h.status === "predicted"),
				attendance,
			})
		}
		days.value = list
	} catch (e) {
		error.value = (e as Error).message
	}
}

function go(delta: number) {
	const next = addMonths(jy.value, jm.value, delta)
	router.replace({ name: "month", params: { year: next.jy, month: next.jm }, query: route.query })
}

watch([jy, jm, employee], load, { immediate: true })
watch(employee, (value) => router.replace({ query: { ...route.query, employee: value || undefined } }))

const STATUS_DOT: Record<string, string> = {
	present: "bg-surface-green-5",
	incomplete: "bg-surface-amber-5",
	absent: "bg-surface-red-5",
	leave: "bg-surface-violet-5",
	mission: "bg-surface-blue-5",
}

function dotClass(d: Day) {
	return STATUS_DOT[d.attendance?.status || ""] || ""
}

const HOLIDAYS = ["official_holiday", "company_holiday"]

function dayStatus(d: Day) {
	if (HOLIDAYS.includes(d.day_type)) return "holiday"
	if (d.day_type === "friday") return "rest_day"
	return ""
}

function cellClass(d: Day) {
	const isToday = d.jdate === session.today
	const holiday = HOLIDAYS.includes(d.day_type)
	return [
		isToday ? "border-outline-gray-5" : "border-transparent",
		holiday
			? "bg-surface-red-1 text-ink-red-6"
			: d.day_type === "friday"
			? "bg-surface-gray-2 text-ink-red-5"
			: "bg-surface-gray-1 hover:bg-surface-gray-2",
	].join(" ")
}

const legend = computed(() => [
	{ label: __("Present"), class: STATUS_DOT.present },
	{ label: __("Incomplete"), class: STATUS_DOT.incomplete },
	{ label: __("Absent"), class: STATUS_DOT.absent },
	{ label: __("Leave"), class: STATUS_DOT.leave },
	{ label: __("Mission"), class: STATUS_DOT.mission },
])

const summary = computed(() => {
	const rows = days.value.map((d) => d.attendance).filter((a): a is Attendance => !!a)
	const sum = (key: keyof Attendance) => rows.reduce((t, r) => t + (Number(r[key]) || 0), 0)
	const count = (...statuses: string[]) => rows.filter((r) => statuses.includes(r.status)).length
	return [
		{ label: __("Days Present"), value: fa(count("present", "incomplete")), class: "" },
		{ label: __("Absence (Days)"), value: fa(count("absent")), class: count("absent") ? "text-ink-red-6" : "" },
		{ label: __("Worked"), value: duration(sum("worked_minutes"), true), class: "" },
		{
			label: __("Late"),
			value: duration(sum("late_minutes"), true),
			class: sum("late_minutes") ? "text-ink-amber-6" : "",
		},
	]
})

// day dialog
const dialogOpen = ref(false)
const selected = ref<Day | null>(null)
const dayData = ref<DayDetails | null>(null)
const loadingDay = ref(false)
const dayWarnings = computed(() => warningMessages(dayData.value?.attendance?.warnings))
const canCorrect = computed(
	() =>
		!!selected.value &&
		!dayData.value?.period_closed &&
		(session.is_admin || (!!employee.value && employee.value === session.employee?.id))
)

async function open(d: Day) {
	if (!employee.value) return
	selected.value = d
	dialogOpen.value = true
	dayData.value = null
	loadingDay.value = true
	try {
		dayData.value = await api.get<DayDetails>("/attendance/day", { jdate: d.jdate, employee_id: employee.value })
	} catch (e) {
		error.value = (e as Error).message
		dialogOpen.value = false
	} finally {
		loadingDay.value = false
	}
}
</script>
