import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    // O worker do maplibre-gl quebra quando pré-bundled pelo Vite no ambiente
    // WSL/Windows (net::ERR_FAILED), deixando o mapa em branco.
    exclude: ['maplibre-gl'],
  },
})
