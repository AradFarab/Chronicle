<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Monthly period lock')" back="manage" />
		<p class="text-sm text-ink-gray-6">
			{{ __("A closed month cannot change: no request, correction or recalculation touches it until it is reopened.") }}
		</p>
		<div class="flex items-center gap-2">
			<Button icon="lucide-chevron-right" :aria-label="__('Previous year')" @click="year--" />
			<span class="hz-num w-16 text-center font-semibold">{{ fa(year) }}</span>
			<Button icon="lucide-chevron-left" :aria-label="__('Next year')" @click="year++" />
		</div>
		<ErrorMessage :message="error" />
		<DataTable :columns="columns" :rows="months" :loading="loading" row-key="jmonth" storage-key="periods">
			<template #cell-status="{ row: p, text }">
				<span class="flex items-center gap-2">
					<span
						:class="p.status === 'closed' ? 'lucide-lock text-ink-gray-7' : 'lucide-lock-open text-ink-gray-4'"
						class="size-4"
					/>
					{{ text }}
				</span>
			</template>
			<template #cell-actions="{ row: p }">
				<Button v-if="p.status === 'open'" size="sm" :loading="busy === p.jmonth" @click="close(p)">{{
					__("Close")
				}}</Button>
				<Button v-else size="sm" theme="red" variant="subtle" :loading="busy === p.jmonth" @click="reopen(p)">{{
					__("Reopen")
				}}</Button>
			</template>
		</DataTable>
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, toast } from "frappe-ui"
import { onMounted, ref, watch } from "vue"
import DataTable from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa, MONTHS } from "@/lib/jalali"
import { session } from "@/lib/session"
import type { TableColumn } from "@/lib/table"

interface Period {
	jyear: number
	jmonth: number
	status: string
	closed_at: string | null
	note: string | null
}

const year = ref(Number((session.today || "1405").slice(0, 4)))
const months = ref<Period[]>([])
const error = ref("")
const busy = ref<number | null>(null)
const loading = ref(false)

const columns: TableColumn<Period>[] = [
	{ key: "jmonth", label: __("Month"), type: "number", format: (p) => MONTHS[p.jmonth - 1], class: "font-medium" },
	{ key: "status", label: __("Status"), value: (p) => (p.status === "closed" ? __("Closed") : __("Not closed")) },
	{ key: "closed_at", label: __("Closed on"), type: "date", format: (p) => fa(p.closed_at ?? "") },
	{ key: "note", label: __("Note"), class: "min-w-48" },
	{ key: "actions", label: "", sortable: false, filterable: false },
]

async function load() {
	error.value = ""
	loading.value = true
	try {
		months.value = await api.get<Period[]>(`/periods/${year.value}`)
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

async function run(p: Period, action: "close" | "reopen", note: string | null) {
	busy.value = p.jmonth
	try {
		await api.post(`/periods/${p.jyear}/${p.jmonth}/${action}`, { note })
		toast.success(action === "close" ? __("Closed") : __("Reopened"))
		load()
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = null
	}
}

function close(p: Period) {
	if (window.confirm(__("Close {0}? Nothing in it can change afterwards.", [MONTHS[p.jmonth - 1]]))) run(p, "close", null)
}

function reopen(p: Period) {
	const reason = window.prompt(__("Reason for reopening"))
	if (reason) run(p, "reopen", reason)
}

watch(year, load)
onMounted(load)
</script>
