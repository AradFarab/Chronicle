<template>
	<Dropdown :options="options" align="end">
		<button
			type="button"
			class="flex items-center gap-2 rounded-4 p-1.5 text-start hover:bg-surface-gray-2"
			:class="compact ? 'shrink-0' : 'w-full'"
			:aria-label="__('Account')"
		>
			<span
				class="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-gray-3 text-sm font-semibold text-ink-gray-7"
				>{{ initial }}</span
			>
			<span v-if="!compact" class="min-w-0 flex-1">
				<span class="block truncate text-sm font-medium">{{ session.user?.full_name }}</span>
				<span class="block truncate text-xs text-ink-gray-5">{{
					session.employee?.code || session.user?.username
				}}</span>
			</span>
		</button>
	</Dropdown>
</template>

<script setup lang="ts">
import { Dropdown, type DropdownOption } from "frappe-ui"
import { computed } from "vue"
import { useRouter } from "vue-router"
import { __ } from "@/lib/i18n"
import { logout, session } from "@/lib/session"
import { useTheme } from "@/lib/theme"

defineProps<{ compact?: boolean }>()

const router = useRouter()

const { colorScheme, cycle } = useTheme()

const initial = computed(() => (session.user?.full_name || session.user?.username || "?").trim().charAt(0))

const themeLabel = computed(
	() =>
		({
			system: __("Theme: follow the device"),
			light: __("Theme: light"),
			dark: __("Theme: dark"),
		}[colorScheme.value])
)

const options = computed(() => {
	const list: DropdownOption[] = [
		{
			label: themeLabel.value,
			icon:
				colorScheme.value === "dark"
					? "lucide-moon"
					: colorScheme.value === "light"
					? "lucide-sun"
					: "lucide-monitor",
			onClick: cycle,
		},
	]
	list.push({ label: __("Change password"), icon: "lucide-key-round", onClick: () => router.push({ name: "account" }) })
	list.push({ label: __("Log out"), icon: "lucide-log-out", onClick: logout })
	return list
})
</script>
