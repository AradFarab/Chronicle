<template>
	<Switch
		v-if="field.type === 'bool'"
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
import { Combobox, Select, Switch, Textarea, TextInput } from "frappe-ui"
import { computed } from "vue"
import { refOptions } from "@/lib/refs"
import type { FieldDef } from "@/lib/resources"
import JalaliDatePicker from "./JalaliDatePicker.vue"
import TimeInput from "./TimeInput.vue"

const props = defineProps<{ field: FieldDef; modelValue: unknown }>()
const emit = defineEmits<{ "update:modelValue": [value: unknown] }>()

const label = computed(() => (props.field.required ? `${props.field.label} *` : props.field.label))

function set(value: unknown) {
	emit("update:modelValue", value)
}
</script>
