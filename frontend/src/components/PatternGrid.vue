<template>
	<div class="flex min-w-0 flex-col gap-3">
		<!-- brushes: drawing tools, then the existing shifts and the day-off eraser -->
		<div class="flex flex-wrap items-center gap-2">
			<div class="flex flex-wrap gap-0.5 rounded-4 bg-surface-gray-2 p-0.5" role="radiogroup" :aria-label="__('Drawing tool')">
				<button
					v-for="kind in KINDS"
					:key="kind"
					type="button"
					role="radio"
					:aria-checked="isBrush({ type: 'draw', kind })"
					class="flex items-center gap-1.5 rounded-3 px-2 py-1 text-sm"
					:class="isBrush({ type: 'draw', kind }) ? 'bg-surface-base font-medium text-ink-gray-9 shadow-sm' : 'text-ink-gray-6'"
					@click="brush = { type: 'draw', kind }"
				>
					<span class="inline-block size-3 shrink-0 rounded-sm" :style="swatch(kind)" />
					{{ kindLabel(kind) }}
				</button>
			</div>
			<label class="flex items-center gap-1 text-xs text-ink-gray-5">
				{{ __("Snap") }}
				<select
					v-model.number="step"
					class="hz-num h-7 rounded-3 border-none bg-surface-gray-2 py-0 pe-7 ps-2 text-sm text-ink-gray-8 focus:ring-0"
				>
					<option v-for="s in STEPS" :key="s" :value="s">{{ __("{0} min", [fa(s)]) }}</option>
				</select>
			</label>
			<Button size="sm" variant="ghost" icon-left="lucide-trash-2" :disabled="!selection" @click="deleteSelected">{{
				__("Delete")
			}}</Button>
			<span class="flex-1" />
			<Button size="sm" variant="ghost" :icon-left="view === 'grid' ? 'lucide-list' : 'lucide-grid-3x3'" @click="view = view === 'grid' ? 'list' : 'grid'">{{
				view === "grid" ? __("List view") : __("Grid view")
			}}</Button>
		</div>
		<div class="flex flex-wrap items-center gap-1.5" role="radiogroup" :aria-label="__('Apply a shift')">
			<span class="text-xs text-ink-gray-5">{{ __("Apply a shift:") }}</span>
			<button
				v-for="s in shifts"
				:key="s.id"
				type="button"
				role="radio"
				:aria-checked="isBrush({ type: 'apply', shift_id: s.id })"
				class="flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm"
				:class="
					isBrush({ type: 'apply', shift_id: s.id })
						? 'border-ink-gray-8 bg-surface-gray-3 font-medium text-ink-gray-9'
						: 'border-outline-gray-2 text-ink-gray-7 hover:bg-surface-gray-2'
				"
				@click="brush = { type: 'apply', shift_id: s.id }"
			>
				<span class="inline-block size-2.5 shrink-0 rounded-full" :style="{ background: s.color || BAR_COLORS.work }" />
				<span class="hz-num">{{ s.name }}</span>
			</button>
			<button
				type="button"
				role="radio"
				:aria-checked="isBrush({ type: 'apply', shift_id: null })"
				class="flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm"
				:class="
					isBrush({ type: 'apply', shift_id: null })
						? 'border-ink-gray-8 bg-surface-gray-3 font-medium text-ink-gray-9'
						: 'border-outline-gray-2 text-ink-gray-7 hover:bg-surface-gray-2'
				"
				@click="brush = { type: 'apply', shift_id: null }"
			>
				<span class="lucide-eraser size-3.5" />{{ __("Day off") }}
			</button>
		</div>
		<p class="text-xs text-ink-gray-5">
			{{
				brush.type === "apply"
					? __("Click a day to give it this shift, or drag down across several days.")
					: __(
							"Draw on a day with the chosen tool; drag a bar to move it or its edges to resize it. A drawing that matches no shift becomes a new shift when you save."
						)
			}}
		</p>

		<template v-if="rotating">
			<div>
				<Button size="sm" icon-left="lucide-wand-sparkles" @click="showRotation = !showRotation">{{ __("Quick rotation") }}</Button>
			</div>
			<RotationBuilder v-if="showRotation" @fill="fill" />
		</template>

		<!-- the grid: a row per day, the hours of the day from right (00) to left (24) -->
		<div v-if="view === 'grid'" class="overflow-x-auto rounded-4 border border-outline-gray-2">
			<div class="min-w-[44rem]">
				<div class="flex border-b border-outline-gray-2 bg-surface-gray-1">
					<div class="sticky right-0 z-20 w-28 shrink-0 bg-surface-gray-1" />
					<div ref="header" class="relative h-6 flex-1 text-[11px] text-ink-gray-5" aria-hidden="true">
						<span
							v-for="t in headerTicks"
							:key="t.minute"
							class="hz-num absolute top-1 translate-x-1/2"
							:style="{ right: `${(t.minute / DAY) * 100}%` }"
							>{{ fa(t.label) }}</span
						>
					</div>
					<div class="w-40 shrink-0" />
				</div>
				<div
					:style="{ touchAction: brush.type === 'apply' ? 'pan-x' : 'auto' }"
					@pointerdown="onPaintDown"
					@pointermove="onPaintMove"
					@pointerup="painting = false"
					@pointercancel="painting = false"
				>
					<div
						v-for="(row, i) in rows"
						:key="i"
						:data-row="i"
						class="flex border-b border-outline-gray-1 last:border-b-0"
						:class="brush.type === 'apply' ? 'cursor-pointer hover:bg-surface-gray-1' : ''"
					>
						<div class="sticky right-0 z-20 flex w-28 shrink-0 flex-col justify-center bg-surface-base px-2 py-1">
							<span class="text-sm">{{ rowLabel(i) }}</span>
							<span v-if="!rotating && i === restDay" class="text-[10px] text-ink-gray-5">{{ __("Weekly rest day") }}</span>
						</div>
						<div class="h-11 flex-1 py-1.5">
							<ShiftTimeline
								compact
								:model-value="drawing(i)"
								:tool="brush.type === 'draw' ? brush.kind : null"
								:step="step"
								:ghosts="ghosts(i)"
								:invalid="problemsOf(i).length > 0"
								:label="rowLabel(i)"
								:selected="selection?.row === i ? selection.bar : null"
								@update:selected="(bar) => (selection = bar === null ? null : { row: i, bar })"
								@update:model-value="(patch) => draw(i, patch)"
							/>
						</div>
						<div class="flex w-40 shrink-0 items-center gap-1 px-2">
							<div class="min-w-0 flex-1 leading-tight">
								<p class="hz-num truncate text-xs" :class="row.draft ? 'text-ink-blue-6' : rowShape(i) ? 'text-ink-gray-8' : 'text-ink-gray-5'">
									{{ rowName(i) }}
								</p>
								<p v-if="rowShape(i)" class="hz-num text-[11px] text-ink-gray-5">{{ hm(rowMinutes(i)) }}</p>
							</div>
							<Button
								size="sm"
								variant="ghost"
								icon="lucide-pencil"
								:aria-label="__('Edit the times')"
								@click="editing = editing === i ? null : i"
							/>
							<Button
								v-if="rotating"
								size="sm"
								variant="ghost"
								icon="lucide-x"
								:aria-label="__('Remove this day')"
								@click="removeDay(i)"
							/>
						</div>
					</div>
					<p v-if="!rows.length" class="px-3 py-6 text-center text-sm text-ink-gray-5">
						{{ __("No days yet: add days or use the quick rotation.") }}
					</p>
				</div>
			</div>
		</div>

		<!-- list view: one picker per day -->
		<div v-else class="flex flex-col gap-1">
			<div v-for="(row, i) in rows" :key="i" class="flex items-center gap-2 rounded-4 bg-surface-gray-1 p-2">
				<span class="w-24 shrink-0 text-sm">{{ rowLabel(i) }}</span>
				<Combobox
					class="min-w-0 flex-1"
					:model-value="row.draft ? null : (row.shift_id ?? DAY_OFF)"
					:options="listOptions"
					:placeholder="rowName(i)"
					@update:model-value="(v) => apply(i, typeof v === 'number' && v !== DAY_OFF ? v : null)"
				/>
				<Button v-if="rotating" :aria-label="__('Remove this day')" icon="lucide-x" @click="removeDay(i)" />
			</div>
		</div>

		<div class="flex flex-wrap items-center gap-2">
			<Button v-if="rotating" size="sm" icon-left="lucide-plus" @click="addDay">{{ __("Add a day") }}</Button>
			<span class="hz-num text-sm text-ink-gray-6">
				{{
					rotating
						? __("Scheduled work in a cycle of {0} days: {1}", [fa(rows.length), hm(totalMinutes)])
						: __("Scheduled work in the week: {0}", [hm(totalMinutes)])
				}}
			</span>
		</div>
		<p v-if="hint" class="text-sm text-ink-amber-7">{{ hint }}</p>
		<ul v-if="allProblems.length" class="flex flex-col gap-0.5 text-sm text-ink-red-6">
			<li v-for="p in allProblems" :key="p" class="flex items-center gap-1">
				<span class="lucide-triangle-alert size-4 shrink-0" />{{ p }}
			</li>
		</ul>

		<!-- exact editing of one day -->
		<div v-if="editing !== null && rows[editing]" class="flex flex-col gap-2 rounded-4 border border-outline-gray-2 p-3">
			<div class="flex items-center gap-2">
				<p class="flex-1 text-sm font-medium">{{ __("The shift of {0}", [rowLabel(editing)]) }}</p>
				<Button size="sm" variant="ghost" icon="lucide-x" :aria-label="__('Close')" @click="editing = null" />
			</div>
			<ShiftTimeline :model-value="drawing(editing)" @update:model-value="(patch) => draw(editing!, patch)" />
		</div>
	</div>
