<template>
	<Button icon-left="lucide-file-spreadsheet" @click="show">{{ __("Import from Excel") }}</Button>
	<Dialog v-model:open="open" :title="__('Import from Excel')" size="5xl">
		<div class="flex flex-col gap-4">
			<!-- the steps -->
			<ol class="flex flex-wrap items-center gap-x-1 gap-y-2 text-sm">
				<li v-for="(s, i) in steps" :key="s" class="flex items-center gap-1">
					<span
						class="hz-num flex size-6 shrink-0 items-center justify-center rounded-full text-xs"
						:class="
							i + 1 === step
								? 'hz-brand font-semibold'
								: i + 1 < step
									? 'bg-surface-gray-3 text-ink-gray-8'
									: 'bg-surface-gray-2 text-ink-gray-5'
						"
						>{{ fa(i + 1) }}</span
					>
					<span :class="i + 1 === step ? 'font-medium text-ink-gray-9' : 'text-ink-gray-5'">{{ s }}</span>
					<span v-if="i < steps.length - 1" class="lucide-chevron-left mx-1 size-4 text-ink-gray-4" />
				</li>
			</ol>

			<!-- 1. the file -->
			<template v-if="step === 1">
				<ul class="list-disc space-y-1 ps-5 text-sm text-ink-gray-6">
					<li>{{ __("Choose your own Excel (.xlsx) or CSV file; the columns can be in any order.") }}</li>
					<li>{{ __("Next you connect the columns of your file to the fields of the program.") }}</li>
					<li>{{ __("Times, dates and digits are standardised and every row is checked before anything is saved.") }}</li>
					<li>{{ __("If any row is wrong, nothing is saved and the wrong rows are listed.") }}</li>
				</ul>
				<div class="flex flex-wrap items-center gap-2">
					<Button icon-left="lucide-download" :loading="busy === 'sample'" @click="sample">{{
						__("Download the sample")
					}}</Button>
					<span class="text-xs text-ink-gray-5">{{ __("A file made from the sample connects itself.") }}</span>
				</div>
				<input
					ref="fileInput"
					type="file"
					accept=".xlsx,.csv"
					class="block w-full text-sm text-ink-gray-7 file:me-3 file:rounded-3 file:border-0 file:bg-surface-gray-2 file:px-3 file:py-1.5 file:text-ink-gray-8"
					@change="pick"
				/>
				<p v-if="busy === 'inspect'" class="text-sm text-ink-gray-5">{{ __("Reading the file...") }}</p>
				<p v-else-if="file" class="text-sm text-ink-gray-6" dir="auto">{{ __("Chosen file: {0}", [file.name]) }}</p>
			</template>

			<!-- 2. connect the columns -->
			<template v-else-if="step === 2 && inspection">
				<div class="flex flex-wrap items-end gap-3">
					<p class="hz-num flex min-w-0 flex-1 items-center gap-2 text-sm text-ink-gray-6">
						<span class="lucide-file-spreadsheet size-4 shrink-0" />
						<span class="truncate" dir="auto">{{ file?.name }}</span>
						<span class="shrink-0">· {{ fa(__("{0} rows", [inspection.row_count])) }}</span>
					</p>
					<div v-if="inspection.sheets.length > 1" class="w-44">
						<Select v-model="sheet" :label="__('Sheet')" :options="inspection.sheets" />
					</div>
					<div class="w-32">
						<TextInput v-model="headerRow" type="number" min="1" dir="ltr" :label="__('Header row')" />
					</div>
				</div>
				<p class="text-sm text-ink-gray-6">
					{{ __("Connect each field to a column of your file. Fields marked * are required.") }}
				</p>
				<div class="rounded-4 border border-outline-gray-1">
					<div
						v-for="f in inspection.fields"
						:key="f.key"
						class="grid gap-2 border-b border-outline-gray-1 px-3 py-2.5 last:border-0 sm:grid-cols-2 sm:items-start sm:gap-4"
						:class="missingKeys.has(f.key) ? 'bg-surface-red-1' : ''"
					>
						<div class="min-w-0">
							<p class="text-sm font-medium text-ink-gray-8">
								{{ f.label }}<span v-if="f.required" class="text-ink-red-6"> *</span>
							</p>
							<p v-if="hint(f)" class="hz-num text-xs text-ink-gray-5">{{ hint(f) }}</p>
						</div>
						<div class="flex min-w-0 flex-col gap-1.5">
							<Select v-model="mapping.choice[f.key]" :options="pickerOptions" />
							<template v-if="mapping.choice[f.key] === FIXED">
								<Select
									v-if="f.kind === 'choice' && f.choices.length"
									v-model="mapping.fixed[f.key]"
									:placeholder="__('The value')"
									:options="f.choices"
								/>
								<Select
									v-else-if="f.kind === 'bool'"
									v-model="mapping.fixed[f.key]"
									:placeholder="__('The value')"
									:options="yesNo"
								/>
								<JalaliDatePicker
									v-else-if="f.kind === 'jdate'"
									:model-value="mapping.fixed[f.key] || null"
									@update:model-value="mapping.fixed[f.key] = $event ?? ''"
								/>
								<TimeInput
									v-else-if="f.kind === 'time'"
									:model-value="mapping.fixed[f.key] || null"
									@update:model-value="mapping.fixed[f.key] = $event ?? ''"
								/>
								<TextInput v-else v-model="mapping.fixed[f.key]" :placeholder="__('The value')" />
							</template>
							<p v-else-if="chosenColumn(f.key)?.samples.length" class="hz-num truncate text-xs text-ink-gray-5" dir="auto">
								{{ fa(__("For example: {0}", [chosenColumn(f.key)!.samples.slice(0, 3).join("، ")])) }}
							</p>
							<p v-if="missingKeys.has(f.key)" class="text-xs text-ink-red-6">{{ __("Required: connect a column") }}</p>
						</div>
					</div>
				</div>
				<div v-if="unused.length" class="flex flex-col gap-1">
					<p class="text-sm text-ink-gray-6">{{ __("Columns of your file that are not imported") }}</p>
					<div class="flex flex-wrap gap-1.5">
						<span
							v-for="c in unused"
							:key="c.index"
							class="hz-num rounded-3 bg-surface-gray-2 px-2 py-0.5 text-xs text-ink-gray-7"
							dir="auto"
							>{{ columnLetter(c.index) }} · {{ c.header || __("(no header)") }}</span
						>
					</div>
				</div>
			</template>

			<!-- 3. check -->
			<template v-else-if="step === 3 && result">
				<div class="grid grid-cols-3 gap-2">
					<div class="rounded-4 bg-surface-gray-1 p-3">
						<p class="text-xs text-ink-gray-5">{{ __("Rows checked") }}</p>
						<p class="hz-num text-lg font-semibold">{{ fa(result.checked) }}</p>
					</div>
					<div class="rounded-4 p-3" :class="result.errors.length ? 'bg-surface-red-1 text-ink-red-7' : 'bg-surface-green-1 text-ink-green-7'">
						<p class="text-xs opacity-80">{{ __("Rows with problems") }}</p>
						<p class="hz-num text-lg font-semibold">{{ fa(result.errors.length) }}</p>
					</div>
					<div class="rounded-4 bg-surface-amber-1 p-3 text-ink-amber-7">
						<p class="text-xs opacity-80">{{ __("Values standardised") }}</p>
						<p class="hz-num text-lg font-semibold">{{ fa(noteCount) }}</p>
					</div>
				</div>
				<p v-if="!result.checked" class="text-sm text-ink-amber-7">{{ __("There are no rows under the header row.") }}</p>
				<p v-else-if="result.errors.length" class="text-sm text-ink-red-6">
					{{ __("Nothing can be imported until every row is right. Fix the file or the column connections and check again.") }}
				</p>
				<p v-else class="text-sm text-ink-green-7">{{ __("Every row is right. Look through the values, then import.") }}</p>
				<div v-if="result.checked" class="flex flex-wrap items-center gap-3">
					<label v-if="result.errors.length" class="flex items-center gap-2 text-sm">
						<input v-model="onlyProblems" type="checkbox" class="rounded-2" />
						{{ __("Only rows with problems") }}
					</label>
					<span class="flex-1" />
					<span v-if="result.rows.length < result.checked" class="hz-num text-xs text-ink-gray-5">{{
						fa(__("Showing {0} of {1} rows; every row with a problem is shown.", [result.rows.length, result.checked]))
					}}</span>
				</div>
				<div v-if="result.checked" class="max-h-[50vh] overflow-auto rounded-4 border border-outline-gray-1">
					<table class="w-full text-sm">
						<thead class="sticky top-0 z-[1] bg-surface-gray-2 text-xs text-ink-gray-6">
							<tr>
								<th class="px-2 py-1.5 text-start font-medium">{{ __("Row") }}</th>
								<th v-for="f in mappedFields" :key="f.key" class="whitespace-nowrap px-2 py-1.5 text-start font-medium">
									{{ f.label }}
								</th>
								<th class="min-w-48 px-2 py-1.5 text-start font-medium">{{ __("Problems and changes") }}</th>
							</tr>
						</thead>
						<tbody>
							<tr
								v-for="r in shownRows"
								:key="r.row"
								class="border-t border-outline-gray-1 align-top"
								:class="r.errors.length ? 'bg-surface-red-1 text-ink-red-7' : ''"
							>
								<td class="hz-num px-2 py-1.5 text-ink-gray-5">{{ fa(r.row) }}</td>
								<td
									v-for="f in mappedFields"
									:key="f.key"
									class="hz-num whitespace-nowrap px-2 py-1.5"
									dir="auto"
									:title="noteFor(r.notes, f.label)"
								>
									<span
										:class="noteFor(r.notes, f.label) ? 'rounded-2 bg-surface-amber-2 px-1 text-ink-amber-8' : ''"
										>{{ shown(r.values[f.key]) }}</span
									>
								</td>
								<td class="px-2 py-1.5 text-xs">
									<p v-for="(e, i) in r.errors" :key="'e' + i" class="hz-num font-medium text-ink-red-7">{{ fa(e) }}</p>
									<p v-for="(n, i) in r.notes" :key="'n' + i" class="hz-num text-ink-gray-5" dir="auto">{{ fa(n) }}</p>
								</td>
							</tr>
						</tbody>
					</table>
				</div>
			</template>

			<!-- 4. done -->
			<template v-else-if="step === 4 && result">
				<div class="flex flex-col items-center gap-2 rounded-4 bg-surface-green-1 p-6 text-ink-green-7">
					<span class="lucide-circle-check size-8" />
					<p class="hz-num text-base font-semibold">{{ fa(__("{0} rows imported", [result.created])) }}</p>
				</div>
			</template>

			<ErrorMessage :message="error" />
		</div>
		<template #actions>
			<div class="flex w-full flex-wrap items-center justify-end gap-2">
				<template v-if="step === 1">
					<Button
						variant="solid"
						icon-right="lucide-chevron-left"
						:disabled="!file"
						:loading="busy === 'inspect'"
						@click="inspect()"
						>{{ __("Next") }}</Button
					>
				</template>
				<template v-else-if="step === 2">
					<Button icon-left="lucide-chevron-right" @click="step = 1">{{ __("Back") }}</Button>
					<Button
						variant="solid"
						icon-left="lucide-list-checks"
						:disabled="missingKeys.size > 0 || busy === 'inspect'"
						:loading="busy === 'check'"
						@click="check"
						>{{ __("Check the data") }}</Button
					>
				</template>
				<template v-else-if="step === 3 && result">
					<Button icon-left="lucide-chevron-right" @click="step = 2">{{ __("Back to the columns") }}</Button>
					<Button
						variant="solid"
						icon-left="lucide-upload"
						:disabled="!!result.errors.length || !result.checked"
						:loading="busy === 'import'"
						@click="save"
						>{{ fa(__("Import {0} rows", [result.checked])) }}</Button
					>
				</template>
				<template v-else>
					<Button variant="solid" @click="open = false">{{ __("Close") }}</Button>
				</template>
			</div>
		</template>
	</Dialog>
