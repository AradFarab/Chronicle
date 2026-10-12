<template>
	<div class="flex min-w-0 flex-col gap-2">
		<!-- toolbar: the page's buttons, then the selection and the filter status -->
		<div v-if="$slots.toolbar || filtering || (selectable && selected.length)" class="flex flex-wrap items-center gap-2">
			<slot name="toolbar" />
			<span class="flex-1" />
			<span v-if="selectable && selected.length" class="hz-num flex items-center gap-1 text-sm text-ink-gray-6">
				{{ __("{0} selected", [fa(selected.length)]) }}
				<Button size="sm" variant="ghost" @click="selected = []">{{ __("Clear selection") }}</Button>
			</span>
			<template v-if="filtering">
				<span class="hz-num text-sm text-ink-gray-5">{{ __("{0} of {1}", [fa(shown.length), fa(rows.length)]) }}</span>
				<Button v-if="filterCount" size="sm" icon-left="lucide-funnel-x" @click="clearFilters">{{
					__("Clear all filters")
				}}</Button>
			</template>
		</div>

		<!-- phone, card layout: the column menus open from these chips -->
		<div v-if="$slots.card && menuColumns.length && rows.length" class="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 sm:hidden">
			<label
				v-if="selectable"
				class="flex shrink-0 items-center gap-1.5 rounded-full border border-outline-gray-2 px-3 py-1 text-xs"
			>
				<input
					type="checkbox"
					:checked="allSelected"
					:indeterminate="someSelected"
					:disabled="!shown.length"
					@change="toggleAll"
				/>{{ __("All") }}
			</label>
			<button
				v-for="c in menuColumns"
				:key="c.key"
				type="button"
				class="flex shrink-0 items-center gap-1 rounded-full border px-3 py-1 text-xs"
				:class="
					isFiltered(c.key) || state.sort?.key === c.key
						? 'border-outline-gray-5 bg-surface-gray-3 font-medium text-ink-gray-8'
						: 'border-outline-gray-2 text-ink-gray-6'
				"
				@click="openMenu(c, $event)"
			>
				{{ c.label }}
				<span v-if="state.sort?.key === c.key" :class="sortIcon" class="size-3.5" />
				<span v-if="isFiltered(c.key)" class="lucide-funnel size-3.5" />
				<span v-else class="lucide-chevron-down size-3.5 opacity-60" />
			</button>
		</div>

		<!-- the table -->
		<div
			class="overflow-auto rounded-6 border border-outline-gray-1 bg-surface-base"
			:class="[$slots.card ? 'hidden sm:block' : '', scrollClass ?? 'max-h-[calc(100dvh-11rem)]']"
		>
			<table class="w-full text-sm">
				<thead class="text-ink-gray-5">
					<tr>
						<th v-if="selectable" class="sticky top-0 z-10 w-10 bg-surface-gray-1 px-3 py-2 text-start">
							<input
								type="checkbox"
								:aria-label="__('Select all')"
								:checked="allSelected"
								:indeterminate="someSelected"
								:disabled="!shown.length"
								@change="toggleAll"
							/>
						</th>
						<th
							v-for="c in columns"
							:key="c.key"
							class="sticky top-0 z-10 whitespace-nowrap bg-surface-gray-1 px-1 py-1 text-start font-medium"
							:aria-sort="ariaSort(c.key)"
						>
							<button
								v-if="hasMenu(c)"
								type="button"
								class="flex w-full items-center gap-1 rounded-3 px-2 py-1 text-start hover:bg-surface-gray-3"
								:class="[
									menuOpen && activeKey === c.key ? 'bg-surface-gray-3 text-ink-gray-8' : '',
									isFiltered(c.key) || state.sort?.key === c.key ? 'text-ink-gray-8' : '',
								]"
								:aria-haspopup="true"
								@click="openMenu(c, $event)"
							>
								<span class="flex-1">{{ c.label }}</span>
								<span v-if="state.sort?.key === c.key" :class="sortIcon" class="size-3.5 shrink-0" />
								<span
									v-if="isFiltered(c.key)"
									class="lucide-funnel size-3.5 shrink-0"
									:title="__('Filtered')"
								/>
								<span v-else class="lucide-chevron-down size-3.5 shrink-0 opacity-50" />
							</button>
							<span v-else class="block px-2 py-1">{{ c.label }}</span>
						</th>
					</tr>
				</thead>
				<tbody>
					<tr
						v-for="row in shown"
						:key="keyOf(row)"
						class="border-t border-outline-gray-1"
						:class="[
							onRowClick ? 'cursor-pointer hover:bg-surface-gray-1' : '',
							selectable && isSelected(row) ? 'bg-surface-gray-1' : '',
							rowClass?.(row),
						]"
						@click="onRowClick?.(row)"
					>
						<td v-if="selectable" class="w-10 px-3 py-2" @click.stop>
							<input
								type="checkbox"
								:aria-label="__('Select')"
								:checked="isSelected(row)"
								@change="toggleRow(row)"
							/>
						</td>
						<td
							v-for="c in columns"
							:key="c.key"
							class="px-3 py-2"
							:class="[c.type === 'number' || c.type === 'date' ? 'hz-num whitespace-nowrap' : '', c.class]"
						>
							<slot :name="`cell-${c.key}`" :row="row" :value="rawValue(c, row)" :text="cellText(c, row)">{{
								cellText(c, row)
							}}</slot>
						</td>
					</tr>
					<tr v-if="!shown.length">
						<td :colspan="columns.length + (selectable ? 1 : 0)" class="px-3 py-6 text-center text-ink-gray-5">
							<template v-if="loading">{{ __("Loading...") }}</template>
							<template v-else-if="rows.length">{{ __("No row matches the filters") }}</template>
							<slot v-else name="empty">{{ __("Nothing here yet") }}</slot>
						</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- phone, card layout -->
		<div v-if="$slots.card" class="flex flex-col gap-2 sm:hidden">
			<div v-for="row in shown" :key="keyOf(row)" class="flex items-start gap-2">
				<input
					v-if="selectable"
					type="checkbox"
					class="mt-4"
					:aria-label="__('Select')"
					:checked="isSelected(row)"
					@change="toggleRow(row)"
				/>
				<div class="min-w-0 flex-1"><slot name="card" :row="row" /></div>
			</div>
			<p v-if="!shown.length" class="hz-card text-center text-sm text-ink-gray-5">
				<template v-if="loading">{{ __("Loading...") }}</template>
				<template v-else-if="rows.length">{{ __("No row matches the filters") }}</template>
				<slot v-else name="empty">{{ __("Nothing here yet") }}</slot>
			</p>
		</div>

		<!-- the column menu (one for the whole table, placed under the header that opened it) -->
		<Popover v-model:open="menuOpen" trigger="manual" :reference="anchor" align="start" @update:open="menuToggled">
			<template #trigger><span class="hidden" /></template>
			<div v-if="menuColumn" class="flex w-72 max-w-[calc(100vw-1.5rem)] flex-col gap-2 p-2 text-sm text-ink-gray-8">
				<p class="px-1 pt-1 font-medium">{{ menuColumn.label }}</p>
				<div v-if="menuColumn.sortable !== false" class="flex flex-col">
					<button
						v-for="dir in ['asc', 'desc'] as const"
						:key="dir"
						type="button"
						class="flex items-center gap-2 rounded-3 px-2 py-1.5 text-start hover:bg-surface-gray-2"
						:class="isSorted(menuColumn.key, dir) ? 'bg-surface-gray-2 font-medium' : ''"
						@click="sortBy(menuColumn.key, dir)"
					>
						<span :class="sortIconFor(menuColumn, dir)" class="size-4 shrink-0 text-ink-gray-6" />
						<span class="flex-1">{{ sortLabel(menuColumn, dir) }}</span>
						<span v-if="isSorted(menuColumn.key, dir)" class="lucide-check size-4 shrink-0" />
					</button>
				</div>
				<template v-if="menuColumn.filterable !== false">
					<div class="border-t border-outline-gray-1" />
					<TextInput
						size="sm"
						:model-value="menuFilter.contains ?? ''"
						:placeholder="__('Contains…')"
						:aria-label="__('Contains…')"
						@update:model-value="(v: string) => setContains(v)"
					/>
					<div class="flex flex-col gap-1 rounded-4 border border-outline-gray-1 p-1">
						<TextInput v-model="valueSearch" size="sm" :placeholder="__('Search the values')" />
						<div class="flex items-center gap-3 px-1 text-xs">
							<button type="button" class="text-ink-blue-link" @click="checkAll">{{ __("Select all") }}</button>
							<button type="button" class="text-ink-blue-link" @click="uncheckAll">{{ __("Clear") }}</button>
							<span class="hz-num flex-1 text-end text-ink-gray-5">{{ fa(matchingValues.length) }}</span>
						</div>
						<div class="max-h-52 overflow-y-auto">
							<label
								v-for="v in matchingValues.slice(0, VALUE_LIMIT)"
								:key="v.text"
								class="flex cursor-pointer items-center gap-2 rounded-2 px-1 py-1 hover:bg-surface-gray-2"
							>
								<input type="checkbox" :checked="isChecked(v.text)" @change="toggleValue(v.text)" />
								<span class="min-w-0 flex-1 truncate" :class="v.text ? '' : 'text-ink-gray-5'">{{
									v.text || __("(Empty)")
								}}</span>
								<span class="hz-num text-xs text-ink-gray-4">{{ fa(v.count) }}</span>
							</label>
							<p v-if="!matchingValues.length" class="px-1 py-2 text-center text-xs text-ink-gray-5">
								{{ __("No value") }}
							</p>
							<p v-else-if="matchingValues.length > VALUE_LIMIT" class="px-1 py-1 text-xs text-ink-gray-5">
								{{ __("{0} more; search to find them", [fa(matchingValues.length - VALUE_LIMIT)]) }}
							</p>
						</div>
					</div>
				</template>
				<div class="flex gap-2">
					<Button
						v-if="menuColumn.filterable !== false"
						class="flex-1"
						icon-left="lucide-funnel-x"
						:disabled="!isFiltered(menuColumn.key)"
						@click="clearFilter(menuColumn.key)"
						>{{ __("Clear filter") }}</Button
					>
					<Button class="flex-1" variant="solid" @click="menuOpen = false">{{ __("Done") }}</Button>
				</div>
			</div>
		</Popover>
	</div>