</template>

<script setup lang="ts">
/**
 * The graphical editor of a work pattern: a row per weekday (Saturday first) or per day of a
 * rotating cycle, the hours of the day as columns. A row shows its shift's bars (a night shift's
 * morning continues faintly on the next row). Rows get a shift from the palette, or are drawn
 * on directly; a drawing that matches no existing shift becomes a new shift when the pattern
 * is saved (`beforeSave`, called by components/ResourceForm.vue), named after its times.
 */
import { Button, Combobox } from "frappe-ui"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa, hm, WEEKDAYS } from "@/lib/jalali"
import { invalidateRef, refRows } from "@/lib/refs"
import {
	BAR_COLORS,
	DAY,
	autoName,
	barsFromShift,
	cleanSegments,
	findIdentical,
	hourTicks,
	removeBar,
	shapeKey,
	shiftFromBars,
	spill,
	validateBars,
	workMinutes,
	type Bar,
	type BarKind,
	type Segment,
	type ShiftShape,
} from "@/lib/timeline"
import RotationBuilder from "./RotationBuilder.vue"
import ShiftTimeline from "./ShiftTimeline.vue"

interface ShiftRow extends ShiftShape {
	id: number
	name: string
	shift_type: string
	color?: string | null
	segments: Segment[]
	[key: string]: unknown
}

