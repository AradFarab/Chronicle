<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Users and roles')" back="manage">
			<Button variant="solid" icon-left="lucide-plus" @click="edit(null)">{{ __("New") }}</Button>
		</PageHeader>
		<ErrorMessage :message="error" />
		<div class="overflow-x-auto rounded-6 border border-outline-gray-1 bg-surface-base">
			<table class="w-full text-sm">
				<thead class="bg-surface-gray-1 text-ink-gray-5">
					<tr>
						<th class="px-3 py-2 text-start font-medium">{{ __("Username") }}</th>
						<th class="px-3 py-2 text-start font-medium">{{ __("Name") }}</th>
						<th class="px-3 py-2 text-start font-medium">{{ __("Roles") }}</th>
						<th class="px-3 py-2 text-start font-medium">{{ __("Last login") }}</th>
					</tr>
				</thead>
				<tbody>
					<tr
						v-for="u in users"
						:key="u.id"
						class="cursor-pointer border-t border-outline-gray-1 hover:bg-surface-gray-1"
						:class="u.is_active ? '' : 'text-ink-gray-4'"
						@click="edit(u)"
					>
						<td class="px-3 py-2" dir="ltr">{{ u.username }}</td>
						<td class="px-3 py-2">{{ u.full_name }}</td>
						<td class="px-3 py-2">{{ u.roles.map(roleLabel).join("، ") }}</td>
						<td class="hz-num px-3 py-2">{{ fa(u.last_login_at ?? "") }}</td>
					</tr>
				</tbody>
			</table>
		</div>

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
				<Combobox
					v-if="!current"
					v-model="form.employee_id"
					:label="__('Employee record')"
					:options="refOptions('employees')"
				/>
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
import { Button, Combobox, Dialog, ErrorMessage, Switch, TextInput, toast } from "frappe-ui"
import { onMounted, reactive, ref } from "vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import { refOptions } from "@/lib/refs"

interface User {
	id: number
	username: string
	full_name: string
	is_active: boolean
	roles: string[]
	employee_id: number | null
	last_login_at: string | null
}

const ROLES = ["employee", "manager", "ceo", "operator", "admin"]

function roleLabel(role: string) {
	return (
		{
			employee: __("Employee"),
			manager: __("Manager"),
			ceo: __("CEO"),
			operator: __("Operator"),
			admin: __("System admin"),
		}[role] ?? role
	)
}

const users = ref<User[]>([])
const error = ref("")
const open = ref(false)
const current = ref<User | null>(null)
const busy = ref(false)
const formError = ref("")
const form = reactive({
	username: "",
	full_name: "",
	roles: [] as string[],
	employee_id: null as number | null,
	is_active: true,
	password: "",
})

async function load() {
	try {
		users.value = await api.get<User[]>("/admin/users")
	} catch (e) {
		error.value = (e as Error).message
	}
}

function edit(u: User | null) {
	current.value = u
	formError.value = ""
	Object.assign(form, {
		username: u?.username ?? "",
		full_name: u?.full_name ?? "",
		roles: [...(u?.roles ?? ["employee"])],
		employee_id: u?.employee_id ?? null,
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
				employee_id: form.employee_id,
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