</template>

<script setup lang="ts" generic="Row extends Record<string, any>">
import { Button, Popover, TextInput } from "frappe-ui"
import { computed, reactive, ref, watch } from "vue"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import {
	applyTable,
	cellText,
	distinctValues,
	filterActive,
	loadState,
	normalize,
	rawValue,
	saveState,
	type ColumnFilter,
	type SortDir,
	type TableColumn,
	type TableState,
} from "@/lib/table"

type Key = string | number

const props = defineProps<{
	columns: TableColumn<Row>[]
	rows: Row[]
	/** The field holding each row's unique key (default "id"), or a function returning it. */
	rowKey?: string | ((row: Row) => Key)
	loading?: boolean
	selectable?: boolean
	/** Remembers sort and filters in this browser under this name. */
	storageKey?: string
	/** A free-text search across every column (the page's own search box). */
	search?: string
	rowClass?: (row: Row) => string | undefined
	/** Classes for the scroll box (its height decides where the sticky header stops). */
	scrollClass?: string
	onRowClick?: (row: Row) => void
}>()

const selected = defineModel<Key[]>("selected", { default: () => [] })

defineSlots<
	{
		toolbar?: () => unknown
		empty?: () => unknown
		/** On phones, rows are shown as these cards instead of the table. */
		card?: (props: { row: Row }) => unknown
	} & {
		[cell: `cell-${string}`]: ((props: { row: Row; value: unknown; text: string }) => unknown) | undefined
	}
