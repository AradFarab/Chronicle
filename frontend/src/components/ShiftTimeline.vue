<template>
	<div class="flex min-w-0 flex-col gap-3" :class="compact ? 'h-full' : ''">
		<template v-if="!compact">
			<!-- tools -->
			<div class="flex flex-wrap items-center gap-2">
				<div class="flex flex-wrap gap-0.5 rounded-4 bg-surface-gray-2 p-0.5" role="radiogroup" :aria-label="__('Drawing tool')">
					<button
						v-for="kind in KINDS"
						:key="kind"
						type="button"
						role="radio"
						:aria-checked="ownTool === kind"
						class="flex items-center gap-1.5 rounded-3 px-2 py-1 text-sm"
						:class="ownTool === kind ? 'bg-surface-base font-medium text-ink-gray-9 shadow-sm' : 'text-ink-gray-6'"
						@click="ownTool = kind"
					>
						<span class="inline-block size-3 shrink-0 rounded-sm" :style="swatch(kind)" />
						{{ kindLabel(kind) }}
					</button>
				</div>
				<label class="flex items-center gap-1 text-xs text-ink-gray-5">
					{{ __("Snap") }}
					<select
						v-model.number="ownStep"
						class="hz-num h-7 rounded-3 border-none bg-surface-gray-2 py-0 pe-7 ps-2 text-sm text-ink-gray-8 focus:ring-0"
					>
						<option v-for="s in STEPS" :key="s" :value="s">{{ __("{0} min", [fa(s)]) }}</option>
					</select>
				</label>
				<Button
					size="sm"
					:variant="showMorning ? 'subtle' : 'ghost'"
					icon-left="lucide-moon"
					:disabled="crossesMidnight"
					@click="extend = !extend"
					>{{ __("Next morning") }}</Button
				>
				<Button size="sm" variant="ghost" icon-left="lucide-trash-2" :disabled="selected === null" @click="removeSelected">{{
					__("Delete")
				}}</Button>
			</div>
			<p class="text-xs text-ink-gray-5">
				{{
					__(
						"Drag on the empty timeline to draw with the chosen tool. Drag a bar to move it, or its edges to resize it. Select a bar and press Delete to remove it."
					)
				}}
			</p>
		</template>

		<div :class="compact ? 'h-full' : 'overflow-x-auto pb-1'">
			<div :class="compact ? 'h-full' : 'min-w-[36rem]'">
				<!-- the next morning, then the hour labels (right to left: 00:00 at the right edge) -->
				<div v-if="!compact && to > DAY" class="relative h-4" aria-hidden="true">
					<span
						class="absolute inset-y-0 left-0 rounded-t-3 bg-surface-gray-3 px-1 text-center text-[10px] text-ink-gray-6"
						:style="{ width: pctWidth(DAY, to) }"
						>{{ __("Next day") }}</span
					>
				</div>
				<div v-if="!compact" class="relative h-5 text-[11px] text-ink-gray-5" aria-hidden="true">
					<span
						v-for="t in labelledTicks"
						:key="t.minute"
						class="hz-num absolute top-0 translate-x-1/2 whitespace-nowrap"
						:class="t.minute > DAY ? 'text-ink-gray-4' : ''"
						:style="{ right: pct(t.minute) }"
						>{{ fa(t.label) }}</span
					>
				</div>
				<div
					ref="track"
					class="relative select-none overflow-hidden rounded-3 bg-surface-gray-2 outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
					:class="compact ? 'h-full min-h-7' : 'h-14'"
					:style="{ cursor, touchAction: interactive ? 'none' : 'pan-x pan-y', boxShadow: invalid ? 'inset 0 0 0 2px #ef4444' : '' }"
					:tabindex="interactive ? 0 : -1"
					role="application"
					:aria-label="label || __('Shift timeline')"
					@pointerdown="onPointerDown"
					@pointermove="onPointerMove"
					@pointerup="onPointerUp"
					@pointercancel="onPointerUp"
					@pointerleave="hoverCursor = ''"
					@keydown="onKey"
				>
					<!-- the next morning -->
					<div
						v-if="to > DAY"
						class="pointer-events-none absolute inset-y-0 left-0 bg-surface-gray-3"
						:style="{ width: pctWidth(DAY, to) }"
					/>
					<!-- hour lines -->
					<div
						v-for="t in ticks"
						:key="t.minute"
						class="pointer-events-none absolute inset-y-0 border-r"
						:class="t.minute % DAY === 0 ? 'border-outline-gray-5' : t.minute % 360 === 0 ? 'border-outline-gray-3' : 'border-outline-gray-2'"
						:style="{ right: pct(t.minute) }"
					/>
					<!-- a night shift continuing from the day before -->
					<div
						v-for="(g, i) in visibleGhosts"
						:key="'g' + i"
						class="pointer-events-none absolute opacity-35"
						:style="barStyle(g)"
					/>
					<!-- the bars: working hours below, overtime windows and breaks on top -->
					<div
						v-for="item in layered"
						:key="item.index"
						class="pointer-events-none absolute flex items-center overflow-hidden"
						:class="[
							item.bar.kind === 'work' ? 'justify-start ps-1' : 'justify-center',
							selected === item.index ? 'z-10 text-ink-gray-9 outline outline-2 -outline-offset-2' : '',
						]"
						:style="barStyle(item.bar)"
					>
						<span
							v-if="!compact && pxWidth(item.bar) > 46"
							class="hz-num truncate px-1 text-[11px] font-medium"
							:class="item.bar.kind === 'break' ? 'text-black' : 'text-white'"
							>{{ hm(item.bar.kind === "work" ? totals.work : item.bar.end - item.bar.start) }}</span
						>
						<template v-if="selected === item.index">
							<span class="absolute inset-y-1 right-0 w-1 rounded-full bg-ink-gray-9" />
							<span class="absolute inset-y-1 left-0 w-1 rounded-full bg-ink-gray-9" />
						</template>
					</div>
				</div>
			</div>
		</div>

		<template v-if="!compact">
			<!-- exact times, for precise editing (and phones) -->
			<div class="flex flex-col gap-1">
				<div
					v-for="(b, i) in bars"
					:key="i"
					class="flex flex-wrap items-center gap-2 rounded-3 px-2 py-1"
					:class="selected === i ? 'bg-surface-gray-2' : ''"
					@click="selected = i"
				>
					<span class="inline-block size-3 shrink-0 rounded-sm" :style="swatch(b.kind)" />
					<span class="basis-[calc(100%-1.5rem)] text-sm sm:basis-auto sm:w-32">{{ kindLabel(b.kind) }}</span>
					<TimeInput size="sm" :model-value="clock(b.start)" @update:model-value="(v) => setTime(i, 'start', v)" />
					<span v-if="b.start >= DAY" class="text-xs text-ink-gray-5">{{ __("(next day)") }}</span>
					<span class="text-ink-gray-5">–</span>
					<TimeInput size="sm" :model-value="clock(b.end)" @update:model-value="(v) => setTime(i, 'end', v)" />
					<span v-if="b.end > DAY" class="text-xs text-ink-gray-5">{{ __("(next day)") }}</span>
					<Button
						size="sm"
						variant="ghost"
						icon="lucide-trash-2"
						:aria-label="__('Remove')"
						@click.stop="remove(i)"
					/>
				</div>
			</div>
			<div class="flex flex-wrap gap-2">
				<Button v-if="!work" size="sm" icon-left="lucide-plus" @click="addWork">{{ __("Add working hours") }}</Button>
				<Button size="sm" icon-left="lucide-plus" :disabled="!work" @click="addBreak">{{ __("Add a break") }}</Button>
				<Button size="sm" icon-left="lucide-plus" @click="addOvertime">{{ __("Add an overtime window") }}</Button>
			</div>
			<div class="hz-num flex flex-wrap gap-x-4 gap-y-1 text-sm">
				<span class="font-medium">{{ __("Scheduled work: {0}", [hm(totals.work)]) }}</span>
				<span class="text-ink-gray-6">{{ __("Breaks: {0}", [hm(totals.breaks)]) }}</span>
				<span class="text-ink-gray-6">{{ __("Overtime allowed: {0}", [hm(totals.overtime)]) }}</span>
			</div>
			<p v-if="modelValue.shift_type === 'flexible'" class="text-xs text-ink-gray-5">
				{{ __("Flexible shift: the work bar runs from the earliest start to the latest end; the required minutes are set below.") }}
			</p>
			<ul v-if="problems.length" class="flex flex-col gap-0.5 text-sm text-ink-amber-7">
				<li v-for="p in problems" :key="p" class="flex items-center gap-1">
					<span class="lucide-triangle-alert size-4 shrink-0" />{{ p }}
				</li>
			</ul>
		</template>
	</div>
