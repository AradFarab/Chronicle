<template>
	<ul v-if="punches.length" class="divide-y divide-outline-gray-1">
		<li v-for="(p, i) in punches" :key="p.ref + i" class="flex items-center gap-3 py-2">
			<span
				class="flex size-8 items-center justify-center rounded-full"
				:class="
					p.direction === 'Out'
						? 'bg-surface-amber-2 text-ink-amber-6'
						: 'bg-surface-green-2 text-ink-green-6'
				"
			>
				<span :class="p.direction === 'Out' ? 'lucide-log-out' : 'lucide-log-in'" class="size-4" />
			</span>
			<span class="hz-num text-lg font-semibold">{{ clock(p.time) }}</span>
			<span class="text-sm text-ink-gray-5">{{ __(p.direction || "Unknown") }}</span>
			<span class="flex-1" />
			<Badge :theme="p.source === 'Manual' ? 'violet' : 'gray'" :label="sourceLabel(p.source)" />
		</li>
	</ul>
	<p v-else class="py-3 text-center text-sm text-ink-gray-5">{{ __("No punches") }}</p>
</template>

<script setup lang="ts">
import { Badge } from "frappe-ui"
import { clock, sourceLabel } from "@/lib/format"
import { __ } from "@/lib/i18n"
import type { Punch } from "@/lib/types"

defineProps<{ punches: Punch[] }>()
</script>
