<template>
	<Badge v-if="status" :theme="tone(status)" :label="label || statusLabel(status)" />
</template>

<script setup lang="ts">
import { Badge } from "frappe-ui"
import { statusLabel, tone } from "@/lib/format"

defineProps<{ status?: string | null; label?: string }>()
</script>
