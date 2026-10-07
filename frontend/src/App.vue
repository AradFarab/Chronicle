<template>
	<FrappeUIProvider>
		<RouterView v-if="route.meta.public" />
		<AppShell v-else>
			<RouterView />
		</AppShell>
	</FrappeUIProvider>
</template>

<script setup lang="ts">
import { FrappeUIProvider } from "frappe-ui"
import { useRoute } from "vue-router"
import AppShell from "./components/AppShell.vue"

const route = useRoute()
</script>
