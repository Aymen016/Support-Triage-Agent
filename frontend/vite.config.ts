import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    watch: {
      // dev server serves from source, never from dist/ — watching build
      // output too caused an EBUSY crash on Windows when dist/ existed
      // from a prior `npm run build`.
      ignored: ['**/dist/**'],
    },
  },
})
