import { defineConfig } from 'vite';
export default defineConfig({ server: { proxy: { '/api': { target: process.env.API_PROXY || 'http://api-backend:8000', changeOrigin: true, timeout: 600000 } } } });