</template>

<script setup lang="ts">
/**
 * The graphical editor of a shift: a day on a horizontal timeline (right to left, 00:00 at the
 * right edge, extending into the next morning for night shifts) with bars for the working hours,
 * breaks and overtime windows. `compact` shows the timeline alone: a row of the work-pattern grid
 * (components/PatternGrid.vue), which then supplies the tool and the snap.
 *
 * v-model takes the shift (or a pattern row's drawing) and gives back the changed fields:
 * {start_time, end_time, segments}. The logic lives in lib/timeline.ts.
 */
import { Button } from "frappe-ui"
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { __ } from "@/lib/i18n"
import { fa, hm } from "@/lib/jalali"
import {
	BAR_COLORS,
	DAY,
	TWO_DAYS,
	barsFromShift,
	cleanSegments,
	clock,
	clockAfter,
	clockToShiftMinute,
	dragTo,
	hourTicks,
	kindMinutes,
	minuteToFraction,
	nudge,
	positionToMinute,
	pressAction,
	removeBar,
	setWork,
	shiftFromBars,
	snap,
	spanOf,
	timelineEnd,
	validateBars,
	workMinutes,
	type Bar,
	type BarKind,
	type Drag,
	type Segment,
	type ShiftShape,
} from "@/lib/timeline"
import TimeInput from "./TimeInput.vue"

