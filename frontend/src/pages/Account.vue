<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Change password')" />
		<form class="flex flex-col gap-4 rounded-6 border border-outline-gray-1 bg-surface-base p-4" @submit.prevent="save">
			<TextInput
				v-model="current"
				type="password"
				dir="ltr"
				autocomplete="current-password"
				:label="__('Current password')"
			/>
			<TextInput v-model="next" type="password" dir="ltr" autocomplete="new-password" :label="__('New password')" />
			<TextInput
				v-model="again"
				type="password"
				dir="ltr"
				autocomplete="new-password"
				:label="__('New password again')"
			/>
			<p class="text-xs text-ink-gray-5">{{ __("Your other devices will be logged out.") }}</p>
			<ErrorMessage :message="error" />
			<Button type="submit" variant="solid" :loading="busy">{{ __("Save") }}</Button>
		</form>
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, TextInput, toast } from "frappe-ui"
import { ref } from "vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"

const current = ref("")
const next = ref("")
const again = ref("")
const error = ref("")
const busy = ref(false)

async function save() {
	error.value = ""
	if (next.value !== again.value) {
		error.value = __("The two new passwords are not the same")
		return
	}
	busy.value = true
	try {
		await api.post("/auth/password", { current_password: current.value, new_password: next.value })
		toast.success(__("Password changed"))
		current.value = next.value = again.value = ""
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = false
	}
}
</script>
