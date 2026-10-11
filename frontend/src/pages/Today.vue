<template>
	<div class="space-y-4">
		<section class="hz-brand rounded-7 p-5">
			<p class="text-sm opacity-80">{{ __("Today") }}</p>
			<p class="mt-1 text-xl font-bold">{{ displayLong(jdate) }}</p>
			<p v-if="session.employee" class="mt-2 text-sm opacity-90">{{ session.employee.full_name }}</p>
		</section>

		<div v-if="!session.employee" class="hz-card space-y-3">
			<p class="text-ink-gray-7">{{ __("Your user is not linked to an employee") }}</p>
			<Button
				v-if="session.is_admin"
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
						<StatusBadge v-else :status="data.attendance?.status || 'absent'" />
						<span v-if="data.schedule.shift" class="text-sm text-ink-gray-5">{{ data.schedule.shift }}</span>
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

				<section v-if="suggestions.length" class="hz-card space-y-3">
					<div>
						<h2 class="flex items-center gap-2 font-semibold">
							<span class="lucide-lightbulb size-4 text-ink-amber-6" />{{ __("Suggested requests") }}
						</h2>
						<p class="text-xs text-ink-gray-5">
							{{ __("From your punches and your shift. Nothing is sent unless you send it.") }}
						</p>
					</div>
					<ul class="divide-y divide-outline-gray-1">
						<li
							v-for="s in suggestions"
							:key="s.id"
							class="flex flex-wrap items-center gap-x-3 gap-y-2 py-2.5 first:pt-0 last:pb-0"
						>
							<span :class="suggestionIcon(s)" class="size-4 shrink-0 text-ink-gray-5" />
							<span class="hz-num min-w-0 flex-1 text-sm">{{ describe(s) }}</span>
							<span class="flex gap-2">
								<Button size="sm" variant="solid" icon-left="lucide-send" :route="sendRoute(s)">{{
									__("Send")
								}}</Button>
								<Button size="sm" :loading="dismissing === s.id" @click="dismiss(s)">{{ __("Dismiss") }}</Button>
							</span>
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
								query: { date: jdate },
							}"
						>
							{{ __("Manual entry") }}
						</Button>
					</div>
					<PunchList :punches="punches" />
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
						<p class="hz-num mt-1 text-2xl font-bold">{{ fa(counts.approvals) }}</p>
						<span class="mt-2 inline-block text-sm text-ink-blue-link">{{ __("Approvals") }}</span>
					</RouterLink>
				</section>
			</template>
		</template>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, ErrorMessage, toast } from "frappe-ui"
import { computed, onMounted, ref } from "vue"
import type { RouteLocationRaw } from "vue-router"
import DayNumbers from "@/components/DayNumbers.vue"
import PunchList from "@/components/PunchList.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { api } from "@/lib/api"
import { counts, refreshCounts } from "@/lib/counts"
import { countedPunches, dayPunches } from "@/lib/format"
import { __ } from "@/lib/i18n"
import { displayLong, fa } from "@/lib/jalali"
import { session } from "@/lib/session"
import type { DayDetails, Suggestion } from "@/lib/types"
import { warningMessages } from "@/lib/warnings"

const jdate = computed(() => session.today)
const data = ref<DayDetails | null>(null)
const leaveBalance = ref<number | null>(null)
const loading = ref(false)
const error = ref("")

const punches = computed(() => dayPunches(data.value))
const warnings = computed(() => warningMessages(data.value?.attendance?.warnings))
// Before the last punch of today the engine sees an unpaired punch; show the day as running.
const inProgress = computed(() => !!data.value && countedPunches(data.value).length % 2 === 1)
// while the day runs, the first punch is the arrival even before it has a pair
const attendance = computed(() => {
	const a = data.value?.attendance
	if (!a || !inProgress.value || a.first_in) return a
	return { ...a, first_in: countedPunches(data.value)[0]?.time?.slice(0, 5) ?? null }
})
const suggestions = ref<Suggestion[]>([])
const dismissing = ref<number | null>(null)
const balance = computed(() => (leaveBalance.value == null ? "—" : fa(Number(leaveBalance.value.toFixed(2)))))

async function load() {
	if (!session.employee) return
	loading.value = true
	error.value = ""
	try {
		const [day, earned] = await Promise.all([
			api.get<DayDetails>("/attendance/day", { employee_id: session.employee.id, jdate: jdate.value }),
			api.get<{ balance: number | null }>("/leave/balance", { employee_id: session.employee.id }),
			refreshCounts(true),
		])
		data.value = day
		leaveBalance.value = earned.balance
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
	loadSuggestions()
}

// requests the calculation proposes; the card is simply left out if they cannot be loaded
async function loadSuggestions() {
	try {
		suggestions.value = await api.get<Suggestion[]>("/suggestions")
	} catch {
		suggestions.value = []
	}
}

function describe(s: Suggestion): string {
	const day = displayLong(s.jdate)
	const range = !!(s.from_time && s.to_time)
	if (s.request_type === "overtime")
		return fa(
			range
				? __("Overtime {0} to {1} ({2} minutes) on {3}", [s.from_time!, s.to_time!, s.minutes, day])
				: __("Overtime of {0} minutes on {1}", [s.minutes, day])
		)
	if (s.request_type === "hourly_leave")
		return fa(
			range
				? __("Hourly leave {0} to {1} ({2} minutes) on {3}", [s.from_time!, s.to_time!, s.minutes, day])
				: __("Hourly leave of {0} minutes on {1}", [s.minutes, day])
		)
	return __("A punch is missing on {0}: add the time the device missed", [day])
}

function suggestionIcon(s: Suggestion): string {
	if (s.request_type === "overtime") return "lucide-clock-arrow-up"
	if (s.request_type === "hourly_leave") return "lucide-clock-alert"
	return "lucide-fingerprint"
}

function sendRoute(s: Suggestion): RouteLocationRaw {
	const query: Record<string, string> = { jdate: s.jdate, suggestion_id: String(s.id) }
	if (s.from_time) query.from_time = s.from_time
	if (s.to_time) query.to_time = s.to_time
	if (s.minutes) query.minutes = String(s.minutes)
	if (s.request_type === "overtime") return { name: "new-request", params: { kind: "overtime" }, query }
	if (s.request_type === "hourly_leave")
		return { name: "new-request", params: { kind: "leave" }, query: { ...query, unit: "hourly" } }
	return { name: "new-request", params: { kind: "correction" }, query: { jdate: s.jdate, suggestion_id: String(s.id) } }
}

async function dismiss(s: Suggestion) {
	dismissing.value = s.id
	try {
		await api.post(`/suggestions/${s.id}/dismiss`)
		suggestions.value = suggestions.value.filter((x) => x.id !== s.id)
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		dismissing.value = null
	}
}

onMounted(load)
</script>