type Patch = { start_time: string | null; end_time: string | null; segments: Segment[] }

const props = withDefaults(
	defineProps<{
		modelValue: ShiftShape & { color?: string | null }
		compact?: boolean
		tool?: BarKind | null // compact: the grid's tool (null: the grid's palette is active, the row is not drawn on)
		step?: number // compact: the grid's snap
		ghosts?: Bar[] // faint bars that belong to another day
		invalid?: boolean
		label?: string
	}>(),
	{ compact: false, tool: null, step: 15, ghosts: () => [], invalid: false, label: "" }
)
const emit = defineEmits<{ "update:modelValue": [patch: Patch] }>()
const selected = defineModel<number | null>("selected", { default: null })

const KINDS: BarKind[] = ["work", "break", "overtime"]
const STEPS = [5, 15, 30]

const ownTool = ref<BarKind>("work")
const ownStep = ref(15)
const extend = ref(false)
const frozenTo = ref<number | null>(null) // the view does not change size during a drag
const hoverCursor = ref("")
const track = ref<HTMLElement>()
const width = ref(0)

const tool = computed(() => (props.compact ? props.tool : ownTool.value))
const step = computed(() => (props.compact ? props.step : ownStep.value))
const interactive = computed(() => !props.compact || props.tool !== null)
const bars = computed(() => barsFromShift(props.modelValue))
const work = computed(() => bars.value.find((b) => b.kind === "work") ?? null)
const crossesMidnight = computed(() => bars.value.some((b) => b.end > DAY))
const showMorning = computed(() => extend.value || crossesMidnight.value)

const from = 0
const to = computed(() => (props.compact ? DAY : (frozenTo.value ?? timelineEnd(bars.value, extend.value))))