>()

const VALUE_LIMIT = 500

const state = reactive<TableState>(loadState(props.storageKey))
watch(
	() => props.storageKey,
	(key) => Object.assign(state, loadState(key))
)
watch(state, () => saveState(props.storageKey, state), { deep: true })

const shown = computed(() => applyTable(props.rows, props.columns, state, props.search ?? ""))
const filterCount = computed(() => props.columns.filter((c) => filterActive(state.filters[c.key])).length)
const filtering = computed(() => filterCount.value > 0 || !!props.search?.trim())
const menuColumns = computed(() => props.columns.filter(hasMenu))

function hasMenu(c: TableColumn<Row>) {
	return c.sortable !== false || c.filterable !== false
}

function isFiltered(key: string) {
	return filterActive(state.filters[key])
}

function keyOf(row: Row): Key {
	return typeof props.rowKey === "function" ? props.rowKey(row) : (row[props.rowKey ?? "id"] as Key)
}

// sorting ---------------------------------------------------------------------------------------

const sortIcon = computed(() => (state.sort?.dir === "desc" ? "lucide-arrow-up" : "lucide-arrow-down"))

function isSorted(key: string, dir: SortDir) {
	return state.sort?.key === key && state.sort.dir === dir
}

function sortBy(key: string, dir: SortDir) {
	state.sort = isSorted(key, dir) ? null : { key, dir }
}

