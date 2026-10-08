<template>
	<div class="space-y-4">
		<h1 class="text-lg font-bold">{{ __("Waiting for my approval") }}</h1>
		<ErrorMessage v-if="error" :message="error" />
		<p v-if="loading" class="text-center text-sm text-ink-gray-5">{{ __("Loading...") }}</p>
		<p v-else-if="!rows.length" class="hz-card text-center text-sm text-ink-gray-5">
			{{ __("Nothing is waiting for you") }}
		</p>

		<ul class="space-y-3">
			<li v-for="r in rows" :key="r.id" class="hz-card space-y-2">
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
			</li>
		</ul>

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
import { api } from "@/lib/api"
import { refreshCounts } from "@/lib/counts"
import { requestSummary, requestTypeLabel } from "@/lib/format"
import { __ } from "@/lib/i18n"
import type { LeaveType, RequestView } from "@/lib/types"

const rows = ref<RequestView[]>([])
const leaveTypes = ref<Record<number, string>>({})
const loading = ref(false)
const error = ref("")
const busy = ref("")
const rejectOpen = ref(false)
const rejecting = ref<RequestView | null>(null)
const comment = ref("")

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