const ticks = computed(() => hourTicks(from, to.value, labelEvery.value))
const labelledTicks = computed(() => ticks.value.filter((t) => t.label !== null) as { minute: number; label: string }[])
const labelEvery = computed(() => {
	const perHour = width.value / ((to.value - from) / 60)
	return [1, 2, 3, 4, 6].find((n) => perHour * n >= 26) ?? 6
})

const layered = computed(() => {
	const order: Record<BarKind, number> = { work: 0, overtime: 1, break: 2 }
	return bars.value
		.map((bar, index) => ({ bar, index }))
		.filter(({ bar }) => bar.end > from && bar.start < to.value)
		.sort((a, b) => order[a.bar.kind] - order[b.bar.kind])
})
const visibleGhosts = computed(() => props.ghosts.filter((g) => g.end > from && g.start < to.value))

const totals = computed(() => ({
	work: workMinutes(bars.value),
	breaks: kindMinutes(bars.value, "break"),
	overtime: kindMinutes(bars.value, "overtime"),
}))
const problems = computed(() => validateBars(bars.value, props.modelValue.shift_type))
const cursor = computed(() => {
	if (!interactive.value) return "default"
	return hoverCursor.value || (tool.value ? "crosshair" : "default")
})

function kindLabel(kind: BarKind): string {
	return { work: __("Work"), break: __("Break (unpaid)"), overtime: __("Overtime allowed") }[kind]
}

const workColor = computed(() => props.modelValue.color || BAR_COLORS.work)

function swatch(kind: BarKind): Record<string, string> {
	if (kind === "work") return { background: workColor.value }
	const c = BAR_COLORS[kind]
	return { background: `repeating-linear-gradient(135deg, ${c} 0 4px, ${c}88 4px 8px)` }
}

const pct = (minute: number) => `${minuteToFraction(minute, from, to.value) * 100}%`
const pctWidth = (a: number, b: number) => `${minuteToFraction(b, from, to.value) * 100 - minuteToFraction(a, from, to.value) * 100}%`
const pxWidth = (b: Bar) => ((Math.min(b.end, to.value) - Math.max(b.start, from)) / (to.value - from)) * width.value

function barStyle(b: Bar): Record<string, string> {
	const start = Math.max(b.start, from)
	const end = Math.min(b.end, to.value)
	const style: Record<string, string> = { right: pct(start), width: pctWidth(start, end), top: "0", bottom: "0" }
	if (b.kind === "work") {
		style.background = workColor.value
		style.borderRadius = "4px"
	} else if (b.kind === "break") {
		Object.assign(style, swatch("break"), { top: "22%", bottom: "22%", borderRadius: "3px" })
	} else {
		Object.assign(style, swatch("overtime"), { borderRadius: "4px", boxShadow: `inset 0 0 0 1px ${BAR_COLORS.overtime}` })
	}
	return style
}

// pointer --------------------------------------------------------------------------------------------

let drag: Drag | null = null

function minuteAt(e: PointerEvent): number {
	const rect = track.value!.getBoundingClientRect()
	return positionToMinute(rect.right - e.clientX, rect.width, from, to.value)
}

function tolerance(): number {
	return (10 / Math.max(1, width.value)) * (to.value - from)
}

function options() {
	return { step: step.value, from, to: to.value, shiftType: props.modelValue.shift_type }
}

let committed: Bar[] | null = null // the bars last sent (the parent may re-render later)

function commit(next: Bar[]) {
	committed = next
	emit("update:modelValue", shiftFromBars(next))
}

function onPointerDown(e: PointerEvent) {
	if (e.button !== 0 || !interactive.value || !track.value) return
	drag = pressAction(bars.value, minuteAt(e), tolerance(), tool.value, props.modelValue.shift_type)
	if (!drag) return
	selected.value = drag.type === "draw" ? null : drag.index
	frozenTo.value = to.value
	committed = null
	track.value.setPointerCapture(e.pointerId)
	track.value.focus({ preventScroll: true })
	e.preventDefault()
	e.stopPropagation()
}

