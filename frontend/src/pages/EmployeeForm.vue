<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="isNew ? __('New employee') : title" back="employees" />
		<ErrorMessage v-if="loadError" :message="loadError" />

		<form class="flex flex-col gap-4" @submit.prevent="save">
			<section class="hz-card flex flex-col gap-4">
				<h2 class="font-semibold">{{ __("Person") }}</h2>
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					<FieldInput v-for="f in personFields" :key="f.key" v-model="form[f.key]" :field="f" />
				</div>
			</section>

			<section class="hz-card flex flex-col gap-4">
				<h2 class="font-semibold">{{ __("Employment") }}</h2>
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					<FieldInput v-for="f in jobFields" :key="f.key" v-model="form[f.key]" :field="f" />
				</div>
				<template v-if="isNew">
					<h3 class="pt-2 text-sm font-semibold text-ink-gray-7">{{ __("First designation") }}</h3>
					<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
						<FieldInput v-model="first.designation_id" :field="firstDesignationField" />
						<JalaliDatePicker v-model="first.designation_from" :label="__('From')" />
					</div>
					<p class="text-xs text-ink-gray-5">
						{{ __("The designation decides who approves this person's requests. More can be given later.") }}
					</p>
				</template>
			</section>

			<section class="hz-card flex flex-col gap-4">
				<h2 class="font-semibold">{{ __("Login") }}</h2>
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					<TextInput
						v-model="login.username"
						dir="ltr"
						autocomplete="off"
						:label="__('Username')"
						:placeholder="isNew ? String(form.code ?? '') : undefined"
					/>
					<TextInput
						v-model="login.password"
						type="password"
						dir="ltr"
						autocomplete="new-password"
						:label="isNew ? __('Password') + ' *' : __('New password (leave empty to keep)')"
					/>
				</div>
				<p v-if="isNew" class="text-xs text-ink-gray-5">
					{{ __("The username is the personnel code unless you enter another. The password needs at least 8 characters.") }}
				</p>
				<Switch
					v-model="login.is_admin"
					:label="__('System admin')"
					:description="__('Can manage everything in the app')"
				/>
				<p class="text-xs text-ink-gray-5">{{ __("A person who left or is suspended can no longer log in.") }}</p>
			</section>

			<section class="hz-card flex flex-col gap-4">
				<h2 class="font-semibold">{{ __("Labor-law details") }}</h2>
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					<FieldInput v-for="f in lawFields" :key="f.key" v-model="form[f.key]" :field="f" />
				</div>
			</section>

			<ErrorMessage :message="error" />
			<Button type="submit" variant="solid" size="md" :loading="busy">{{ __("Save") }}</Button>
		</form>

		<!-- the designation history: give one, take one away -->
		<section v-if="!isNew" class="hz-card flex flex-col gap-3">
			<div class="flex items-center gap-2">
				<h2 class="flex-1 font-semibold">{{ __("Designations") }}</h2>
				<Button icon-left="lucide-plus" @click="giveOpen = true">{{ __("Give a designation") }}</Button>
			</div>
			<p v-if="!held.length" class="text-sm text-ink-gray-5">{{ __("No designation yet") }}</p>
			<ul class="divide-y divide-outline-gray-1">
				<li v-for="d in held" :key="d.assignment_id" class="flex flex-wrap items-center gap-2 py-2">
					<span class="font-medium" :class="d.current ? '' : 'text-ink-gray-5'">{{
						refLabel("designations", d.designation_id)
					}}</span>
					<Badge v-if="d.current" theme="green" :label="__('Current')" />
					<span class="hz-num flex-1 text-sm text-ink-gray-5">{{
						d.valid_to
							? __("From {0} to {1}", [display(d.valid_from), display(d.valid_to)])
							: __("From {0}", [display(d.valid_from)])
					}}</span>
					<Button v-if="d.current && !d.valid_to" size="sm" @click="askTake(d)">{{ __("Take away") }}</Button>
				</li>
			</ul>
		</section>

		<AssignmentDialog v-model:open="giveOpen" mode="give" :employee-id="id ?? null" @saved="load" />
		<AssignmentDialog
			v-model:open="takeOpen"
			mode="take"
			:assignment-id="taking?.assignment_id ?? null"
			:summary="taking ? refLabel('designations', taking.designation_id) : ''"
			@saved="load"
		/>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, ErrorMessage, Switch, TextInput, toast } from "frappe-ui"
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import AssignmentDialog from "@/components/AssignmentDialog.vue"
import FieldInput from "@/components/FieldInput.vue"
import JalaliDatePicker from "@/components/JalaliDatePicker.vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { display } from "@/lib/jalali"
import { employeeStatusOptions, type EmployeeRow, type HeldDesignation } from "@/lib/people"
import { invalidateRef, refLabel } from "@/lib/refs"
import type { FieldDef } from "@/lib/resources"
import { session } from "@/lib/session"

const props = defineProps<{ id?: number }>()
const router = useRouter()
const isNew = computed(() => !props.id)

const options = (pairs: [string, string][]) => () => pairs.map(([value, label]) => ({ value, label }))

