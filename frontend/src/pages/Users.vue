<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Users and roles')" back="manage">
			<Button variant="solid" icon-left="lucide-plus" @click="edit(null)">{{ __("New") }}</Button>
		</PageHeader>
		<p class="text-sm text-ink-gray-6">
			{{
				__(
					"Employees get their login when they are added in the Employees screen. Here you add a login without an employee record, such as one for IT staff."
				)
			}}
		</p>
		<ErrorMessage :message="error" />
		<DataTable
			:columns="columns"
			:rows="users"
			:loading="loading"
			:row-class="(u) => (u.is_active ? '' : 'text-ink-gray-4')"
			storage-key="users"
			@row-click="edit"
		>
			<template #cell-username="{ row }"><span dir="ltr">{{ row.username }}</span></template>
		</DataTable>

		<Dialog v-model:open="open" :title="current ? current.username : __('New user')">
			<div class="flex flex-col gap-4">
				<TextInput v-if="!current" v-model="form.username" dir="ltr" :label="__('Username')" />
				<TextInput v-model="form.full_name" :label="__('Full name')" />
				<div class="flex flex-col gap-2">
					<p class="text-sm">{{ __("Roles") }}</p>
					<label v-for="r in ROLES" :key="r" class="flex items-center gap-2 text-sm">
						<input v-model="form.roles" type="checkbox" :value="r" />{{ roleLabel(r) }}
					</label>
				</div>
				<Switch v-if="current" v-model="form.is_active" :label="__('Active')" />
				<TextInput
					v-model="form.password"
					type="password"
					dir="ltr"
					autocomplete="new-password"
					:label="current ? __('New password (leave empty to keep)') : __('Password')"
				/>
				<ErrorMessage :message="formError" />
			</div>
			<template #actions>
				<Button variant="solid" :loading="busy" @click="save">{{ __("Save") }}</Button>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { Button, Dialog, ErrorMessage, Switch, TextInput, toast } from "frappe-ui"
import { onMounted, reactive, ref } from "vue"
import DataTable from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import type { TableColumn } from "@/lib/table"

interface User {
	id: number
	username: string
	full_name: string
	is_active: boolean
	roles: string[]
	employee_id: number | null
	last_login_at: string | null
}

// only two roles are stored; managers and the CEO are derived from the designations people hold
const ROLES = ["admin", "employee"]

function roleLabel(role: string) {
	return (
		{
			employee: __("Employee"),
			admin: __("System admin"),
		}[role] ?? role
	)
}

const users = ref<User[]>([])
const loading = ref(false)
const error = ref("")

const columns: TableColumn<User>[] = [
	{ key: "username", label: __("Username") },
	{ key: "full_name", label: __("Name") },
	{ key: "roles", label: __("Roles"), value: (u) => u.roles.map(roleLabel).join("، ") },
	{ key: "is_active", label: __("Active"), type: "bool" },
	{ key: "last_login_at", label: __("Last login"), type: "date", format: (u) => fa(u.last_login_at ?? "") },
]
const open = ref(false)
const current = ref<User | null>(null)
const busy = ref(false)
const formError = ref("")
const form = reactive({
	username: "",
	full_name: "",
	roles: [] as string[],
	is_active: true,
	password: "",
})

async function load() {
	loading.value = true
	try {
		users.value = await api.get<User[]>("/admin/users")
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

function edit(u: User | null) {
	current.value = u
	formError.value = ""
	Object.assign(form, {
		username: u?.username ?? "",
		full_name: u?.full_name ?? "",
		roles: [...(u?.roles ?? ["admin"])],
		is_active: u?.is_active ?? true,
		password: "",
	})
	open.value = true
}

async function save() {
	busy.value = true
	formError.value = ""
	try {
		if (current.value) {
			await api.patch(`/admin/users/${current.value.id}`, {
				full_name: form.full_name,
				roles: form.roles,
				is_active: form.is_active,
			})
			if (form.password) await api.post(`/admin/users/${current.value.id}/password`, { password: form.password })
		} else {
			await api.post("/admin/users", {
				username: form.username,
				full_name: form.full_name,
				password: form.password,
				roles: form.roles,
			})
		}
		toast.success(__("Saved"))
		open.value = false
		load()
	} catch (e) {
		formError.value = (e as Error).message
	} finally {
		busy.value = false
	}
}

onMounted(load)
</script>
