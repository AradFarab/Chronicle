<template>
	<div class="flex flex-col gap-3 rounded-4 border border-outline-gray-2 p-3">
		<div>
			<p class="text-sm font-medium">{{ __("Quick rotation") }}</p>
			<p class="text-xs text-ink-gray-5">
				{{ __("Fills the days of the cycle: shift A for some days, then shift B, then days off. You can edit the rows afterwards.") }}
			</p>
		</div>
		<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
			<Combobox v-model="shiftA" :label="__('Shift A')" :options="refOptions('shifts')" :placeholder="__('Choose')" />
			<TextInput
				:model-value="daysA === null ? '' : String(daysA)"
				type="number"
				dir="ltr"
				:label="__('Days of shift A')"
				@update:model-value="(v: string) => (daysA = v === '' ? null : Number(v))"
			/>
			<Combobox v-model="shiftB" :label="__('Shift B')" :options="refOptions('shifts')" :placeholder="__('Choose')" />
			<TextInput
				:model-value="daysB === null ? '' : String(daysB)"
				type="number"
				dir="ltr"
				:label="__('Days of shift B')"
				@update:model-value="(v: string) => (daysB = v === '' ? null : Number(v))"
			/>
			<TextInput
				:model-value="daysOff === null ? '' : String(daysOff)"
				type="number"
				dir="ltr"
				:label="__('Days off at the end (optional)')"
				@update:model-value="(v: string) => (daysOff = v === '' ? null : Number(v))"
			/>
		</div>
		<p v-if="total" class="hz-num text-xs text-ink-gray-5">{{ fa(__("The cycle will have {0} days", [total])) }}</p>
		<ErrorMessage :message="error" />
		<div>
			<Button icon-left="lucide-wand-sparkles" @click="fill">{{ __("Fill the days") }}</Button>
		</div>
	</div>
</template>

<script setup lang="ts">
import { Button, Combobox, ErrorMessage, TextInput } from "frappe-ui"
import { computed, ref } from "vue"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import { refOptions } from "@/lib/refs"

interface CycleDay {
	weekday: null
	cycle_day: number
	shift_id: number | null
}

const emit = defineEmits<{ fill: [rows: CycleDay[]] }>()

const shiftA = ref<number | null>(null)
const daysA = ref<number | null>(null)
const shiftB = ref<number | null>(null)
const daysB = ref<number | null>(null)
const daysOff = ref<number | null>(null)
const error = ref("")

const count = (n: number | null) => (n && n > 0 ? Math.floor(n) : 0)
const total = computed(() => count(daysA.value) + count(daysB.value) + count(daysOff.value))

function fill() {
	error.value = ""
	if (count(daysA.value) && !shiftA.value) return void (error.value = __("Choose shift A"))
	if (count(daysB.value) && !shiftB.value) return void (error.value = __("Choose shift B"))
	if (!total.value) return void (error.value = __("Enter the number of days"))
	const shifts: (number | null)[] = [
		...Array(count(daysA.value)).fill(shiftA.value),
		...Array(count(daysB.value)).fill(shiftB.value),
		...Array(count(daysOff.value)).fill(null),
	]
	emit(
		"fill",
		shifts.map((shift_id, i) => ({ weekday: null, cycle_day: i + 1, shift_id }))
	)
}
</script>
