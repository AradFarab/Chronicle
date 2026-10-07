<template>
	<div class="hz-card mt-8 text-center">
		<p class="text-lg font-semibold text-ink-gray-8">{{ __("Page not found") }}</p>
		<RouterLink class="mt-4 inline-block text-ink-blue-link underline" :to="{ name: 'today' }">
			{{ __("Back to today") }}
		</RouterLink>
	</div>
</template>
