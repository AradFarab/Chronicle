<template>
	<div>
		<label v-if="label" class="mb-1.5 block text-xs text-ink-gray-5">{{ label }}</label>
		<input
			type="time"
			dir="ltr"
			class="hz-num h-9 w-full rounded-3 border border-transparent bg-surface-gray-2 px-2.5 text-base text-ink-gray-8 hover:bg-surface-gray-3 focus:border-outline-gray-4 focus:outline-none focus:ring-0"
			:value="modelValue ?? ''"
			@input="emit('update:modelValue', ($event.target as HTMLInputElement).value || null)"
		/>
	</div>
</template>

<script setup lang="ts">
defineProps<{ modelValue?: string | null; label?: string }>()
const emit = defineEmits<{ "update:modelValue": [value: string | null] }>()
</script>
