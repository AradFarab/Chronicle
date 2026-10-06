<template>
	<div class="space-y-4">
		<h1 class="text-lg font-bold">{{ __("Waiting for my approval") }}</h1>
		<ErrorMessage v-if="error" :message="error" />
		<p v-if="loading" class="text-center text-sm text-ink-gray-5">{{ __("Loading...") }}</p>
		<p v-else-if="!rows.length" class="hz-card text-center text-sm text-ink-gray-5">
			{{ __("Nothing is waiting for you") }}
		</p>

		<ul class="space-y-3">
			<li v-for="r in rows" :key="r.doctype + r.name" class="hz-card space-y-2">
				<div class="flex items-center gap-2">
					<Badge :label="r.kind" />
					<span class="font-semibold">{{ r.employee_name }}</span>
				</div>
				<p class="hz-num text-sm text-ink-gray-7">{{ fa(r.summary) }}</p>
				<p v-if="r.reason" class="text-sm text-ink-gray-5">{{ r.reason }}</p>
				<p v-if="r.acceptance" class="text-xs text-ink-amber-7">
					{{ __("Your manager assigned this overtime; it needs your acceptance (Article 59).") }}
				</p>
				<div class="flex gap-2 pt-1">
					<Button
						variant="solid"
						theme="green"
						icon-left="lucide-check"
						:loading="busy === r.name + 'Approve'"
						@click="act(r, 'Approve')"
					>
						{{ r.acceptance ? __("Accept") : __("Approve") }}
					</Button>
					<Button theme="red" icon-left="lucide-x" @click="askReject(r)">
						{{ r.acceptance ? __("Decline") : __("Reject") }}
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
					@click="rejecting && act(rejecting, 'Reject', comment)"
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
import { call } from "@/lib/api"
import { refreshCounts } from "@/lib/counts"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"

interface Row {
	doctype: string
	kind: string
	name: string
	employee_name: string
	summary: string
	reason: string | null
	acceptance: boolean
}

const rows = ref<Row[]>([])
const loading = ref(false)
const error = ref("")
const busy = ref("")
const rejectOpen = ref(false)
const rejecting = ref<Row | null>(null)
const comment = ref("")

async function load() {
	loading.value = true
	error.value = ""
	try {
		rows.value = await call<Row[]>("hozur.api.pwa.inbox")
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

function askReject(r: Row) {
	rejecting.value = r
	comment.value = ""
	rejectOpen.value = true
}

async function act(r: Row, action: "Approve" | "Reject", text?: string) {
	busy.value = r.name + action
	try {
		await call("hozur.approvals.act_on_request", {
			doctype: r.doctype,
			name: r.name,
			action,
			comment: text || null,
		})
		toast.success(action === "Approve" ? __("Approved") : __("Rejected"))
		rejectOpen.value = false
		rows.value = rows.value.filter((x) => x !== r)
		refreshCounts(true)
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

onMounted(load)
</script>
