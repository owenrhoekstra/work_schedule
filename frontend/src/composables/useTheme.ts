import { ref, watchEffect } from 'vue'

type Theme = 'system' | 'light' | 'dark'
const stored = localStorage.getItem('theme')
const theme = ref<Theme>(stored === 'light' || stored === 'dark' ? stored : 'system')

watchEffect(() => {
  const root = document.documentElement
  root.classList.remove('light', 'dark')
  if (theme.value === 'system') {
    localStorage.removeItem('theme')
  } else {
    root.classList.add(theme.value)
    localStorage.setItem('theme', theme.value)
  }
})

export const useTheme = () => ({ theme })