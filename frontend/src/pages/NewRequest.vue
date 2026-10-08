<template>
	<form class="space-y-4" @submit.prevent="submit">
		<h1 class="text-lg font-bold">{{ __("New request") }}</h1>
		<Segmented v-model="kind" :options="kinds" />

		<section class="hz-card space-y-4">
			<EmployeePicker
				v-if="canChooseEmployee"
				v-model="employee"
				:label="__('Employee')"
				:placeholder="session.employee ? undefined : __('Choose an employee')"
			/>

			<!-- leave -->
			<template v-if="kind === 'leave'">
				<Select v-model="leave.leave_type_id" :label="__('Leave Type')" :options="leaveTypeOptions" />
				<Segmented v-if="allowHourly" v-model="leave.unit" :options="units" />
				<template v-if="leave.unit === 'daily'">
					<div class="grid gap-4 sm:grid-cols-2">
						<JalaliDatePicker v-model="leave.from_date" :label="__('From Date')" />
						<JalaliDatePicker v-model="leave.to_date" :label="__('To Date')" :min="leave.from_date" />
					</div>
				</template>
				<template v-else>
					<JalaliDatePicker v-model="leave.jdate" :label="__('Date')" />
					<div class="grid grid-cols-2 gap-4">
						<TimeInput v-model="leave.from_time" :label="__('From Time')" />
						<TimeInput v-model="leave.to_time" :label="__('To Time')" />
					</div>
				</template>
				<Textarea v-model="leave.reason" :label="__('Reason')" :rows="2" />
			</template>

			<!-- mission -->
			<template v-else-if="kind === 'mission'">
				<Segmented v-model="mission.unit" :options="units" />
				<TextInput v-model="mission.destination" :label="__('Destination')" />
				<template v-if="mission.unit === 'daily'">
					<div class="grid gap-4 sm:grid-cols-2">
						<JalaliDatePicker v-model="mission.from_date" :label="__('From Date')" />
						<JalaliDatePicker v-model="mission.to_date" :label="__('To Date')" :min="mission.from_date" />
					</div>
				</template>
				<template v-else>
					<JalaliDatePicker v-model="mission.jdate" :label="__('Date')" />
					<div class="grid grid-cols-2 gap-4">
						<TimeInput v-model="mission.from_time" :label="__('From Time')" />
						<TimeInput v-model="mission.to_time" :label="__('To Time')" />
					</div>
				</template>
				<Textarea v-model="mission.reason" :label="__('Reason')" :rows="2" />
			</template>

			<!-- overtime -->
			<template v-else-if="kind === 'overtime'">
				<p v-if="assigning" class="rounded-4 bg-surface-amber-1 p-3 text-sm text-ink-amber-7">
					{{ __("Overtime you assign needs the employee's acceptance (Article 59).") }}
				</p>
				<JalaliDatePicker v-model="overtime.jdate" :label="__('Date')" />
				<Select v-model="overtime.overtime_kind" :label="__('Overtime Kind')" :options="overtimeKinds" />
				<div class="grid grid-cols-2 gap-4">
					<TimeInput v-model="overtime.from_time" :label="__('From Time')" />
					<TimeInput v-model="overtime.to_time" :label="__('To Time')" />
				</div>
				<Textarea v-model="overtime.reason" :label="__('Reason')" :rows="2" />
			</template>

			<!-- manual punch entry (attendance correction) -->
			<template v-else>
				<p class="text-sm text-ink-gray-5">
					{{
						__(
							"Add the times the device missed. They count only after approval; device punches are never changed."
						)
					}}
				</p>
				<JalaliDatePicker v-model="correction.jdate" :label="__('Date')" />
				<div v-if="existing.length" class="space-y-1">
					<p class="text-xs text-ink-gray-5">{{ __("Punches of this day") }}</p>
					<label
						v-for="(p, i) in existing"
						:key="(p.id ?? 'm') + '-' + i"
						class="flex items-center gap-3 rounded-4 px-2 py-1.5 hover:bg-surface-gray-1"
					>
						<span
							class="hz-num font-semibold"
							:class="p.is_duplicate || p.ignored || (p.id && ignored.includes(p.id)) ? 'line-through opacity-50' : ''"
							>{{ clock(p.time) }}</span
						>
						<span class="text-sm text-ink-gray-5"
							>{{ directionLabel(p.direction) }} · {{ sourceLabel(p.source) }}</span
						>
						<span class="flex-1" />
						<template v-if="canIgnore(p)">
							<input v-model="ignored" type="checkbox" :value="p.id" class="rounded-2" />
							<span class="text-xs text-ink-gray-5">{{ __("Ignore") }}</span>
						</template>
					</label>
				</div>
				<div class="space-y-2">
					<p class="text-xs text-ink-gray-5">{{ __("Times to add") }}</p>
					<div v-for="(item, i) in correction.items" :key="i" class="flex items-end gap-2">
						<TimeInput v-model="item.time" class="flex-1" :label="i === 0 ? __('Time') : undefined" />
						<div class="w-28">
							<Select v-model="item.direction" :options="directions" />
						</div>
						<Button
							:aria-label="__('Remove')"
							icon="lucide-trash-2"
							@click="correction.items.splice(i, 1)"
						/>
					</div>
					<Button icon-left="lucide-plus" @click="addTime">{{ __("Add a time") }}</Button>
				</div>
				<Textarea v-model="correction.reason" :label="__('Reason')" :rows="2" />
			</template>
		</section>

		<ErrorMessage v-if="error" :message="error" />
		<div class="flex gap-2">
			<Button type="submit" variant="solid" size="md" :loading="saving" class="flex-1">{{ __("Submit") }}</Button>
			<Button size="md" :route="{ name: 'requests' }">{{ __("Cancel") }}</Button>
		</div>
	</form>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, Select, TextInput, Textarea, toast } from "frappe-ui"
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import EmployeePicker from "@/components/EmployeePicker.vue"
import JalaliDatePicker from "@/components/JalaliDatePicker.vue"
import Segmented from "@/components/Segmented.vue"
import TimeInput from "@/components/TimeInput.vue"
import { api } from "@/lib/api"
import { refreshCounts } from "@/lib/counts"
import { clock, dayPunches, directionLabel, sourceLabel, statusLabel } from "@/lib/format"
import { __ } from "@/lib/i18n"
import { session } from "@/lib/session"
import type { DayDetails, LeaveType, Punch, RequestView } from "@/lib/types"

