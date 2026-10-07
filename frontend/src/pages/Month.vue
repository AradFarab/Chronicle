<template>
	<div class="space-y-4">
		<div class="flex items-center gap-2">
			<Button :aria-label="__('Previous month')" icon="lucide-chevron-right" @click="go(-1)" />
			<h1 class="flex-1 text-center text-lg font-bold">{{ MONTHS[jm - 1] }} {{ fa(jy) }}</h1>
			<Button :aria-label="__('Next month')" icon="lucide-chevron-left" @click="go(1)" />
		</div>

		<EmployeePicker
			v-if="session.is_manager || session.is_operator"
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
					<PunchList :punches="dayData.punches" />
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
import { call } from "@/lib/api"
import { duration } from "@/lib/format"
import { __ } from "@/lib/i18n"
import { MONTHS, WEEKDAYS_SHORT, addMonths, displayLong, fa, parse, today, weekday } from "@/lib/jalali"
import { session } from "@/lib/session"
import type { Attendance, Punch } from "@/lib/types"
import { warningMessages } from "@/lib/warnings"

interface Day {
	jdate: string
	weekday: string
	day_type: string
	holiday: string
	predicted: boolean
	attendance: (Attendance & { worked_minutes: number }) | null
}

const route = useRoute()
const router = useRouter()
const now = today()
const jy = computed(() => Number(route.params.year) || now.jy)
const jm = computed(() => Number(route.params.month) || now.jm)
const employee = ref<string | null>(String(route.query.employee || "") || session.employee?.name || null)

const days = ref<Day[]>([])
const error = ref("")

const offset = computed(() => {
	const first = days.value[0] && parse(days.value[0].jdate)
	return first ? weekday(first) : 0
})

async function load() {
	error.value = ""
	days.value = []
	if (!employee.value) return
	try {
		const result = await call<{ days: Day[] }>("hozur.api.pwa.month", {
			year: jy.value,
			month: jm.value,
			employee: employee.value,
		})
		days.value = result.days
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
	Present: "bg-surface-green-5",
	Incomplete: "bg-surface-amber-5",
	Absent: "bg-surface-red-5",
	Leave: "bg-surface-violet-5",
	Mission: "bg-surface-blue-5",
}

function dotClass(d: Day) {
	return STATUS_DOT[d.attendance?.status || ""] || ""
}

const HOLIDAYS = ["Official Holiday", "Company Holiday"]

function dayStatus(d: Day) {
	if (HOLIDAYS.includes(d.day_type)) return "Holiday"
	if (d.day_type === "Friday") return "Rest Day"
	return ""
}

function cellClass(d: Day) {
	const isToday = d.jdate === session.today
	const holiday = HOLIDAYS.includes(d.day_type)
	return [
		isToday ? "border-outline-gray-5" : "border-transparent",
		holiday
			? "bg-surface-red-1 text-ink-red-6"
			: d.day_type === "Friday"
			? "bg-surface-gray-2 text-ink-red-5"
			: "bg-surface-gray-1 hover:bg-surface-gray-2",
	].join(" ")
}

const legend = computed(() => [
	{ label: __("Present"), class: STATUS_DOT.Present },
	{ label: __("Incomplete"), class: STATUS_DOT.Incomplete },
	{ label: __("Absent"), class: STATUS_DOT.Absent },
	{ label: __("Leave"), class: STATUS_DOT.Leave },
	{ label: __("Mission"), class: STATUS_DOT.Mission },
])

const summary = computed(() => {
	const rows = days.value.map((d) => d.attendance).filter((a): a is NonNullable<Day["attendance"]> => !!a)
	const sum = (key: keyof Attendance) => rows.reduce((t, r) => t + (Number(r[key]) || 0), 0)
	const count = (...statuses: string[]) => rows.filter((r) => statuses.includes(r.status)).length
	return [
		{ label: __("Days Present"), value: fa(count("Present", "Incomplete")), class: "" },
		{ label: __("Absence (Days)"), value: fa(count("Absent")), class: count("Absent") ? "text-ink-red-6" : "" },
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
const dayData = ref<{ attendance: Attendance | null; punches: Punch[] } | null>(null)
const loadingDay = ref(false)
const dayWarnings = computed(() => warningMessages(dayData.value?.attendance?.warnings))
const canCorrect = computed(
	() => !!selected.value && (session.is_operator || employee.value === session.employee?.name)
)

async function open(d: Day) {
	selected.value = d
	dialogOpen.value = true
	dayData.value = null
	loadingDay.value = true
	try {
		dayData.value = await call("hozur.api.pwa.day", { jdate: d.jdate, employee: employee.value })
	} catch (e) {
		error.value = (e as Error).message
		dialogOpen.value = false
	} finally {
		loadingDay.value = false
	}
}
</script>
