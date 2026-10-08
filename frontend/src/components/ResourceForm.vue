<template>
	<Dialog v-model:open="open" :title="title" size="2xl">
		<form class="flex flex-col gap-4" @submit.prevent="save">
			<template v-for="field in visibleFields" :key="field.key">
				<!-- child rows (days of a pattern, steps of a process) -->
				<div v-if="field.type === 'children'" class="flex flex-col gap-2">
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
			</template>
			<Textarea
				v-if="def.reasonOnChange && row"
				v-model="reason"
				:label="__('Reason for the change') + ' *'"
				:rows="2"
			/>
			<ErrorMessage :message="error" />
		</form>
		<template #actions>
			<div class="flex gap-2">
				<Button variant="solid" :loading="busy" @click="save">{{ __("Save") }}</Button>
				<Button
					v-if="row && def.canDelete && !readOnly"
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
import { computed, reactive, ref, watch } from "vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import { invalidateRef } from "@/lib/refs"
import { PARAMETER_LABELS, type FieldDef, type ResourceDef } from "@/lib/resources"
import FieldInput from "./FieldInput.vue"

interface Parameter {
	name: string
	article: string
	unit: string
	legal_check: boolean
	legal_value: number
}

const props = defineProps<{ def: ResourceDef; row: Record<string, unknown> | null; readOnly?: boolean }>()
const emit = defineEmits<{ saved: [] }>()
const open = defineModel<boolean>("open", { default: false })

const values = reactive<Record<string, unknown>>({})
const params = reactive<Record<string, number | null>>({})
const parameters = ref<Parameter[]>([])
const reason = ref("")
const error = ref("")
const busy = ref(false)

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
		Object.assign(values, JSON.parse(JSON.stringify(props.row ?? props.def.defaults ?? {})))
		for (const f of props.def.fields) if (f.type === "children" && !values[f.key]) values[f.key] = []
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