const route = useRoute()
const router = useRouter()
const KINDS = ["leave", "mission", "overtime", "correction"]
const kind = ref(KINDS.includes(String(route.params.kind)) ? String(route.params.kind) : "leave")
watch(kind, (value) => router.replace({ name: "new-request", params: { kind: value }, query: route.query }))

const kinds = computed(() => [
	{ value: "leave", label: __("Leave") },
	{ value: "mission", label: __("Mission") },
	{ value: "overtime", label: __("Overtime") },
	{ value: "correction", label: __("Manual entry") },
])
const units = computed(() => [
	{ value: "daily", label: __("Daily") },
	{ value: "hourly", label: __("Hourly") },
])
const directions = computed(() => [
	{ value: "in", label: __("In") },
	{ value: "out", label: __("Out") },
	{ value: "unknown", label: __("Unknown") },
])
const overtimeKinds = computed(() => [
	{ value: "normal", label: __("Normal") },
	{ value: "exceptional", label: __("Exceptional") },
	{ value: "emergency", label: __("Emergency") },
])

const date = String(route.query.date || "") || session.today
const employee = ref<number | null>(Number(route.query.employee) || session.employee?.id || null)
const canChooseEmployee = computed(() => session.is_operator || (kind.value === "overtime" && session.is_manager))
// the request is for someone else only when the picker is shown and another person is chosen
const forSomeoneElse = computed(
	() => canChooseEmployee.value && !!employee.value && employee.value !== session.employee?.id
)
const assigning = computed(() => kind.value === "overtime" && forSomeoneElse.value)