</template>

<script setup lang="ts">
import { Button, Dialog, ErrorMessage, Select, TextInput } from "frappe-ui"
import { computed, reactive, ref, watch } from "vue"
import JalaliDatePicker from "@/components/JalaliDatePicker.vue"
import TimeInput from "@/components/TimeInput.vue"
import { api, downloadGet } from "@/lib/api"
import { __ } from "@/lib/i18n"
import {
	columnLetter,
	FIXED,
	headerSignature,
	initialMapping,
	type MappingState,
	missingFields,
	noteFor,
	rememberedMapping,
	rememberMapping,
	SKIP,
	toPayload,
	unusedColumns,
} from "@/lib/imports"
import { fa } from "@/lib/jalali"
import { invalidateRef } from "@/lib/refs"
import type { ImportField, ImportInspection, ImportResult } from "@/lib/types"

// `name` is the import spec (the same name as the admin resource: departments, shifts, ...)
const props = defineProps<{ name: string }>()
const emit = defineEmits<{ done: [] }>()

const open = ref(false)
const step = ref(1)
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement>()
const busy = ref("")
const error = ref("")
const inspection = ref<ImportInspection | null>(null)
const sheet = ref("")
const headerRow = ref<string | number>("")
const mapping = reactive<MappingState>({ choice: {}, fixed: {} })
const result = ref<ImportResult | null>(null)
const onlyProblems = ref(false)