interface PatternDay {
	weekday: number | null
	cycle_day: number | null
	shift_id: number | null
}

/** A day of the pattern: an existing shift, or a drawing that becomes a shift on save. */
interface Row {
	shift_id: number | null
	draft: ShiftShape | null
	base: number | null // the shift the drawing started from (its other settings are copied)
}

type Brush = { type: "draw"; kind: BarKind } | { type: "apply"; shift_id: number | null }
type Patch = { start_time: string | null; end_time: string | null; segments: Segment[] }

const props = defineProps<{ modelValue: Record<string, unknown> }>()

const KINDS: BarKind[] = ["work", "break", "overtime"]
const STEPS = [5, 15, 30]
const DAY_OFF = 0 // the "day off" option of the list view
const EMPTY: ShiftShape = { shift_type: "fixed", start_time: null, end_time: null, segments: [] }

const rows = ref<Row[]>([])
const brush = ref<Brush>({ type: "draw", kind: "work" })
const step = ref(15)
const view = ref<"grid" | "list">("grid")
const selection = ref<{ row: number; bar: number } | null>(null)
const editing = ref<number | null>(null)
const showRotation = ref(false)
const hint = ref("")
const header = ref<HTMLElement>()
const headerWidth = ref(0)

const shifts = computed(() => refRows("shifts") as ShiftRow[])
const rotating = computed(() => props.modelValue.pattern_type === "rotating")
const restDay = computed(() => props.modelValue.weekly_rest_day as number | null)

// rows <-> the pattern's days ------------------------------------------------------------------------

function load() {
	const days = ((props.modelValue.days as PatternDay[] | null) ?? []).slice()
	const row = (shift_id: number | null | undefined): Row => ({ shift_id: shift_id ?? null, draft: null, base: null })
	if (rotating.value) {
		rows.value = days.sort((a, b) => (a.cycle_day ?? 0) - (b.cycle_day ?? 0)).map((d) => row(d.shift_id))
	} else {
		rows.value = WEEKDAYS.map((_, w) => row(days.find((d) => d.weekday === w)?.shift_id))
	}
	selection.value = null
	editing.value = null
	hint.value = ""
}

