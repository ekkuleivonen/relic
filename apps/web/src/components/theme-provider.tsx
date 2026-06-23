/* eslint-disable react-refresh/only-export-components */
import * as React from "react"

type Theme = "dark" | "light" | "system"
type ResolvedTheme = "dark" | "light"

type ThemeProviderProps = {
  children: React.ReactNode
  defaultTheme?: Theme
  persistenceKey?: string
  disableTransitionOnChange?: boolean
}

type ThemeProviderState = {
  resolvedTheme: ResolvedTheme
  theme: Theme
  setTheme: (theme: Theme) => void
}

const COLOR_SCHEME_QUERY = "(prefers-color-scheme: dark)"
const THEME_VALUES: Theme[] = ["dark", "light", "system"]

const ThemeProviderContext = React.createContext<
  ThemeProviderState | undefined
>(undefined)

function isTheme(value: string | null): value is Theme {
  return value !== null && THEME_VALUES.includes(value as Theme)
}

function getSystemTheme(): ResolvedTheme {
  return window.matchMedia(COLOR_SCHEME_QUERY).matches ? "dark" : "light"
}

function disableTransitionsTemporarily() {
  const style = document.createElement("style")
  style.appendChild(
    document.createTextNode(
      "*,*::before,*::after{-webkit-transition:none!important;transition:none!important}"
    )
  )
  document.head.appendChild(style)

  return () => {
    window.getComputedStyle(document.body)
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        style.remove()
      })
    })
  }
}

export function ThemeProvider({
  children,
  defaultTheme = "system",
  persistenceKey = "relic-admin-theme",
  disableTransitionOnChange = true,
}: ThemeProviderProps) {
  const [theme, setThemeState] = React.useState<Theme>(() => {
    const persistedTheme = localStorage.getItem(persistenceKey)
    return isTheme(persistedTheme) ? persistedTheme : defaultTheme
  })
  const [systemTheme, setSystemTheme] =
    React.useState<ResolvedTheme>(getSystemTheme)
  const resolvedTheme = theme === "system" ? systemTheme : theme

  const setTheme = React.useCallback(
    (nextTheme: Theme) => {
      localStorage.setItem(persistenceKey, nextTheme)
      setThemeState(nextTheme)
    },
    [persistenceKey]
  )

  React.useEffect(() => {
    const root = document.documentElement
    const restoreTransitions = disableTransitionOnChange
      ? disableTransitionsTemporarily()
      : null

    root.classList.remove("light", "dark")
    root.classList.add(resolvedTheme)

    restoreTransitions?.()
  }, [disableTransitionOnChange, resolvedTheme])

  React.useEffect(() => {
    if (theme !== "system") {
      return undefined
    }

    const mediaQuery = window.matchMedia(COLOR_SCHEME_QUERY)
    const handleChange = () => {
      setSystemTheme(getSystemTheme())
    }

    mediaQuery.addEventListener("change", handleChange)

    return () => {
      mediaQuery.removeEventListener("change", handleChange)
    }
  }, [theme])

  React.useEffect(() => {
    const handlePersistedThemeChange = (event: StorageEvent) => {
      if (event.storageArea !== localStorage || event.key !== persistenceKey) {
        return
      }

      setThemeState(isTheme(event.newValue) ? event.newValue : defaultTheme)
    }

    window.addEventListener("storage", handlePersistedThemeChange)

    return () => {
      window.removeEventListener("storage", handlePersistedThemeChange)
    }
  }, [defaultTheme, persistenceKey])

  const value = React.useMemo(
    () => ({
      resolvedTheme,
      theme,
      setTheme,
    }),
    [resolvedTheme, theme, setTheme]
  )

  return (
    <ThemeProviderContext.Provider value={value}>
      {children}
    </ThemeProviderContext.Provider>
  )
}

export function useTheme() {
  const context = React.useContext(ThemeProviderContext)

  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider")
  }

  return context
}
