<template>
	<dl class="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
		<div v-for="item in items" :key="item.label">
			<dt class="text-xs text-ink-gray-5">{{ item.label }}</dt>
			<dd class="hz-num mt-0.5 text-base font-semibold" :class="item.class">{{ item.value }}</dd>
		</div>
	</dl>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { clock, duration } from "@/lib/format"
import { __ } from "@/lib/i18n"
import type { Attendance } from "@/lib/types"

const props = defineProps<{ attendance: Attendance; inProgress?: boolean }>()

const items = computed(() => {
	const a = props.attendance
	const list = [
		{ label: __("First In"), value: clock(a.first_in) },
		{ label: __("Last Out"), value: clock(a.last_out) },
		{ label: __("Required"), value: duration(a.required_minutes) },
		{ label: __("Worked"), value: duration(a.worked_minutes, true) },
	]
	const extra = [
		{ label: __("Late"), value: a.late_minutes, class: "text-ink-amber-6" },
		{ label: __("Early Leave"), value: a.early_leave_minutes, class: "text-ink-amber-6" },
		{ label: __("Absence (Hours)"), value: a.absence_minutes, class: "text-ink-red-6" },
		{ label: __("Leave (Hours)"), value: a.leave_minutes, class: "" },
		{ label: __("Mission (Hours)"), value: a.mission_minutes, class: "" },
		{
			label: __("Overtime"),
			value:
				(a.overtime_normal_minutes || 0) +
				(a.overtime_exceptional_minutes || 0) +
				(a.overtime_emergency_minutes || 0),
			class: "text-ink-green-6",
		},
		{ label: __("Unapproved Extra Work"), value: a.unapproved_extra_minutes, class: "" },
	]
	return [
		...list.map((i) => ({ ...i, class: "" })),
		...extra
			.filter((i) => i.value && !(props.inProgress && i.class === "text-ink-red-6"))
			.map((i) => ({ ...i, value: duration(i.value) })),
	]
})
</script>