// a new record (or another one) brings a new `days` array
watch(() => props.modelValue.days, load, { immediate: true })

watch(rotating, (now) => {
	// weekly -> rotating keeps the seven days as days 1..7 of the cycle; back again keeps the first seven
	if (!now) {
		const first = rows.value.slice(0, 7)
		while (first.length < 7) first.push({ shift_id: null, draft: null, base: null })
		rows.value = first
	}
	selection.value = null
	editing.value = null
})

function rowLabel(i: number): string {
	return rotating.value ? __("Day {0}", [fa(i + 1)]) : WEEKDAYS[i]
}

function shiftById(id: number | null): ShiftRow | undefined {
	return id === null ? undefined : shifts.value.find((s) => s.id === id)
}

function rowShape(i: number): ShiftShape | null {
	const row = rows.value[i]
	if (!row) return null
	return row.draft ?? shiftById(row.shift_id) ?? null
}

/** What a row's timeline shows: the shape and the colour of its shift. */
function drawing(i: number): ShiftShape & { color?: string | null } {
	const row = rows.value[i]
	const shape = rowShape(i)
	const color = shiftById(row?.shift_id ?? null)?.color ?? shiftById(row?.base ?? null)?.color ?? null
	return { ...(shape ?? EMPTY), color }
}

function rowName(i: number): string {
	const row = rows.value[i]
	if (row?.draft) return __("New: {0}", [autoName(row.draft, [])])
	return shiftById(row?.shift_id ?? null)?.name ?? (row?.shift_id ? "…" : __("Day off"))
}

const rowMinutes = (i: number) => workMinutes(barsFromShift(rowShape(i)))
const totalMinutes = computed(() => rows.value.reduce((sum, _, i) => sum + rowMinutes(i), 0))

/** The morning of the day before's night shift, shown faintly at the start of the row. */
function ghosts(i: number): Bar[] {
	const n = rows.value.length
	if (!n) return []
	return spill(barsFromShift(rowShape((i - 1 + n) % n)))
}

function problemsOf(i: number): string[] {
	const draft = rows.value[i]?.draft
	return draft ? validateBars(barsFromShift(draft), draft.shift_type) : []
}

const allProblems = computed(() =>
	rows.value.flatMap((_, i) => problemsOf(i).map((p) => __("{0}: {1}", [rowLabel(i), p])))
)

// editing --------------------------------------------------------------------------------------------

function isBrush(b: Brush): boolean {
	const a = brush.value
	return a.type === b.type && (a.type === "draw" ? a.kind === (b as typeof a).kind : a.shift_id === (b as typeof a).shift_id)
}

function kindLabel(kind: BarKind): string {
	return { work: __("Work"), break: __("Break (unpaid)"), overtime: __("Overtime allowed") }[kind]
}

function swatch(kind: BarKind): Record<string, string> {
	if (kind === "work") return { background: BAR_COLORS.work }
	const c = BAR_COLORS[kind]
	return { background: `repeating-linear-gradient(135deg, ${c} 0 4px, ${c}88 4px 8px)` }
}

function apply(i: number, shiftId: number | null) {
	rows.value[i] = { shift_id: shiftId, draft: null, base: null }
	if (selection.value?.row === i) selection.value = null
}

/** A row was drawn on: reuse an identical shift, or keep the drawing to create on save. */
function draw(i: number, patch: Patch) {
	const row = rows.value[i]
	if (!row) return
	const current = rowShape(i)
	hint.value = ""
	if (!patch.start_time) {
		if (current) apply(i, null) // the working hours were removed: a day off
		else if (patch.segments.length) hint.value = __("Draw the working hours first")
		return
	}
	const shape: ShiftShape = { shift_type: current?.shift_type ?? "fixed", ...patch }
	const prefer = row.shift_id ?? row.base
	const match = findIdentical(shifts.value, shape, prefer)
	rows.value[i] = match
		? { shift_id: match.id, draft: null, base: null }
		: { shift_id: null, draft: shape, base: prefer }
}

function deleteSelected() {
	const s = selection.value
	if (!s) return
	const bars = barsFromShift(rowShape(s.row))
	draw(s.row, shiftFromBars(removeBar(bars, s.bar)))
	selection.value = null
}