const steps = computed(() => [__("File"), __("Connect columns"), __("Check"), __("Import")])
const yesNo = computed(() => [
	{ value: "yes", label: __("Yes") },
	{ value: "no", label: __("No") },
])

function show() {
	step.value = 1
	file.value = null
	if (fileInput.value) fileInput.value.value = ""
	error.value = ""
	inspection.value = null
	result.value = null
	open.value = true
}

async function sample() {
	busy.value = "sample"
	error.value = ""
	try {
		await downloadGet(`/import/${props.name}/template`)
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

function pick(event: Event) {
	file.value = (event.target as HTMLInputElement).files?.[0] ?? null
	inspection.value = null
	result.value = null
	error.value = ""
	if (file.value) inspect()
}

// --- 2. connect the columns ---------------------------------------------------------------

async function inspect(chosenSheet?: string, chosenHeaderRow?: number) {
	if (!file.value) return
	busy.value = "inspect"
	error.value = ""
	try {
		const data = new FormData()
		data.append("file", file.value)
		if (chosenSheet) data.append("sheet", chosenSheet)
		if (chosenHeaderRow) data.append("header_row", String(chosenHeaderRow))
		const found = await api.upload<ImportInspection>(`/import/${props.name}/inspect`, data)
		const start = initialMapping(found, rememberedMapping(props.name, headerSignature(found.columns)))
		mapping.choice = start.choice
		mapping.fixed = start.fixed
		inspection.value = found
		sheet.value = found.sheet
		headerRow.value = found.header_row
		result.value = null
		step.value = 2
	} catch (e) {
		error.value = (e as Error).message
		// a wrong header row: show what the file had before
		if (inspection.value) {
			sheet.value = inspection.value.sheet
			headerRow.value = inspection.value.header_row
		}
	} finally {
		busy.value = ""
	}
}

watch(sheet, (value) => {
	if (inspection.value && value && value !== inspection.value.sheet) inspect(value)
})

let headerTimer: ReturnType<typeof setTimeout> | undefined
watch(headerRow, (value) => {
	clearTimeout(headerTimer)
	const row = Number(value)
	if (!inspection.value || !Number.isInteger(row) || row < 1 || row === inspection.value.header_row) return
	headerTimer = setTimeout(() => inspect(inspection.value?.sheet, row), 600)
})

const pickerOptions = computed(() => [
	{ value: SKIP, label: __("Not imported") },
	{ value: FIXED, label: __("The same value for every row") },
	...(inspection.value?.columns ?? []).map((c) => ({
		value: String(c.index),
		label: `${columnLetter(c.index)} · ${c.header || __("(no header)")}`,
		description: c.samples.length ? fa(c.samples.slice(0, 2).join("، ")) : undefined,
	})),
])

function chosenColumn(key: string) {
	const choice = mapping.choice[key]
	if (!choice || choice === SKIP || choice === FIXED) return undefined
	return inspection.value?.columns.find((c) => String(c.index) === choice)
}

const missingKeys = computed(
	() => new Set(inspection.value ? missingFields(mapping, inspection.value.fields).map((f) => f.key) : [])
)
const unused = computed(() => (inspection.value ? unusedColumns(mapping, inspection.value.columns) : []))

function hint(f: ImportField): string {
	const parts: string[] = []
	if (f.kind === "jdate") parts.push(__("Jalali date, like 1405/07/01"))
	else if (f.kind === "time") parts.push(__("Time, like 08:30"))
	else if (f.kind === "number") parts.push(__("A number"))
	else if (f.kind === "bool") parts.push(__("Yes or No"))
	else if (f.kind === "choice" && f.choices.length) parts.push(__("One of: {0}", [f.choices.join("، ")]))
	else if (f.kind === "ref") parts.push(__("The name or code of an existing record"))
	if (f.example && f.kind !== "choice") parts.push(__("Example: {0}", [f.example]))
	if (f.help) parts.push(f.help)
	return fa(parts.join(" · "))
}

// --- 3. check, 4. import ------------------------------------------------------------------

function request(dryRun: boolean): FormData {
	const data = new FormData()
	data.append("file", file.value!)
	data.append("mapping", JSON.stringify(toPayload(mapping, inspection.value!.fields)))
	data.append("sheet", inspection.value!.sheet)
	data.append("header_row", String(inspection.value!.header_row))
	data.append("dry_run", dryRun ? "true" : "false")
	return data
}

async function check() {
	if (!file.value || !inspection.value) return
	busy.value = "check"
	error.value = ""
	try {
		result.value = await api.upload<ImportResult>(`/import/${props.name}`, request(true))
		rememberMapping(
			props.name,
			headerSignature(inspection.value.columns),
			toPayload(mapping, inspection.value.fields)
		)
		onlyProblems.value = result.value.errors.length > 0
		step.value = 3
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

async function save() {
	if (!file.value || !inspection.value) return
	busy.value = "import"
	error.value = ""
	try {
		const done = await api.upload<ImportResult>(`/import/${props.name}`, request(false))
		result.value = done
		if (done.imported) {
			step.value = 4
			invalidateRef(props.name)
			emit("done")
		} else {
			// the data changed since the check: show the new problems
			onlyProblems.value = done.errors.length > 0
		}
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

const mappedFields = computed(() => {
	if (!inspection.value) return []
	const payload = toPayload(mapping, inspection.value.fields)
	return inspection.value.fields.filter((f) => payload[f.key] !== undefined)
})
const shownRows = computed(() =>
	(result.value?.rows ?? []).filter((r) => !onlyProblems.value || r.errors.length)
)
const noteCount = computed(() => (result.value?.rows ?? []).reduce((sum, r) => sum + r.notes.length, 0))

function shown(value: unknown): string {
	if (value === null || value === undefined) return ""
	if (typeof value === "boolean") return value ? __("Yes") : __("No")
	return fa(value)
}
</script>
