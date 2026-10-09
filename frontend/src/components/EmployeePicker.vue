<template>
	<div>
		<label v-if="label" class="mb-1.5 block text-xs text-ink-gray-5">{{ label }}</label>
		<select
			class="h-9 w-full rounded-3 border border-transparent bg-surface-gray-2 px-2.5 text-base text-ink-gray-8 hover:bg-surface-gray-3 focus:border-outline-gray-4 focus:outline-none focus:ring-0"
			:value="modelValue ?? ''"
			@change="pick(($event.target as HTMLSelectElement).value)"
		>
			<option v-if="placeholder !== undefined" value="">{{ placeholder }}</option>
			<option v-for="e in shown" :key="e.id" :value="e.id">{{ e.full_name }} ({{ fa(e.code) }})</option>
		</select>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { api } from "@/lib/api"
import { fa } from "@/lib/jalali"
import type { Employee } from "@/lib/types"

const props = defineProps<{
	modelValue?: number | null
	label?: string
	placeholder?: string
	exclude?: number | null
	everyone?: boolean // all active employees, for managers handing something to a peer
}>()
const emit = defineEmits<{ "update:modelValue": [value: number | null] }>()

// the server already narrows the list to the people this user may see
const employees = ref<Employee[]>([])
// people who have left stay out of the list unless one of them is the current choice
const shown = computed(() =>
	employees.value.filter((e) => e.id !== props.exclude && (e.status !== "left" || e.id === props.modelValue))
)

function pick(value: string) {
	emit("update:modelValue", value ? Number(value) : null)
}

onMounted(async () => {
	try {
		employees.value = await api.get<Employee[]>(props.everyone ? "/people/active" : "/admin/employees")
	} catch {
		// without the list the picker stays empty; the page shows its own errors
	}
})
</script>
