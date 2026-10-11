<template>
	<Dialog v-model:open="open" :title="title" :size="def.size ?? '2xl'">
		<form class="grid grid-cols-1 gap-4" :class="COLUMNS[def.columns ?? 1]" @submit.prevent="save">
			<div v-for="field in visibleFields" :key="field.key" class="min-w-0" :class="isWide(field) ? 'col-span-full' : ''">
				<!-- a custom editor of part of the record (the shift timeline, the work-pattern grid) -->
				<div v-if="field.type === 'editor'" class="flex flex-col gap-2">
					<p class="text-sm font-medium">{{ field.label }}</p>
					<p v-if="field.help" class="text-xs text-ink-gray-5">{{ field.help }}</p>
					<component
						:is="EDITORS[field.editor!]"
						:ref="(el: unknown) => (editors[field.key] = el as EditorHandle | null)"
						:model-value="values"
						@update:model-value="(patch: Record<string, unknown>) => Object.assign(values, patch)"
					/>
				</div>
				<!-- child rows (steps of a process) -->
				<div v-else-if="field.type === 'children'" class="flex flex-col gap-2">
					<p class="text-sm font-medium">{{ field.label }}</p>
					<div
						v-for="(child, i) in (values[field.key] as Record<string, unknown>[])"
						:key="i"
						class="flex items-end gap-2 rounded-4 bg-surface-gray-1 p-2"
					>
						<div v-for="c in childFields(field)" :key="c.key" class="min-w-0 flex-1">
							<FieldInput v-model="child[c.key]" :field="c" />
						</div>
						<Button :aria-label="__('Remove')" icon="lucide-trash-2" @click="removeChild(field, i)" />
					</div>
					<Button class="self-start" icon-left="lucide-plus" @click="addChild(field)">{{ __("Add a row") }}</Button>
				</div>
				<!-- labor-law parameters of a rule set -->
				<div v-else-if="field.type === 'params'" class="flex flex-col gap-2">
					<p class="text-sm font-medium">{{ field.label }}</p>
					<p class="text-xs text-ink-gray-5">
						{{ __("A value may be better for the worker than the law, never worse.") }}
					</p>
					<div v-for="p in parameters" :key="p.name" class="grid grid-cols-[1fr_8rem] items-center gap-2">
						<label class="text-sm">
							{{ PARAMETER_LABELS[p.name] ?? p.name }}
							<span class="text-xs text-ink-gray-5"
								>· {{ __("Article {0}", [fa(p.article.replace("note", __("note")))]) }} · {{ __("Law: {0}", [fa(p.legal_value)]) }}</span
							>
							<span v-if="p.legal_check" class="text-xs text-ink-amber-3"> · {{ __("to be checked") }}</span>
						</label>
						<TextInput
							:model-value="String(params[p.name] ?? '')"
							type="number"
							dir="ltr"
							@update:model-value="(v: string) => (params[p.name] = v === '' ? null : Number(v))"
						/>
					</div>
				</div>
				<FieldInput v-else v-model="values[field.key]" :field="field" />
			</div>
			<Textarea
				v-if="def.reasonOnChange && row"
				v-model="reason"
				class="col-span-full"
				:label="__('Reason for the change') + ' *'"
				:rows="2"
			/>
			<ErrorMessage class="col-span-full" :message="error" />
		</form>
		<template #actions>
			<div class="flex gap-2">
				<Button variant="solid" :loading="busy" @click="save">{{ __("Save") }}</Button>
				<Button
					v-if="row && def.canDelete && !readOnly && !row.is_ceo"
					theme="red"
					:loading="busy"
					@click="remove"
					>{{ __("Delete") }}</Button
				>
			</div>
		</template>
	</Dialog>
</template>

<script setup lang="ts">
import { Button, Dialog, ErrorMessage, Textarea, TextInput, toast } from "frappe-ui"
import { computed, reactive, ref, watch, type Component } from "vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import { invalidateRef } from "@/lib/refs"
import { PARAMETER_LABELS, type FieldDef, type ResourceDef } from "@/lib/resources"
import FieldInput from "./FieldInput.vue"
import PatternGrid from "./PatternGrid.vue"
import ShiftTimeline from "./ShiftTimeline.vue"

interface Parameter {
	name: string
	article: string
	unit: string
	legal_check: boolean
	legal_value: number
}

/**
 * Custom editors (fields of type "editor"). One gets the whole record as `modelValue`, emits
 * `update:modelValue` with the keys it changed, and may expose `beforeSave()`: it runs before the
 * form is sent, may throw an Error whose message the form shows, and may return more keys to send
 * (the work-pattern grid first creates the shifts drawn on it).
 */
