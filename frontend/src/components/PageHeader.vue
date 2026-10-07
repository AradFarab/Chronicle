<template>
	<div class="flex items-center gap-2">
		<Button v-if="back" :aria-label="__('Back')" icon="lucide-arrow-right" :route="{ name: back }" />
		<h1 class="flex-1 text-xl font-semibold">{{ title }}</h1>
		<slot />
	</div>
</template>

<script setup lang="ts">
import { Button } from "frappe-ui"

defineProps<{ title: string; back?: string }>()
</script>
