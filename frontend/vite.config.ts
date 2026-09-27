import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
  build: {
    rolldownOptions: {
      output: {
        advancedChunks: { groups: [
          { name: 'charts', test: /node_modules[\\/](recharts|d3-|victory)/ },
          { name: 'motion', test: /node_modules[\\/](motion|framer-motion|motion-dom|motion-utils|lenis)[\\/]/ },
        ] },
      },
    },
  },
})