const EDITORS: Record<NonNullable<FieldDef["editor"]>, Component> = {
	"shift-timeline": ShiftTimeline,
	"pattern-grid": PatternGrid,
}

interface EditorHandle {
	beforeSave?: () => Record<string, unknown> | void | Promise<Record<string, unknown> | void>
}

const COLUMNS = { 1: "", 2: "sm:grid-cols-2", 3: "sm:grid-cols-2 md:grid-cols-3" }
const WIDE: FieldDef["type"][] = ["editor", "children", "params", "textarea"]
const isWide = (field: FieldDef) => WIDE.includes(field.type)

// `initial` pre-fills a new record (e.g. the parent of a new designation)
const props = defineProps<{
	def: ResourceDef
	row: Record<string, unknown> | null
	readOnly?: boolean
	initial?: Record<string, unknown>
}>()
const emit = defineEmits<{ saved: [] }>()
const open = defineModel<boolean>("open", { default: false })

const values = reactive<Record<string, unknown>>({})
const params = reactive<Record<string, number | null>>({})
const parameters = ref<Parameter[]>([])
const reason = ref("")
const error = ref("")
const busy = ref(false)
const editors: Record<string, EditorHandle | null> = {}

const title = computed(() => (props.row ? props.def.singular : __("New {0}", [props.def.singular])))
const visibleFields = computed(() => props.def.fields.filter((f) => !f.show || f.show(values)))

function childFields(field: FieldDef) {
	return (field.children ?? []).filter((c) => !c.show || c.show(values))
}

function addChild(field: FieldDef) {
	const rows = (values[field.key] as Record<string, unknown>[]) ?? []
	const next: Record<string, unknown> = {}
	for (const c of field.children ?? []) next[c.key] = null
	if ("position" in next) next.position = rows.length + 1
	if ("cycle_day" in next && values.pattern_type === "rotating") next.cycle_day = rows.length + 1
	values[field.key] = [...rows, next]
}

function removeChild(field: FieldDef, index: number) {
	values[field.key] = (values[field.key] as unknown[]).filter((_, i) => i !== index)
}

watch(
	() => [open.value, props.row],
	async () => {
		if (!open.value) return
		error.value = ""
		reason.value = ""
		for (const key of Object.keys(values)) delete values[key]
		Object.assign(values, JSON.parse(JSON.stringify(props.row ?? { ...props.def.defaults, ...props.initial })))
		for (const f of props.def.fields) {
			if (f.type === "children" && !values[f.key]) values[f.key] = []
			for (const key of f.keys ?? []) if (values[key] === undefined) values[key] = null
		}
		if (props.def.fields.some((f) => f.type === "params")) {
			parameters.value = await api.get<Parameter[]>("/admin/rule-parameters")
			for (const key of Object.keys(params)) delete params[key]
			const current = (values.parameters as Record<string, number> | undefined) ?? {}
			for (const p of parameters.value) params[p.name] = current[p.name] ?? p.legal_value
		}
	},
	{ immediate: true }
)

function payload(): Record<string, unknown> {
	const body: Record<string, unknown> = {}
	for (const f of props.def.fields) {
		if (f.type === "badge") continue
		if (f.type === "editor") {
			for (const key of f.keys ?? []) body[key] = values[key] ?? null
			continue
		}
		if (f.show && !f.show(values) && f.type !== "children") continue
		if (f.type === "params") body[f.key] = { ...params }
		else if (f.type === "children")
			body[f.key] = ((values[f.key] as Record<string, unknown>[]) ?? []).map((c) => {
				const out: Record<string, unknown> = {}
				for (const cf of f.children ?? []) if (!cf.show || cf.show(values)) out[cf.key] = c[cf.key] ?? null
				return out
			})
		else body[f.key] = values[f.key] ?? null
	}
	if (reason.value) body.reason = reason.value
	return body
}

async function save() {
	busy.value = true
	error.value = ""
	try {
		for (const f of visibleFields.value) {
			if (f.type !== "editor") continue
			const patch = await editors[f.key]?.beforeSave?.()
			if (patch) Object.assign(values, patch)
		}
		if (props.row) await api.patch(`/admin/${props.def.name}/${props.row.id}`, payload())
		else await api.post(`/admin/${props.def.name}`, payload())
		invalidateRef(props.def.name)
		toast.success(__("Saved"))
		open.value = false
		emit("saved")
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = false
	}
}

async function remove() {
	if (!props.row || !window.confirm(__("Delete this record?"))) return
	busy.value = true
	try {
		await api.del(`/admin/${props.def.name}/${props.row.id}`)
		invalidateRef(props.def.name)
		toast.success(__("Deleted"))
		open.value = false
		emit("saved")
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = false
	}
}
</script>
