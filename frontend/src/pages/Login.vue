<template>
	<div class="flex min-h-screen items-center justify-center bg-surface-gray-1 px-4">
		<form class="w-full max-w-sm rounded-8 bg-surface-base p-6 shadow-sm" @submit.prevent="submit">
			<div class="mb-6 flex items-center gap-3">
				<span class="hz-brand flex size-10 items-center justify-center rounded-4 text-xl font-bold">ح</span>
				<div>
					<h1 class="text-lg font-semibold">{{ __("Hozur") }}</h1>
					<p class="text-sm text-ink-gray-5">{{ __("Attendance") }}</p>
				</div>
			</div>
			<div class="flex flex-col gap-4">
				<TextInput v-model="username" :label="__('Username')" autocomplete="username" dir="ltr" required />
				<TextInput
					v-model="password"
					:label="__('Password')"
					type="password"
					autocomplete="current-password"
					dir="ltr"
					required
				/>
				<ErrorMessage :message="error" />
				<Button variant="solid" type="submit" :loading="busy" class="w-full">{{ __("Log in") }}</Button>
			</div>
		</form>
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, TextInput } from "frappe-ui"
import { ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { login } from "@/lib/session"

const route = useRoute()
const router = useRouter()
const username = ref("")
const password = ref("")
const error = ref("")
const busy = ref(false)

async function submit() {
	busy.value = true
	error.value = ""
	try {
		await login(username.value, password.value)
		const next = typeof route.query.next === "string" && route.query.next.startsWith("/") ? route.query.next : "/"
		await router.replace(next)
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = false
	}
}
</script>
