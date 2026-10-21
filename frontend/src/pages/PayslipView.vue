<template>
	<div class="flex min-h-screen items-center justify-center bg-surface-gray-1 px-4">
		<div class="w-full max-w-sm rounded-8 bg-surface-base p-6 text-center shadow-sm">
			<div class="mb-5 flex flex-col items-center gap-2">
				<span class="hz-brand flex size-10 items-center justify-center rounded-4 text-xl font-bold">C</span>
				<p class="text-sm text-ink-gray-5">{{ info?.organization || __("Chronicle") }}</p>
			</div>
			<p v-if="loading" class="text-sm text-ink-gray-5">{{ __("Loading...") }}</p>
			<template v-else-if="!info">
				<h1 class="mb-2 text-lg font-semibold">{{ __("Payslip") }}</h1>
				<ErrorMessage :message="error" />
			</template>
			<form v-else class="flex flex-col gap-4" @submit.prevent="open">
				<h1 class="text-lg font-semibold">{{ __("Payslip {0}", [info.month_label]) }}</h1>
				<p class="text-sm text-ink-gray-6">{{ __("To see your payslip, enter the last 4 digits of your national id.") }}</p>
				<TextInput
					v-model="secret"
					type="password"
					inputmode="numeric"
					maxlength="4"
					autocomplete="off"
					dir="ltr"
					placeholder="••••"
					required
				/>
				<ErrorMessage :message="error" />
				<Button variant="solid" type="submit" :loading="busy" class="w-full">{{ __("See the payslip") }}</Button>
				<p class="text-xs text-ink-gray-5">{{ __("This page is confidential; do not share your link with anyone.") }}</p>
			</form>
		</div>
	</div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, TextInput } from "frappe-ui"
import { onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"

const route = useRoute()
const token = String(route.params.token ?? "")
const info = ref<{ month_label: string; organization: string } | null>(null)
const secret = ref("")
const error = ref("")
const loading = ref(true)
const busy = ref(false)

onMounted(async () => {
	try {
		info.value = await api.get(`/payslip-link/${encodeURIComponent(token)}`)
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
})

async function open() {
	busy.value = true
	error.value = ""
	try {
		const pdf = await api.post<Blob>(`/payslip-link/${encodeURIComponent(token)}`, { secret: secret.value })
		// the PDF opens in the browser's own viewer; nothing is kept on the server side of the page
		window.location.href = URL.createObjectURL(new Blob([pdf], { type: "application/pdf" }))
	} catch (e) {
		error.value = (e as Error).message
		secret.value = ""
	} finally {
		busy.value = false
	}
}
</script>
