import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  envDir: process.env.CLEARCREDIT_NO_ENV === '1' ? false : undefined,
  plugins: [react()],
})
