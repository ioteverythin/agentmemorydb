import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/explorer/',
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8100',
      '/ws': { target: 'ws://localhost:8100', ws: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
