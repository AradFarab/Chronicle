import frappeUIPreset, { content as frappeUIContent } from "frappe-ui/tailwind"

/** @type {import('tailwindcss').Config} */
export default {
	presets: [frappeUIPreset],
	content: [...frappeUIContent, "./index.html", "./src/**/*.{vue,ts}"],
	theme: {
		extend: {
			fontFamily: {
				sans: ["Vazirmatn", "Tahoma", "system-ui", "sans-serif"],
			},
		},
	},
}