function ariaSort(key: string) {
	if (state.sort?.key !== key) return undefined
	return state.sort.dir === "asc" ? "ascending" : "descending"
}

function sortLabel(c: TableColumn<Row>, dir: SortDir) {
	if (c.type === "number")
		return dir === "asc" ? __("Sort smallest to largest") : __("Sort largest to smallest")
	if (c.type === "date") return dir === "asc" ? __("Sort oldest to newest") : __("Sort newest to oldest")
	return dir === "asc" ? __("Sort A to Z") : __("Sort Z to A")
}

function sortIconFor(c: TableColumn<Row>, dir: SortDir) {
	if (c.type === "number" || c.type === "date") return dir === "asc" ? "lucide-arrow-down-0-1" : "lucide-arrow-down-1-0"
	return dir === "asc" ? "lucide-arrow-down-a-z" : "lucide-arrow-up-z-a"
}

// the column menu -------------------------------------------------------------------------------

const menuOpen = ref(false)
const anchor = ref<HTMLElement>()
const activeKey = ref("")
const valueSearch = ref("")
let closed = { key: "", at: 0 }

const menuColumn = computed(() => props.columns.find((c) => c.key === activeKey.value))
const menuFilter = computed<ColumnFilter>(() => state.filters[activeKey.value] ?? {})
const menuValues = computed(() =>
	menuOpen.value && menuColumn.value?.filterable !== false
		? distinctValues(props.rows, props.columns, activeKey.value, state.filters, props.search ?? "")
		: []
)
const matchingValues = computed(() => {
	const q = normalize(valueSearch.value)
	if (!q) return menuValues.value
	return menuValues.value.filter((v) => normalize(v.text).includes(q))
})

function openMenu(c: TableColumn<Row>, event: MouseEvent) {
	// a click on the header whose menu just closed (by this very press) only closes it
	if (closed.key === c.key && Date.now() - closed.at < 300) return
	anchor.value = event.currentTarget as HTMLElement
	activeKey.value = c.key
	valueSearch.value = ""
	menuOpen.value = true
}

function menuToggled(open: boolean) {
	if (!open) closed = { key: activeKey.value, at: Date.now() }
}

function setFilter(key: string, change: ColumnFilter) {
	const next = { ...(state.filters[key] ?? {}), ...change }
	if (filterActive(next)) state.filters = { ...state.filters, [key]: next }
	else {
		const { [key]: _removed, ...rest } = state.filters
		state.filters = rest
	}
}

function setContains(value: string) {
	setFilter(activeKey.value, { contains: value })
}

function isChecked(text: string) {
	const values = menuFilter.value.values
	return !Array.isArray(values) || values.includes(text)
}

/** Stores the checked values; every offered value checked means no value filter. */
function setValues(values: Set<string>) {
	const all = menuValues.value.every((v) => values.has(v.text))
	setFilter(activeKey.value, { values: all ? null : [...values] })
}

function checkedSet() {
	const values = menuFilter.value.values
	return new Set(Array.isArray(values) ? values : menuValues.value.map((v) => v.text))
}

function toggleValue(text: string) {
	const values = checkedSet()
	if (values.has(text)) values.delete(text)
	else values.add(text)
	setValues(values)
}

function checkAll() {
	const values = checkedSet()
	for (const v of matchingValues.value) values.add(v.text)
	setValues(values)
}

function uncheckAll() {
	const values = checkedSet()
	for (const v of matchingValues.value) values.delete(v.text)
	setValues(values)
}

function clearFilter(key: string) {
	setFilter(key, { values: null, contains: "" })
}

function clearFilters() {
	state.filters = {}
}

// selection -------------------------------------------------------------------------------------

const selectedSet = computed(() => new Set(selected.value))
const allSelected = computed(() => shown.value.length > 0 && shown.value.every((r) => selectedSet.value.has(keyOf(r))))
const someSelected = computed(() => !allSelected.value && shown.value.some((r) => selectedSet.value.has(keyOf(r))))

function isSelected(row: Row) {
	return selectedSet.value.has(keyOf(row))
}

function toggleRow(row: Row) {
	const key = keyOf(row)
	selected.value = isSelected(row) ? selected.value.filter((k) => k !== key) : [...selected.value, key]
}

/** The header checkbox: selects every row the filters show, or unselects them all. */
function toggleAll() {
	const visible = new Set(shown.value.map(keyOf))
	if (allSelected.value) selected.value = selected.value.filter((k) => !visible.has(k))
	else selected.value = [...new Set([...selected.value, ...visible])]
}
</script>
