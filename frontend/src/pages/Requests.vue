<template>
	<div class="space-y-4">
		<div class="flex items-center gap-2">
			<h1 class="flex-1 text-lg font-bold">{{ __("My requests") }}</h1>
			<Button variant="solid" icon-left="lucide-plus" :route="{ name: 'new-request' }">{{
				__("New request")
			}}</Button>
		</div>

		<EmployeePicker
			v-if="session.is_operator || session.is_manager"
			v-model="employee"
			:label="__('Employee')"
			:placeholder="session.employee ? undefined : __('Choose an employee')"
		/>

		<ErrorMessage v-if="error" :message="error" />
		<p v-if="loading" class="text-center text-sm text-ink-gray-5">{{ __("Loading...") }}</p>
		<p v-else-if="!rows.length && employee" class="hz-card text-center text-sm text-ink-gray-5">
			{{ __("No requests yet") }}
		</p>

		<ul class="space-y-2">
			<li v-for="r in rows" :key="r.id" class="hz-card !p-3">
				<div class="flex items-center gap-2">
					<span class="font-medium">{{ requestTypeLabel(r.request_type) }}</span>
					<span class="hz-num text-xs text-ink-gray-5" dir="ltr">{{ fa(r.number) }}</span>
					<span class="flex-1" />
					<StatusBadge :status="r.status" />
				</div>
				<p class="hz-num mt-1 text-sm text-ink-gray-6">{{ requestSummary(r, leaveTypes) }}</p>
				<p v-if="r.status === 'pending' && r.waiting_for" class="mt-1 text-xs text-ink-gray-5">
					{{ __("Waiting for {0}", [r.waiting_for]) }}
				</p>
				<p v-if="rejection(r)" class="mt-1 text-xs text-ink-red-6">{{ rejection(r) }}</p>
				<div v-if="canCancel(r)" class="mt-2">
					<Button size="sm" icon-left="lucide-undo-2" :loading="busy === r.id" @click="cancel(r)">
						{{ __("Withdraw") }}
					</Button>
				</div>
			</li>
		</ul>
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, toast } from "frappe-ui"
import { onMounted, ref, watch } from "vue"
import EmployeePicker from "@/components/EmployeePicker.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { api } from "@/lib/api"
import { requestSummary, requestTypeLabel } from "@/lib/format"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import { session } from "@/lib/session"
import type { LeaveType, RequestView } from "@/lib/types"

const employee = ref<number | null>(session.employee?.id ?? null)
const rows = ref<RequestView[]>([])
const leaveTypes = ref<Record<number, string>>({})
const loading = ref(false)
const error = ref("")
const busy = ref<number | null>(null)

async function load() {
	rows.value = []
	if (!employee.value) return
	loading.value = true
	error.value = ""
	try {
		rows.value = await api.get<RequestView[]>("/requests", { employee_id: employee.value, limit: 100 })
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

function rejection(r: RequestView): string {
	if (r.status !== "rejected") return ""
	const step = r.approvals.find((a) => a.status === "rejected")
	return step?.comment ? __("Rejected: {0}", [step.comment]) : ""
}

// people withdraw their own pending requests; cancelling anything else is an operator's job
function canCancel(r: RequestView) {
	return r.status === "pending" && r.employee_id === session.employee?.id
}

async function cancel(r: RequestView) {
	busy.value = r.id
	try {
		const updated = await api.post<RequestView>(`/requests/${r.id}/cancel`, { reason: null })
		rows.value = rows.value.map((x) => (x.id === r.id ? updated : x))
		toast.success(__("Request withdrawn"))
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = null
	}
}

onMounted(async () => {
	try {
		const types = await api.get<LeaveType[]>("/leave-types")
		leaveTypes.value = Object.fromEntries(types.map((t) => [t.id, t.name]))
	} catch {
		// the summary falls back to "Daily Leave" / "Hourly Leave"
	}
})

watch(employee, load, { immediate: true })
</script>
