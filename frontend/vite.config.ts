import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  build: {
    // 产物文件名带内容哈希；沙箱环境会拦截 fs.rmSync 导致 emptyOutDir 报错，关闭自动清空
    emptyOutDir: false,
  },
  server: {
    port: 5173,
    proxy: {
      // 对接真实后端：/api/v1/* 代理到本机 FastAPI（main.py 端口 8000）
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
