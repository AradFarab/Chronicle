<template>
	<div class="space-y-4">
		<h1 class="text-lg font-bold">{{ __("Waiting for my approval") }}</h1>
		<ErrorMessage v-if="error" :message="error" />
		<DataTable :columns="columns" :rows="rows" :loading="loading" storage-key="approvals">
			<template #empty>{{ __("Nothing is waiting for you") }}</template>
			<template #cell-request_type="{ row: r, text }">
				<Badge :label="text" />
				<p v-if="r.is_acceptance" class="mt-1 max-w-56 text-xs text-ink-amber-7">
					{{ __("Your manager assigned this overtime; it needs your acceptance (Article 59).") }}
				</p>
			</template>
			<template #cell-actions="{ row: r }">
				<div class="flex gap-1 whitespace-nowrap">
					<Button
						size="sm"
						variant="solid"
						theme="green"
						icon-left="lucide-check"
						:loading="busy === r.id + 'approve'"
						@click="act(r, 'approve')"
					>
						{{ r.is_acceptance ? __("Accept") : __("Approve") }}
					</Button>
					<Button size="sm" theme="red" icon-left="lucide-x" @click="askReject(r)">
						{{ r.is_acceptance ? __("Decline") : __("Reject") }}
					</Button>
				</div>
			</template>
			<template #card="{ row: r }">
				<div class="hz-card space-y-2">
					<div class="flex items-center gap-2">
						<Badge :label="requestTypeLabel(r.request_type)" />
						<span class="font-semibold">{{ r.employee_name }}</span>
					</div>
					<p class="hz-num text-sm text-ink-gray-7">{{ requestSummary(r, leaveTypes) }}</p>
					<p v-if="r.reason" class="text-sm text-ink-gray-5">{{ r.reason }}</p>
					<p v-if="r.is_acceptance" class="text-xs text-ink-amber-7">
						{{ __("Your manager assigned this overtime; it needs your acceptance (Article 59).") }}
					</p>
					<div class="flex gap-2 pt-1">
						<Button
							variant="solid"
							theme="green"
							icon-left="lucide-check"
							:loading="busy === r.id + 'approve'"
							@click="act(r, 'approve')"
						>
							{{ r.is_acceptance ? __("Accept") : __("Approve") }}
						</Button>
						<Button theme="red" icon-left="lucide-x" @click="askReject(r)">
							{{ r.is_acceptance ? __("Decline") : __("Reject") }}
						</Button>
					</div>
				</div>
			</template>
		</DataTable>

		<Dialog v-model:open="rejectOpen" :title="__('Reject')">
			<Textarea v-model="comment" :label="__('Reason')" :rows="3" />
			<template #actions>
				<Button
					variant="solid"
					theme="red"
					:loading="!!busy"
					@click="rejecting && act(rejecting, 'reject', comment)"
				>
					{{ __("Reject") }}
				</Button>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, Dialog, ErrorMessage, Textarea, toast } from "frappe-ui"
import { onMounted, ref } from "vue"
import DataTable from "@/components/DataTable.vue"
import { api } from "@/lib/api"
import { refreshCounts } from "@/lib/counts"
import { requestSummary, requestTypeLabel } from "@/lib/format"
import { __ } from "@/lib/i18n"
import type { TableColumn } from "@/lib/table"
import type { LeaveType, RequestView } from "@/lib/types"

const rows = ref<RequestView[]>([])
const leaveTypes = ref<Record<number, string>>({})
const loading = ref(false)
const error = ref("")
const busy = ref("")
const rejectOpen = ref(false)
const rejecting = ref<RequestView | null>(null)
const comment = ref("")

const columns: TableColumn<RequestView>[] = [
	{ key: "employee_name", label: __("Employee"), class: "whitespace-nowrap font-medium" },
	{ key: "request_type", label: __("Type"), value: (r) => requestTypeLabel(r.request_type) },
	{ key: "start_jdate", label: __("From"), type: "date" },
	{ key: "end_jdate", label: __("Until"), type: "date" },
	{ key: "summary", label: __("Details"), value: (r) => requestSummary(r, leaveTypes.value), class: "hz-num" },
	{ key: "reason", label: __("Reason"), class: "text-ink-gray-6" },
	{ key: "actions", label: "", sortable: false, filterable: false },
]

async function load() {
	loading.value = true
	error.value = ""
	try {
		const [inbox, types] = await Promise.all([
			api.get<RequestView[]>("/inbox"),
			api.get<LeaveType[]>("/leave-types").catch(() => [] as LeaveType[]),
		])
		rows.value = inbox
		leaveTypes.value = Object.fromEntries(types.map((t) => [t.id, t.name]))
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

function askReject(r: RequestView) {
	rejecting.value = r
	comment.value = ""
	rejectOpen.value = true
}

async function act(r: RequestView, action: "approve" | "reject", text?: string) {
	busy.value = r.id + action
	try {
		await api.post(`/requests/${r.id}/${action}`, { comment: text?.trim() || null })
		if (action === "approve") toast.success(r.is_acceptance ? __("Accepted") : __("Approved"))
		else toast.success(r.is_acceptance ? __("Declined") : __("Rejected"))
		rejectOpen.value = false
		rows.value = rows.value.filter((x) => x.id !== r.id)
		refreshCounts(true)
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

onMounted(load)
</script>