function onPointerMove(e: PointerEvent) {
	if (!interactive.value || !track.value) return
	if (!drag) {
		const next = pressAction(bars.value, minuteAt(e), tolerance(), tool.value, props.modelValue.shift_type)
		hoverCursor.value = next?.type === "move" ? "grab" : next?.type === "resize" ? "ew-resize" : ""
		return
	}
	commit(dragTo(drag, minuteAt(e), options()))
}

function onPointerUp() {
	if (!drag) return
	const now = committed ?? bars.value
	if (drag.type === "draw" && now !== drag.original) {
		selected.value = drag.kind === "work" ? now.findIndex((b) => b.kind === "work") : now.length - 1
	}
	drag = null
	frozenTo.value = null
}

function onKey(e: KeyboardEvent) {
	if (selected.value === null || !interactive.value) return
	if (e.key === "Delete" || e.key === "Backspace") {
		removeSelected()
		e.preventDefault()
	} else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
		// time runs right to left
		commit(nudge(bars.value, selected.value, (e.key === "ArrowLeft" ? 1 : -1) * step.value, options()))
		e.preventDefault()
	}
}

function remove(index: number) {
	commit(removeBar(bars.value, index))
	selected.value = null
}

function removeSelected() {
	if (selected.value !== null) remove(selected.value)
}

// exact times ------------------------------------------------------------------------------------------

function setTime(index: number, edge: "start" | "end", value: string | null) {
	const bar = bars.value[index]
	if (!value || !bar) return
	if (bar.kind === "work") {
		const span = edge === "start" ? spanOf(value, clock(bar.end)) : spanOf(clock(bar.start), value)
		if (span) commit(bars.value.map((b, i) => (i === index ? span : b)))
		return
	}
	let { start, end } = bar
	if (edge === "start") {
		const minute = clockToShiftMinute(value, work.value)
		if (minute === null) return
		if (!(minute < end && end - minute <= DAY)) end = minute + (end - start)
		start = minute
	} else {
		const minute = clockAfter(value, start)
		if (minute === null) return
		end = minute
	}
	if (end > TWO_DAYS) return
	commit(bars.value.map((b, i) => (i === index ? { ...b, start, end } : b)))
}

function append(bar: Bar) {
	const next = [...bars.value, bar]
	commit(next)
	selected.value = next.length - 1
}

function addWork() {
	commit(setWork(bars.value, 540, 1020, props.modelValue.shift_type))
	selected.value = 0
}

function addBreak() {
	const w = work.value
	if (!w) return
	const middle = snap((w.start + w.end) / 2 - 15, 15)
	append({ kind: "break", start: Math.max(w.start, middle), end: Math.min(w.end, middle + 30) })
}

function addOvertime() {
	const w = work.value ?? { start: 540, end: 1020 }
	const windows = bars.value.filter((b) => b.kind === "overtime")
	const after = { kind: "overtime" as const, start: w.end, end: Math.min(TWO_DAYS, w.end + 120) }
	const before = { kind: "overtime" as const, start: Math.max(0, w.start - 60), end: w.start }
	const free = (b: Bar) => b.end > b.start && !windows.some((x) => x.start < b.end && b.start < x.end)
	append(free(after) ? after : free(before) ? before : after)
}

// size -------------------------------------------------------------------------------------------------

let observer: ResizeObserver | undefined
onMounted(() => {
	if (!track.value) return
	width.value = track.value.clientWidth
	observer = new ResizeObserver(() => (width.value = track.value?.clientWidth ?? 0))
	observer.observe(track.value)
})
onBeforeUnmount(() => observer?.disconnect())

/** Called by the form before saving: the server's rules, and the fields to send. */
function beforeSave(): Patch {
	if (problems.value.length) throw new Error(problems.value[0])
	const fields = shiftFromBars(bars.value)
	return { ...fields, segments: cleanSegments(fields.segments) }
}

defineExpose({ beforeSave })
</script>
