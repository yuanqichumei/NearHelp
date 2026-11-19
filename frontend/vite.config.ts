import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';

const cert = process.env.NEARHELP_DEV_CERT;
const key = process.env.NEARHELP_DEV_KEY;
if (Boolean(cert) !== Boolean(key)) throw new Error('本地 HTTPS 需要同时配置证书和私钥。');
const https = cert && key ? { cert: readFileSync(cert), key: readFileSync(key) } : undefined;
const backendPort = Number(process.env.NEARHELP_DEV_API_PORT ?? 8000);
const proxy = { '/api': {
  target: 'http://127.0.0.1:' + backendPort,
  changeOrigin: false,
  headers: { 'X-Forwarded-Proto': https ? 'https' : 'http' },
} };

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy, https },
  preview: { proxy, https },
});
