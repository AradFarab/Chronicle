<template>
	<div class="flex rounded-4 bg-surface-gray-2 p-0.5" role="tablist">
		<button
			v-for="o in options"
			:key="o.value"
			type="button"
			role="tab"
			:aria-selected="modelValue === o.value"
			class="flex-1 rounded-3 px-2 py-1.5 text-sm"
			:class="
				modelValue === o.value ? 'bg-surface-base font-medium text-ink-gray-9 shadow-sm' : 'text-ink-gray-6'
			"
			@click="emit('update:modelValue', o.value)"
		>
			{{ o.label }}
		</button>
	</div>
</template>

<script setup lang="ts">
import type { Option } from "@/lib/types"

defineProps<{ modelValue: string; options: Option[] }>()
const emit = defineEmits<{ "update:modelValue": [value: string] }>()
</script>