const leave = reactive({
	leave_type_id: null as number | null,
	unit: "daily",
	from_date: date as string | null,
	to_date: date as string | null,
	jdate: date as string | null,
	from_time: null as string | null,
	to_time: null as string | null,
	reason: "",
})
const mission = reactive({
	unit: "daily",
	destination: "",
	from_date: date as string | null,
	to_date: date as string | null,
	jdate: date as string | null,
	from_time: null as string | null,
	to_time: null as string | null,
	reason: "",
})
const overtime = reactive({
	jdate: date as string | null,
	overtime_kind: "normal",
	from_time: null as string | null,
	to_time: null as string | null,
	reason: "",
})
const correction = reactive({
	jdate: date as string | null,
	items: [{ time: null as string | null, direction: "in" }],
	reason: "",
})

const saving = ref(false)
const error = ref("")

const leaveTypes = ref<LeaveType[]>([])
const leaveTypeOptions = computed(() => leaveTypes.value.map((t) => ({ value: t.id, label: t.name })))
const allowHourly = computed(() => !!leaveTypes.value.find((t) => t.id === leave.leave_type_id)?.allow_hourly)
watch(allowHourly, (allowed) => {
	if (!allowed) leave.unit = "daily"
})

onMounted(async () => {
	try {
		leaveTypes.value = await api.get<LeaveType[]>("/leave-types")
		leave.leave_type_id = leaveTypes.value[0]?.id ?? null
	} catch (e) {
		error.value = (e as Error).message
	}
})

// existing punches of the correction day, so a wrong device punch can be ignored
const existing = ref<Punch[]>([])
const ignored = ref<number[]>([])
watch(
	() => [kind.value, correction.jdate, employee.value],
	async () => {
		existing.value = []
		ignored.value = []
		const person = forSomeoneElse.value ? employee.value : session.employee?.id
		if (kind.value !== "correction" || !correction.jdate || !person) return
		try {
			existing.value = dayPunches(
				await api.get<DayDetails>("/attendance/day", { jdate: correction.jdate, employee_id: person })
			)
		} catch {
			// the form still works without the list
		}
	},
	{ immediate: true }
)

// only raw punches that still count can be set aside
function canIgnore(p: Punch) {
	return !!p.id && p.source !== "manual" && !p.is_duplicate && !p.ignored
}

function addTime() {
	const last = correction.items[correction.items.length - 1]
	correction.items.push({ time: null, direction: last?.direction === "in" ? "out" : "in" })
}

function values(): Record<string, unknown> {
	const base = forSomeoneElse.value ? { employee_id: employee.value } : {}
	if (kind.value === "leave") {
		const v = { ...leave }
		return v.unit === "daily"
			? { ...base, ...v, jdate: null, from_time: null, to_time: null }
			: { ...base, ...v, from_date: null, to_date: null }
	}
	if (kind.value === "mission") {
		const v = { ...mission }
		return v.unit === "daily"
			? { ...base, ...v, jdate: null, from_time: null, to_time: null }
			: { ...base, ...v, from_date: null, to_date: null }
	}
	if (kind.value === "overtime") return { ...base, ...overtime }
	return {
		...base,
		jdate: correction.jdate,
		reason: correction.reason,
		items: [
			...correction.items
				.filter((i) => i.time)
				.map((i) => ({ action: "add_punch", time: i.time, direction: i.direction })),
			...ignored.value.map((id) => ({ action: "ignore_punch", raw_punch_id: id })),
		],
	}
}

async function submit() {
	saving.value = true
	error.value = ""
	try {
		const result = await api.post<RequestView>(`/requests/${kind.value}`, values())
		toast.success(__("Request submitted: {0}", [statusLabel(result.status)]))
		refreshCounts(true)
		router.push({ name: "requests" })
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		saving.value = false
	}
}
</script>