const personFields: FieldDef[] = [
	{ key: "code", label: __("Personnel code"), type: "text", required: true, dir: "ltr" },
	{
		key: "detail_code",
		label: __("Detail code"),
		type: "text",
		dir: "ltr",
		help: __("The person's account code in the accounting books"),
	},
	{ key: "first_name", label: __("First name"), type: "text", required: true },
	{ key: "last_name", label: __("Last name"), type: "text", required: true },
	{ key: "national_id", label: __("National code"), type: "text", dir: "ltr" },
	{
		key: "gender",
		label: __("Gender"),
		type: "select",
		options: options([
			["male", __("Male")],
			["female", __("Female")],
		]),
	},
	{ key: "birth_date", label: __("Birth date"), type: "jdate", help: __("Only for young-worker rules") },
	{ key: "mobile", label: __("Mobile"), type: "text", dir: "ltr" },
	{ key: "email", label: __("Email"), type: "text", dir: "ltr" },
]
const jobFields: FieldDef[] = [
	{ key: "status", label: __("Status"), type: "select", required: true, options: employeeStatusOptions },
	{
		key: "contract_type",
		label: __("Contract"),
		type: "select",
		required: true,
		options: options([
			["full_time", __("Full time")],
			["part_time", __("Part time")],
			["hourly", __("Hourly")],
		]),
	},
	{ key: "start_date", label: __("Start date"), type: "jdate", required: true },
	{ key: "end_date", label: __("End date"), type: "jdate" },
	{ key: "work_location_id", label: __("Work location"), type: "ref", ref: "work-locations" },
	{ key: "department_id", label: __("Department"), type: "ref", ref: "departments" },
]
const lawFields: FieldDef[] = [
	{
		key: "overtime_consent_on_file",
		label: __("Written overtime consent on file"),
		type: "bool",
		help: __("Article 59"),
	},
	{ key: "overtime_consent_date", label: __("Overtime consent date"), type: "jdate" },
	{
		key: "biometric_consent_date",
		label: __("Biometric consent date"),
		type: "jdate",
		help: __("Written consent is needed before enrolling face or fingerprint"),
	},
	{ key: "uses_card_instead_of_biometrics", label: __("Uses a card instead of biometrics"), type: "bool" },
	{ key: "nursing_until", label: __("Nursing breaks until"), type: "jdate", help: __("Article 78") },
]
const firstDesignationField: FieldDef = {
	key: "designation_id",
	label: __("Designation"),
	type: "ref",
	ref: "designations",
}

const FIELDS = [...personFields, ...jobFields, ...lawFields].map((f) => f.key)

function blank(): Record<string, unknown> {
	return {
		status: "active",
		contract_type: "full_time",
		start_date: session.today,
		overtime_consent_on_file: false,
		uses_card_instead_of_biometrics: false,
	}
}

const form = reactive<Record<string, unknown>>(blank())
const login = reactive({ username: "", password: "", is_admin: false })
const first = reactive({ designation_id: null as number | null, designation_from: session.today as string | null })
const title = ref("")
const held = ref<HeldDesignation[]>([])
const error = ref("")
const loadError = ref("")
const busy = ref(false)

const giveOpen = ref(false)
const takeOpen = ref(false)
const taking = ref<HeldDesignation | null>(null)

function askTake(d: HeldDesignation) {
	taking.value = d
	takeOpen.value = true
}

function fill(e: EmployeeRow) {
	const values = e as unknown as Record<string, unknown>
	for (const key of FIELDS) form[key] = values[key] ?? null
	Object.assign(login, { username: e.username, password: "", is_admin: e.is_admin })
	title.value = e.full_name
	held.value = e.designations
}

async function load() {
	loadError.value = ""
	if (!props.id) {
		for (const key of Object.keys(form)) delete form[key]
		Object.assign(form, blank())
		Object.assign(login, { username: "", password: "", is_admin: false })
		Object.assign(first, { designation_id: null, designation_from: session.today })
		held.value = []
		return
	}
	try {
		fill(await api.get<EmployeeRow>(`/admin/employees/${props.id}`))
		invalidateRef("employees")
	} catch (e) {
		loadError.value = (e as Error).message
	}
}

function body(): Record<string, unknown> {
	const out: Record<string, unknown> = {}
	for (const key of FIELDS) {
		const value = form[key]
		out[key] = value === "" ? null : value
	}
	if (login.username) out.username = login.username
	if (login.password) out.password = login.password
	out.is_admin = login.is_admin
	if (isNew.value && first.designation_id) {
		out.designation_id = first.designation_id
		out.designation_from = first.designation_from || form.start_date
	}
	return out
}

async function save() {
	busy.value = true
	error.value = ""
	try {
		if (props.id) {
			fill(await api.patch<EmployeeRow>(`/admin/employees/${props.id}`, body()))
			toast.success(__("Saved"))
		} else {
			const created = await api.post<EmployeeRow>("/admin/employees", body())
			toast.success(__("Saved"))
			invalidateRef("employees")
			router.replace({ name: "employee", params: { id: created.id } })
			return
		}
		invalidateRef("employees")
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = false
	}
}

watch(() => props.id, load)
onMounted(load)
</script>
