import { useColorScheme } from "frappe-ui"

/** Light / dark / follow the phone. frappe-ui keeps <html data-theme> and localStorage in sync. */
export function useTheme() {
  const { colorScheme, setColorScheme } = useColorScheme()
  const order = ["system", "light", "dark"] as const
  function cycle() {
    const next = order[(order.indexOf(colorScheme.value) + 1) % order.length]
    setColorScheme(next)
  }
  return { colorScheme, cycle }
}
