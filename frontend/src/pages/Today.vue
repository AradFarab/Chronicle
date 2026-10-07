<template>
	<div class="space-y-4">
		<section class="hz-brand rounded-7 p-5">
			<p class="text-sm opacity-80">{{ __("Today") }}</p>
			<p class="mt-1 text-xl font-bold">{{ displayLong(data?.jdate || session.today) }}</p>
			<p v-if="session.employee" class="mt-2 text-sm opacity-90">{{ session.employee.full_name }}</p>
		</section>

		<div v-if="!session.employee" class="hz-card space-y-3">
			<p class="text-ink-gray-7">{{ __("Your user is not linked to an employee") }}</p>
			<Button
				v-if="session.is_operator"
				variant="solid"
				:route="{ name: 'devices' }"
				icon-left="lucide-fingerprint"
			>
				{{ __("Devices") }}
			</Button>
		</div>

		<template v-else>
			<ErrorMessage v-if="error" :message="error" />
			<div v-if="loading && !data" class="hz-card text-center text-ink-gray-5">{{ __("Loading...") }}</div>

			<template v-if="data">
				<section class="hz-card space-y-4">
					<div class="flex flex-wrap items-center gap-2">
						<Badge v-if="inProgress" theme="blue" :label="__('At work')" />
						<StatusBadge v-else :status="data.attendance?.status || 'Absent'" />
						<span v-if="data.attendance?.shift" class="text-sm text-ink-gray-5">{{
							data.attendance.shift
						}}</span>
						<span v-if="data.attendance?.holiday_title" class="text-sm text-ink-red-6">{{
							data.attendance.holiday_title
						}}</span>
						<span class="flex-1" />
						<button
							type="button"
							class="rounded-2 p-1 text-ink-gray-5 hover:bg-surface-gray-2"
							:aria-label="__('Refresh')"
							@click="load"
						>
							<span class="lucide-refresh-cw size-4" :class="loading ? 'animate-spin' : ''" />
						</button>
					</div>
					<DayNumbers v-if="attendance" :attendance="attendance" :in-progress="inProgress" />
					<p v-if="inProgress" class="text-xs text-ink-gray-5">
						{{ __("The day is not over; the numbers are final after your last punch.") }}
					</p>
					<ul v-if="warnings.length && !inProgress" class="space-y-1 text-sm text-ink-amber-7">
						<li v-for="w in warnings" :key="w" class="flex gap-2">
							<span class="lucide-triangle-alert mt-0.5 size-4 shrink-0" />{{ w }}
						</li>
					</ul>
				</section>

				<section class="hz-card">
					<div class="mb-2 flex items-center justify-between">
						<h2 class="font-semibold">{{ __("Today's punches") }}</h2>
						<Button
							size="sm"
							icon-left="lucide-plus"
							:route="{
								name: 'new-request',
								params: { kind: 'correction' },
								query: { date: data.jdate },
							}"
						>
							{{ __("Manual entry") }}
						</Button>
					</div>
					<PunchList :punches="data.punches" />
				</section>

				<section class="grid grid-cols-2 gap-4">
					<div class="hz-card">
						<p class="text-xs text-ink-gray-5">{{ __("Leave Balance (Days)") }}</p>
						<p class="hz-num mt-1 text-2xl font-bold">{{ balance }}</p>
						<RouterLink
							class="mt-2 inline-block text-sm text-ink-blue-link"
							:to="{ name: 'new-request', params: { kind: 'leave' } }"
							>{{ __("Request leave") }}</RouterLink
						>
					</div>
					<RouterLink :to="{ name: 'approvals' }" class="hz-card block">
						<p class="text-xs text-ink-gray-5">{{ __("Waiting for my approval") }}</p>
						<p class="hz-num mt-1 text-2xl font-bold">{{ fa(data.pending_approvals) }}</p>
						<span class="mt-2 inline-block text-sm text-ink-blue-link">{{ __("Approvals") }}</span>
					</RouterLink>
				</section>
			</template>
		</template>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, ErrorMessage } from "frappe-ui"
import { computed, onMounted, ref } from "vue"
import DayNumbers from "@/components/DayNumbers.vue"
import PunchList from "@/components/PunchList.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { call } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { displayLong, fa } from "@/lib/jalali"
import { session } from "@/lib/session"
import type { Attendance, Punch } from "@/lib/types"
import { warningMessages } from "@/lib/warnings"

interface TodayData {
	jdate: string
	time: string
	attendance: Attendance | null
	punches: Punch[]
	leave_balance: number | null
	pending_approvals: number
}

const data = ref<TodayData | null>(null)
const loading = ref(false)
const error = ref("")

const warnings = computed(() => warningMessages(data.value?.attendance?.warnings))
// Before the last punch of today the engine sees an unpaired punch; show the day as running.
const inProgress = computed(
	() => !!data.value && data.value.jdate === session.today && data.value.punches.length % 2 === 1
)
// while the day runs, the first punch is the arrival even before it has a pair
const attendance = computed(() => {
	const a = data.value?.attendance
	if (!a || !inProgress.value || a.first_in) return a
	return { ...a, first_in: data.value!.punches[0]?.time?.slice(0, 5) ?? null }
})
const balance = computed(() =>
	data.value?.leave_balance == null ? "—" : fa(Number(data.value.leave_balance.toFixed(2)))
)

async function load() {
	if (!session.employee) return
	loading.value = true
	error.value = ""
	try {
		data.value = await call<TodayData>("hozur.api.pwa.today")
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