function fill(days: { shift_id: number | null }[]) {
	rows.value = days.map((d) => ({ shift_id: d.shift_id, draft: null, base: null }))
	selection.value = null
	editing.value = null
}

function addDay() {
	rows.value.push({ shift_id: null, draft: null, base: null })
}

function removeDay(i: number) {
	rows.value.splice(i, 1)
	selection.value = null
	editing.value = null
}

const listOptions = computed(() => [
	{ value: DAY_OFF, label: __("Day off") },
	...shifts.value.map((s) => ({ value: s.id, label: s.name })),
])

// painting rows with a shift from the palette (click, or drag down across rows) ------------------------

const painting = ref(false)

function rowAt(e: PointerEvent): number | null {
	const el = document.elementFromPoint(e.clientX, e.clientY)?.closest<HTMLElement>("[data-row]")
	return el ? Number(el.dataset.row) : null
}

function onPaintDown(e: PointerEvent) {
	const b = brush.value
	if (b.type !== "apply" || e.button !== 0 || (e.target as Element).closest("button")) return
	const i = rowAt(e)
	if (i === null) return
	painting.value = true
	apply(i, b.shift_id)
	;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
	e.preventDefault()
}

function onPaintMove(e: PointerEvent) {
	const b = brush.value
	if (!painting.value || b.type !== "apply") return
	const i = rowAt(e)
	if (i !== null && rows.value[i]?.shift_id !== b.shift_id) apply(i, b.shift_id)
}

// header ---------------------------------------------------------------------------------------------

const headerTicks = computed(() => {
	const perHour = headerWidth.value / 24
	const every = [1, 2, 3, 4, 6].find((n) => perHour * n >= 24) ?? 6
	return hourTicks(0, DAY, every).filter((t) => t.label !== null) as { minute: number; label: string }[]
})

let observer: ResizeObserver | undefined
onMounted(() => {
	observer = new ResizeObserver(() => (headerWidth.value = header.value?.clientWidth ?? 0))
	if (header.value) observer.observe(header.value)
})
watch(header, (el) => el && observer?.observe(el))
onBeforeUnmount(() => observer?.disconnect())

// saving ---------------------------------------------------------------------------------------------

/** Called by the form before saving: creates the drawn shifts that do not exist yet, then gives the days. */
async function beforeSave(): Promise<{ days: PatternDay[] }> {
	if (allProblems.value.length) throw new Error(allProblems.value[0])
	if (rotating.value && !rows.value.length) throw new Error(__("Add the days of the cycle"))
	if (rotating.value && !props.modelValue.cycle_start_date)
		throw new Error(__("A rotating pattern needs the first day of the cycle"))
	if (rows.value.some((r) => r.draft)) {
		const existing = await api.get<ShiftRow[]>("/admin/shifts")
		const made = new Map<string, number>()
		for (const row of rows.value) {
			if (!row.draft) continue
			const key = shapeKey(row.draft)
			let id = findIdentical(existing, row.draft, row.base)?.id ?? made.get(key)
			if (id === undefined) {
				const base = existing.find((s) => s.id === row.base)
				const created = await api.post<ShiftRow>("/admin/shifts", {
					name: autoName(row.draft, existing.map((s) => s.name)),
					shift_type: row.draft.shift_type ?? "fixed",
					start_time: row.draft.start_time,
					end_time: row.draft.end_time,
					segments: cleanSegments(row.draft.segments),
					color: base?.color ?? null,
					latest_start_time: base?.latest_start_time ?? null,
					required_minutes: base?.required_minutes ?? null,
					break_minutes: base?.break_minutes ?? 0,
					grace_late_minutes: base?.grace_late_minutes ?? 0,
					grace_early_minutes: base?.grace_early_minutes ?? 0,
					overtime_after_minutes: base?.overtime_after_minutes ?? 0,
				})
				existing.push(created)
				id = created.id
			}
			made.set(key, id)
			// the row now points at a saved shift (a retry does not create it again)
			Object.assign(row, { shift_id: id, draft: null, base: null })
		}
		invalidateRef("shifts")
	}
	return {
		days: rows.value.map((r, i) =>
			rotating.value
				? { weekday: null, cycle_day: i + 1, shift_id: r.shift_id }
				: { weekday: i, cycle_day: null, shift_id: r.shift_id }
		),
	}
}

defineExpose({ beforeSave })
</script>
