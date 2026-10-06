<template>
	<div ref="root" class="relative">
		<label v-if="label" class="mb-1.5 block text-xs text-ink-gray-5">{{ label }}</label>
		<button
			type="button"
			class="flex h-9 w-full items-center gap-2 rounded-3 border border-transparent bg-surface-gray-2 px-2.5 text-start text-base hover:bg-surface-gray-3 focus-visible:border-outline-gray-4 focus-visible:outline-none"
			:aria-expanded="open"
			@click="toggle"
		>
			<span class="lucide-calendar size-4 text-ink-gray-5" />
			<span class="hz-num flex-1" :class="modelValue ? 'text-ink-gray-8' : 'text-ink-gray-4'">
				{{ modelValue ? displayLong(modelValue) : placeholder || __("Choose a date") }}
			</span>
		</button>
		<div
			v-if="open"
			class="absolute z-30 mt-1 w-72 rounded-6 border border-outline-gray-2 bg-surface-elevation-2 p-3 shadow-xl"
			style="inset-inline-start: 0"
		>
			<div class="mb-2 flex items-center justify-between">
				<button
					type="button"
					class="rounded-2 p-1 hover:bg-surface-gray-2"
					:aria-label="__('Previous month')"
					@click="move(-1)"
				>
					<span class="lucide-chevron-right size-4" />
				</button>
				<span class="text-sm font-semibold">{{ MONTHS[view.jm - 1] }} {{ fa(view.jy) }}</span>
				<button
					type="button"
					class="rounded-2 p-1 hover:bg-surface-gray-2"
					:aria-label="__('Next month')"
					@click="move(1)"
				>
					<span class="lucide-chevron-left size-4" />
				</button>
			</div>
			<div class="grid grid-cols-7 gap-1 text-center text-xs text-ink-gray-5">
				<span v-for="(w, i) in WEEKDAYS_SHORT" :key="i" :class="i === 6 ? 'text-ink-red-4' : ''">{{ w }}</span>
			</div>
			<div class="mt-1 grid grid-cols-7 gap-1 text-center">
				<span v-for="n in offset" :key="'b' + n" />
				<button
					v-for="d in days"
					:key="d"
					type="button"
					class="hz-num aspect-square rounded-3 text-sm"
					:class="cellClass(d)"
					@click="pick(d)"
				>
					{{ fa(d) }}
				</button>
			</div>
			<div class="mt-3 flex justify-between text-sm">
				<button type="button" class="text-ink-blue-link" @click="pickToday">{{ __("Today") }}</button>
				<button v-if="clearable && modelValue" type="button" class="text-ink-gray-5" @click="clear">
					{{ __("Clear") }}
				</button>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue"
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

const props = defineProps<{
	modelValue?: string | null
	label?: string
	placeholder?: string
	clearable?: boolean
	min?: string | null
}>()
const emit = defineEmits<{ "update:modelValue": [value: string | null] }>()

const open = ref(false)
const root = ref<HTMLElement>()
const now = today()
const start = parse(props.modelValue || "") ?? now
const view = reactive({ jy: start.jy, jm: start.jm })

const days = computed(() => monthLength(view.jy, view.jm))
const offset = computed(() => weekday({ jy: view.jy, jm: view.jm, jd: 1 }))
const selected = computed(() => parse(props.modelValue || ""))

function toggle() {
	open.value = !open.value
	const d = selected.value
	if (open.value && d) Object.assign(view, { jy: d.jy, jm: d.jm })
}

function move(delta: number) {
	Object.assign(view, addMonths(view.jy, view.jm, delta))
}

function value(d: number) {
	return format({ jy: view.jy, jm: view.jm, jd: d })
}

function disabled(d: number) {
	return !!props.min && value(d) < props.min
}

function cellClass(d: number) {
	const s = selected.value
	if (s && s.jy === view.jy && s.jm === view.jm && s.jd === d) return "hz-brand font-semibold"
	if (disabled(d)) return "text-ink-gray-3 cursor-not-allowed"
	const isToday = now.jy === view.jy && now.jm === view.jm && now.jd === d
	const friday = weekday({ jy: view.jy, jm: view.jm, jd: d }) === 6
	return [
		"hover:bg-surface-gray-2",
		isToday ? "ring-1 ring-outline-gray-4" : "",
		friday ? "text-ink-red-4" : "text-ink-gray-8",
	].join(" ")
}

function pick(d: number) {
	if (disabled(d)) return
	emit("update:modelValue", value(d))
	open.value = false
}

function pickToday() {
	Object.assign(view, { jy: now.jy, jm: now.jm })
	pick(now.jd)
}

function clear() {
	emit("update:modelValue", null)
	open.value = false
}

function outside(event: Event) {
	if (open.value && root.value && !root.value.contains(event.target as Node)) open.value = false
}
onMounted(() => document.addEventListener("pointerdown", outside))
onBeforeUnmount(() => document.removeEventListener("pointerdown", outside))
</script>
