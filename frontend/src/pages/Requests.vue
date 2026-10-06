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
			<li v-for="r in rows" :key="r.doctype + r.name" class="hz-card !p-3">
				<div class="flex items-center gap-2">
					<span class="font-medium">{{ r.kind }}</span>
					<span class="flex-1" />
					<StatusBadge :status="r.status" :label="r.status_label" />
				</div>
				<p class="hz-num mt-1 text-sm text-ink-gray-6">{{ fa(r.summary) }}</p>
				<p v-if="r.waiting_for" class="mt-1 text-xs text-ink-gray-5">
					{{ __("Waiting for {0}", [r.waiting_for]) }}
				</p>
			</li>
		</ul>
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage } from "frappe-ui"
import { ref, watch } from "vue"
import EmployeePicker from "@/components/EmployeePicker.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { call } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import { session } from "@/lib/session"

interface Row {
	doctype: string
	kind: string
	name: string
	status: string
	status_label: string
	summary: string
	waiting_for: string | null
}

const employee = ref<string | null>(session.employee?.name ?? null)
const rows = ref<Row[]>([])
const loading = ref(false)
const error = ref("")

async function load() {
	rows.value = []
	if (!employee.value) return
	loading.value = true
	error.value = ""
	try {
		rows.value = await call<Row[]>("hozur.api.pwa.my_requests", { employee: employee.value })
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

watch(employee, load, { immediate: true })
</script>
