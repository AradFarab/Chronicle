<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Delegation of approvals')">
			<Button variant="solid" icon-left="lucide-plus" @click="add">{{ __("New") }}</Button>
		</PageHeader>
		<p class="text-sm text-ink-gray-6">
			{{
				__(
					"Hand your approvals to another person for a period. Both of you can then approve the requests that wait for you."
				)
			}}
		</p>
		<ErrorMessage :message="error" />
		<DataTable :columns="columns" :rows="rows" :loading="loading" storage-key="delegations">
			<template #empty>{{ __("No delegation yet") }}</template>
			<template #cell-state="{ row: d, text }">
				<Badge :theme="d.current ? 'green' : 'gray'" :label="text" />
			</template>
			<template #cell-actions="{ row: d }">
				<Button
					v-if="canRemove(d)"
					size="sm"
					theme="red"
					icon-left="lucide-trash-2"
					:loading="busy === d.id"
					@click="remove(d)"
					>{{ d.current ? __("End") : __("Delete") }}</Button
				>
			</template>
			<template #card="{ row: d }">
				<div class="hz-card flex flex-col gap-1 !p-3">
					<div class="flex flex-wrap items-center gap-2">
						<span class="font-medium">{{ d.delegator_name }}</span>
						<span class="lucide-arrow-left size-4 text-ink-gray-5" />
						<span class="font-medium">{{ d.delegate_name }}</span>
						<Badge :theme="d.current ? 'green' : 'gray'" :label="stateLabel(d)" />
						<span class="flex-1" />
						<Button
							v-if="canRemove(d)"
							size="sm"
							theme="red"
							icon-left="lucide-trash-2"
							:loading="busy === d.id"
							@click="remove(d)"
							>{{ d.current ? __("End") : __("Delete") }}</Button
						>
					</div>
					<p class="hz-num text-sm text-ink-gray-6">
						{{ d.valid_to ? __("From {0} to {1}", [display(d.valid_from), display(d.valid_to)]) : __("From {0}", [display(d.valid_from)]) }}
					</p>
					<p v-if="d.note" class="text-sm text-ink-gray-5">{{ d.note }}</p>
				</div>
			</template>
		</DataTable>

		<Dialog v-model:open="open" :title="__('New delegation')">
			<div class="flex flex-col gap-4">
				<Combobox
					v-if="session.is_admin"
					v-model="form.delegator_id"
					:label="__('Whose approvals')"
					:options="refOptions('employees')"
					:placeholder="session.employee ? __('Myself') : __('Choose')"
				/>
				<EmployeePicker
					v-model="form.delegate_id"
					everyone
					:exclude="form.delegator_id ?? session.employee?.id"
					:label="__('Hand the approvals to') + ' *'"
					:placeholder="__('Choose')"
				/>
				<JalaliDatePicker v-model="form.valid_from" :label="__('From')" />
				<JalaliDatePicker v-model="form.valid_to" :label="__('Until')" />
				<Textarea v-model="form.note" :label="__('Note')" :rows="2" />
				<ErrorMessage :message="formError" />
			</div>
			<template #actions>
				<Button variant="solid" :loading="busy === 'save'" @click="save">{{ __("Save") }}</Button>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, Combobox, Dialog, ErrorMessage, Textarea, toast } from "frappe-ui"
import { onMounted, reactive, ref } from "vue"
import DataTable from "@/components/DataTable.vue"
import EmployeePicker from "@/components/EmployeePicker.vue"
import JalaliDatePicker from "@/components/JalaliDatePicker.vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { display } from "@/lib/jalali"
import { refOptions } from "@/lib/refs"
import { session } from "@/lib/session"
import type { TableColumn } from "@/lib/table"

interface Delegation {
	id: number
	delegator_id: number
	delegator_name: string | null
	delegate_id: number
	delegate_name: string | null
	valid_from: string
	valid_to: string | null
	note: string | null
	current: boolean
}

const rows = ref<Delegation[]>([])
const loading = ref(false)
const error = ref("")
const open = ref(false)
const formError = ref("")
const busy = ref<string | number>("")
const form = reactive({
	delegator_id: null as number | null,
	delegate_id: null as number | null,
	valid_from: null as string | null,
	valid_to: null as string | null,
	note: "",
})

function stateLabel(d: Delegation) {
	if (d.current) return __("Current")
	return d.valid_from > session.today ? __("Not started") : __("Ended")
}

const columns: TableColumn<Delegation>[] = [
	{ key: "delegator_name", label: __("Whose approvals") },
	{ key: "delegate_name", label: __("Handed to") },
	{ key: "valid_from", label: __("From"), type: "date" },
	{ key: "valid_to", label: __("Until"), type: "date" },
	{ key: "state", label: __("State"), value: stateLabel },
	{ key: "note", label: __("Note"), class: "min-w-48" },
	{ key: "actions", label: "", sortable: false, filterable: false },
]

// you can end the delegations you gave; the system admin can end any
const canRemove = (d: Delegation) => session.is_admin || d.delegator_id === session.employee?.id

async function load() {
	loading.value = true
	error.value = ""
	try {
		rows.value = await api.get<Delegation[]>("/delegations")
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

function add() {
	formError.value = ""
	Object.assign(form, { delegator_id: null, delegate_id: null, valid_from: session.today, valid_to: null, note: "" })
	open.value = true
}

async function save() {
	formError.value = ""
	if (!form.delegate_id) {
		formError.value = __("Choose the person who gets the approvals")
		return
	}
	busy.value = "save"
	try {
		await api.post("/delegations", {
			delegate_id: form.delegate_id,
			valid_from: form.valid_from,
			valid_to: form.valid_to,
			note: form.note || null,
			...(session.is_admin && form.delegator_id ? { delegator_id: form.delegator_id } : {}),
		})
		toast.success(__("Saved"))
		open.value = false
		load()
	} catch (e) {
		formError.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

async function remove(d: Delegation) {
	if (!window.confirm(d.current ? __("End this delegation?") : __("Delete this record?"))) return
	busy.value = d.id
	try {
		await api.del(`/delegations/${d.id}`)
		toast.success(__("Deleted"))
		load()
	} catch (e) {
		toast.error((e as Error).message)
	} finally {
		busy.value = ""
	}
}

onMounted(load)
</script>
