<template>
	<Button icon-left="lucide-file-spreadsheet" @click="show">{{ __("Import from Excel") }}</Button>
	<Dialog v-model:open="open" :title="__('Import from Excel')">
		<div class="flex flex-col gap-4">
			<ol class="list-decimal space-y-1 ps-5 text-sm text-ink-gray-6">
				<li>{{ __("Download the sample and fill it in, one row for each record.") }}</li>
				<li>{{ __("Choose the filled file and upload it.") }}</li>
				<li>{{ __("If any row is wrong, nothing is saved and the wrong rows are listed.") }}</li>
			</ol>
			<div>
				<Button icon-left="lucide-download" :loading="busy === 'sample'" @click="sample">{{
					__("Download the sample")
				}}</Button>
			</div>
			<input
				ref="fileInput"
				type="file"
				accept=".xlsx"
				class="block w-full text-sm text-ink-gray-7 file:me-3 file:rounded-3 file:border-0 file:bg-surface-gray-2 file:px-3 file:py-1.5 file:text-ink-gray-8"
				@change="file = ($event.target as HTMLInputElement).files?.[0] ?? null"
			/>
			<ErrorMessage :message="error" />
			<p v-if="result?.imported" class="hz-num rounded-4 bg-surface-green-1 p-3 text-sm text-ink-green-7">
				{{ fa(__("{0} rows imported", [result.created])) }}
			</p>
			<div v-else-if="result" class="flex flex-col gap-1">
				<p class="text-sm font-medium text-ink-red-6">{{ __("Nothing was saved. Fix these rows and upload again.") }}</p>
				<ul class="hz-num max-h-60 overflow-y-auto rounded-4 bg-surface-red-1 p-3 text-sm text-ink-red-7">
					<li v-for="(e, i) in result.errors" :key="i">{{ fa(__("Row {0}: {1}", [e.row, e.message])) }}</li>
				</ul>
			</div>
		</div>
		<template #actions>
			<Button variant="solid" icon-left="lucide-upload" :disabled="!file" :loading="busy === 'upload'" @click="upload">{{
				__("Upload")
			}}</Button>
		</template>
	</Dialog>
</template>

<script setup lang="ts">
import { Button, Dialog, ErrorMessage } from "frappe-ui"
import { ref } from "vue"
import { api, downloadGet } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { fa } from "@/lib/jalali"
import { invalidateRef } from "@/lib/refs"

interface ImportResult {
	imported: boolean
	created: number
	errors: { row: number; message: string }[]
}

// `name` is the import spec (the same name as the admin resource: departments, shifts, ...)
const props = defineProps<{ name: string }>()
const emit = defineEmits<{ done: [] }>()

const open = ref(false)
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement>()
const busy = ref("")
const error = ref("")
const result = ref<ImportResult | null>(null)

function show() {
	file.value = null
	if (fileInput.value) fileInput.value.value = ""
	error.value = ""
	result.value = null
	open.value = true
}

async function sample() {
	busy.value = "sample"
	error.value = ""
	try {
		await downloadGet(`/import/${props.name}/template`)
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}

async function upload() {
	if (!file.value) return
	busy.value = "upload"
	error.value = ""
	result.value = null
	try {
		const data = new FormData()
		data.append("file", file.value)
		result.value = await api.upload<ImportResult>(`/import/${props.name}`, data)
		if (result.value.imported) {
			invalidateRef(props.name)
			emit("done")
		}
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		busy.value = ""
	}
}
</script>
