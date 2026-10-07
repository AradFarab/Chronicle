<template>
	<div>
		<label v-if="label" class="mb-1.5 block text-xs text-ink-gray-5">{{ label }}</label>
		<select
			class="h-9 w-full rounded-3 border border-transparent bg-surface-gray-2 px-2.5 text-base text-ink-gray-8 hover:bg-surface-gray-3 focus:border-outline-gray-4 focus:outline-none focus:ring-0"
			:value="modelValue ?? ''"
			@change="emit('update:modelValue', ($event.target as HTMLSelectElement).value || null)"
		>
			<option v-if="placeholder !== undefined" value="">{{ placeholder }}</option>
			<option v-for="e in employees" :key="e.name" :value="e.name">{{ e.full_name }} ({{ fa(e.name) }})</option>
		</select>
	</div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { call } from "@/lib/api"
import { fa } from "@/lib/jalali"

defineProps<{ modelValue?: string | null; label?: string; placeholder?: string }>()
const emit = defineEmits<{ "update:modelValue": [value: string | null] }>()

interface Row {
	name: string
	full_name: string
}
const employees = ref<Row[]>([])
onMounted(async () => {
	employees.value = await call<Row[]>("hozur.api.pwa.employees", { limit: 500 })
})
</script>
