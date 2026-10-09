<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Company')" back="manage" />
		<form class="flex flex-col gap-4 rounded-6 border border-outline-gray-1 bg-surface-base p-4" @submit.prevent="save">
			<TextInput v-model="org.name" :label="__('Name') + ' *'" />
			<TextInput v-model="org.legal_name" :label="__('Registered name')" />
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
				<TextInput v-model="org.national_id" dir="ltr" :label="__('National id of the company')" />
				<TextInput v-model="org.economic_code" dir="ltr" :label="__('Economic code')" />
				<TextInput v-model="org.insurance_workshop_code" dir="ltr" :label="__('Insurance workshop code')" />
				<TextInput v-model="org.phone" dir="ltr" :label="__('Phone')" />
			</div>
			<Textarea v-model="org.address" :label="__('Address')" :rows="2" />
			<ErrorMessage :message="error" />
			<Button type="submit" variant="solid" :loading="busy">{{ __("Save") }}</Button>
		</form>
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, Textarea, TextInput, toast } from "frappe-ui"
import { onMounted, reactive, ref } from "vue"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { session } from "@/lib/session"

const org = reactive({
	name: "",
	legal_name: "",
	national_id: "",
	economic_code: "",
	insurance_workshop_code: "",
	phone: "",
	address: "",
})
const error = ref("")
const busy = ref(false)

onMounted(async () => {
	try {
		const data = await api.get<Record<string, unknown>>("/admin/organization")
		for (const key of Object.keys(org) as (keyof typeof org)[]) {
			if (data[key] !== undefined && data[key] !== null) (org as Record<string, unknown>)[key] = data[key]
		}
	} catch (e) {
		error.value = (e as Error).message
	}
})

async function save() {
	busy.value = true
	error.value = ""
	try {
		await api.put("/admin/organization", { ...org })
		session.organization = org.name
		toast.success(__("Saved"))
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = false
	}
}
</script>
