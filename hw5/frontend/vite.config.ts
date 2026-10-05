import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Bind IPv4 explicitly so http://127.0.0.1:5173 and http://localhost:5173 both work on Windows.
  server: { host: '127.0.0.1', port: 5173 },
})
