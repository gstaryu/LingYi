import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 开发与生产均通过 rewrites 代理后端 FastAPI（:8000），前端同源调用 /api/*，免 CORS
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
