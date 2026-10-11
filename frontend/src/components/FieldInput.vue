<template>
	<div v-if="field.type === 'badge'">
		<Badge v-if="modelValue" theme="blue" :label="field.label" />
	</div>
	<Switch
		v-else-if="field.type === 'bool'"
		:model-value="Boolean(modelValue)"
		:label="field.label"
		:description="field.help"
		@update:model-value="set"
	/>
	<JalaliDatePicker
		v-else-if="field.type === 'jdate'"
		:model-value="(modelValue as string | null) ?? null"
		:label="label"
		@update:model-value="set"
	/>
	<TimeInput
		v-else-if="field.type === 'time'"
		:model-value="(modelValue as string | null) ?? null"
		:label="label"
		@update:model-value="set"
	/>
	<Select
		v-else-if="field.type === 'select'"
		:model-value="(modelValue as string | number | null) ?? null"
		:label="label"
		:description="field.help"
		:options="field.options ? field.options() : []"
		@update:model-value="set"
	/>
	<Combobox
		v-else-if="field.type === 'ref'"
		:model-value="(modelValue as number | null) ?? null"
		:label="label"
		:description="field.help"
		:options="refOptions(field.ref!)"
		:placeholder="__('Choose')"
		@update:model-value="set"
	/>
	<div v-else-if="field.type === 'color'">
		<label class="mb-1.5 block text-xs text-ink-gray-5">{{ label }}</label>
		<div class="flex items-center gap-2">
			<input
				type="color"
				class="h-8 w-10 shrink-0 cursor-pointer rounded-3 border border-outline-gray-2 bg-surface-base p-0.5"
				:value="hexColor"
				:aria-label="field.label"
				@input="set(($event.target as HTMLInputElement).value)"
			/>
			<TextInput
				class="min-w-0 flex-1"
				:model-value="(modelValue as string | null) ?? ''"
				dir="ltr"
				placeholder="#0d9488"
				@update:model-value="(v: string) => set(v || null)"
			/>
		</div>
		<p v-if="field.help" class="mt-1.5 text-xs text-ink-gray-5">{{ field.help }}</p>
	</div>
	<Textarea
		v-else-if="field.type === 'textarea'"
		:model-value="(modelValue as string | null) ?? ''"
		:label="label"
		:description="field.help"
		:rows="2"
		@update:model-value="set"
	/>
	<TextInput
		v-else-if="field.type === 'number'"
		:model-value="modelValue === null || modelValue === undefined ? '' : String(modelValue)"
		type="number"
		dir="ltr"
		:label="label"
		:description="field.help"
		@update:model-value="(v: string) => set(v === '' ? null : Number(v))"
	/>
	<TextInput
		v-else
		:model-value="(modelValue as string | null) ?? ''"
		:dir="field.dir"
		:label="label"
		:description="field.help"
		@update:model-value="set"
	/>
</template>

<script setup lang="ts">
import { Badge, Combobox, Select, Switch, Textarea, TextInput } from "frappe-ui"
import { computed } from "vue"
import { refOptions } from "@/lib/refs"
import type { FieldDef } from "@/lib/resources"
import JalaliDatePicker from "./JalaliDatePicker.vue"
import TimeInput from "./TimeInput.vue"

const props = defineProps<{ field: FieldDef; modelValue: unknown }>()
const emit = defineEmits<{ "update:modelValue": [value: unknown] }>()

const label = computed(() => (props.field.required ? `${props.field.label} *` : props.field.label))
// the colour picker only takes #rrggbb
const hexColor = computed(() => (/^#[0-9a-f]{6}$/i.test(String(props.modelValue ?? "")) ? String(props.modelValue) : "#0d9488"))

function set(value: unknown) {
	emit("update:modelValue", value)
}
</script>
