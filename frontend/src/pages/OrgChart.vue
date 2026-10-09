<template>
	<div class="flex flex-col gap-4">
		<PageHeader :title="__('Organization chart')" back="manage">
			<Button icon-left="lucide-plus" @click="addChild(null)">{{ __("New top designation") }}</Button>
		</PageHeader>
		<p class="text-sm text-ink-gray-6">
			{{
				__(
					"Designations form a tree. Whoever holds the designation above approves the requests of the people below. Several people may hold one designation."
				)
			}}
		</p>
		<ErrorMessage :message="error" />
		<p v-if="!loading && !nodes.length" class="hz-card text-center text-sm text-ink-gray-5">{{ __("Nothing here yet") }}</p>

		<ul class="flex flex-col gap-2">
			<li v-for="n in nodes" :key="n.id" :style="{ marginInlineStart: `${n.depth * 1.5}rem` }">
				<div class="hz-card flex flex-col gap-2 !p-3" :class="n.depth ? 'border-s-4 border-s-outline-gray-3' : ''">
					<div class="flex flex-wrap items-center gap-2">
						<button
							v-if="n.hasChildren"
							type="button"
							class="rounded-2 p-0.5 hover:bg-surface-gray-2"
							:aria-label="collapsed.has(n.id) ? __('Expand') : __('Collapse')"
							@click="toggle(n.id)"
						>
							<span :class="collapsed.has(n.id) ? 'lucide-chevron-left' : 'lucide-chevron-down'" class="size-4" />
						</button>
						<button type="button" class="font-semibold hover:underline" @click="edit(n.row)">{{ n.row.name }}</button>
						<Badge v-if="n.row.is_ceo" theme="blue" :label="__('CEO')" />
						<Badge v-if="n.row.hard_and_harmful" theme="amber" :label="__('Hard and harmful work')" />
						<span class="flex-1" />
						<Button size="sm" icon-left="lucide-user-plus" @click="give(n.row)">{{ __("Give to someone") }}</Button>
						<Button size="sm" icon-left="lucide-plus" @click="addChild(n.row)">{{ __("Add a child") }}</Button>
					</div>
					<div class="flex flex-wrap items-center gap-2">
						<span
							v-for="h in n.holders"
							:key="h.assignment_id"
							class="inline-flex items-center gap-1 rounded-full bg-surface-gray-2 py-0.5 ps-3 pe-1 text-sm"
							:class="h.active ? '' : 'text-ink-gray-4'"
						>
							{{ h.name }}
							<span v-if="h.valid_to" class="hz-num text-xs text-ink-gray-5">{{ __("until {0}", [display(h.valid_to)]) }}</span>
							<button
								type="button"
								class="rounded-full p-1 hover:bg-surface-gray-3"
								:aria-label="__('Take away')"
								:title="__('Take away')"
								@click="take(n.row, h)"
							>
								<span class="lucide-user-minus size-3.5" />
							</button>
						</span>
						<span v-if="!n.holders.length" class="text-sm text-ink-amber-7">{{ __("Nobody holds this designation") }}</span>
					</div>
				</div>
			</li>
		</ul>

		<ResourceForm
			v-model:open="formOpen"
			:def="def"
			:row="current"
			:initial="initial"
			@saved="load"
		/>
		<AssignmentDialog
			v-model:open="giveOpen"
			mode="give"
			:designation-id="target?.id ?? null"
			:summary="target ? target.name : ''"
			@saved="load"
		/>
		<AssignmentDialog
			v-model:open="takeOpen"
			mode="take"
			:assignment-id="taking?.assignment_id ?? null"
			:summary="taking && target ? `${taking.name} · ${target.name}` : ''"
			@saved="load"
		/>
	</div>
</template>

<script setup lang="ts">
import { Badge, Button, ErrorMessage } from "frappe-ui"
import { computed, onMounted, reactive, ref } from "vue"
import AssignmentDialog from "@/components/AssignmentDialog.vue"
import PageHeader from "@/components/PageHeader.vue"
import ResourceForm from "@/components/ResourceForm.vue"
import { api } from "@/lib/api"
import { __ } from "@/lib/i18n"
import { display } from "@/lib/jalali"
import type { EmployeeRow } from "@/lib/people"
import { invalidateRef } from "@/lib/refs"
import { resourceDef } from "@/lib/resources"

interface DesignationRow {
	id: number
	name: string
	parent_id: number | null
	is_ceo: boolean
	hard_and_harmful: boolean
	[key: string]: unknown
}

interface Holder {
	assignment_id: number
	employee_id: number
	name: string
	valid_to: string | null
	active: boolean
}

const def = resourceDef("designations")!
const designations = ref<DesignationRow[]>([])
const employees = ref<EmployeeRow[]>([])
const loading = ref(false)
const error = ref("")
const collapsed = reactive(new Set<number>())

const formOpen = ref(false)
const current = ref<Record<string, unknown> | null>(null)
const initial = ref<Record<string, unknown>>({})
const giveOpen = ref(false)
const takeOpen = ref(false)
const target = ref<DesignationRow | null>(null)
const taking = ref<Holder | null>(null)

// the current holders of every designation
const holders = computed(() => {
	const byDesignation = new Map<number, Holder[]>()
	for (const e of employees.value) {
		for (const d of e.designations) {
			if (!d.current) continue
			const list = byDesignation.get(d.designation_id) ?? []
			list.push({ assignment_id: d.assignment_id, employee_id: e.id, name: e.full_name, valid_to: d.valid_to, active: e.status === "active" })
			byDesignation.set(d.designation_id, list)
		}
	}
	return byDesignation
})

// the tree flattened in reading order; each row knows its depth
const nodes = computed(() => {
	const byParent = new Map<number | null, DesignationRow[]>()
	const known = new Set(designations.value.map((d) => d.id))
	for (const d of designations.value) {
		const key = d.parent_id && known.has(d.parent_id) ? d.parent_id : null
		byParent.set(key, [...(byParent.get(key) ?? []), d])
	}
	const order = (list: DesignationRow[]) =>
		[...list].sort((a, b) => Number(b.is_ceo) - Number(a.is_ceo) || a.name.localeCompare(b.name, "fa"))
	const out: { id: number; row: DesignationRow; depth: number; hasChildren: boolean; holders: Holder[] }[] = []
	const walk = (parent: number | null, depth: number) => {
		for (const row of order(byParent.get(parent) ?? [])) {
			const children = byParent.get(row.id) ?? []
			out.push({ id: row.id, row, depth, hasChildren: children.length > 0, holders: holders.value.get(row.id) ?? [] })
			if (!collapsed.has(row.id)) walk(row.id, depth + 1)
		}
	}
	walk(null, 0)
	return out
})

function toggle(id: number) {
	if (collapsed.has(id)) collapsed.delete(id)
	else collapsed.add(id)
}

function edit(row: DesignationRow) {
	current.value = row
	initial.value = {}
	formOpen.value = true
}

function addChild(parent: DesignationRow | null) {
	current.value = null
	initial.value = parent ? { parent_id: parent.id } : {}
	formOpen.value = true
}

function give(row: DesignationRow) {
	target.value = row
	giveOpen.value = true
}

function take(row: DesignationRow, holder: Holder) {
	target.value = row
	taking.value = holder
	takeOpen.value = true
}

async function load() {
	loading.value = true
	error.value = ""
	try {
		;[designations.value, employees.value] = await Promise.all([
			api.get<DesignationRow[]>("/admin/designations"),
			api.get<EmployeeRow[]>("/admin/employees"),
		])
		invalidateRef("designations")
	} catch (e) {
		error.value = (e as Error).message
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
