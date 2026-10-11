<template>
	<div>
		<label v-if="label" class="mb-1.5 block text-xs text-ink-gray-5">{{ label }}</label>
		<input
			type="time"
			dir="ltr"
			class="hz-num rounded-3 border border-transparent bg-surface-gray-2 text-ink-gray-8 hover:bg-surface-gray-3 focus:border-outline-gray-4 focus:outline-none focus:ring-0"
			:class="size === 'sm' ? 'h-7 w-[6.5rem] px-1.5 text-sm' : 'h-9 w-full px-2.5 text-base'"
			:value="modelValue ?? ''"
			:aria-label="ariaLabel || label"
			@input="emit('update:modelValue', ($event.target as HTMLInputElement).value || null)"
		/>
	</div>
</template>

<script setup lang="ts">
// `size="sm"`: a compact input that fits in a row (the exact times under the shift timeline)
defineProps<{ modelValue?: string | null; label?: string; size?: "sm"; ariaLabel?: string }>()
const emit = defineEmits<{ "update:modelValue": [value: string | null] }>()
</script>
