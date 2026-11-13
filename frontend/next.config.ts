import type { NextConfig } from "next";

// With NEXT_PUBLIC_API_URL=/api the browser talks only to this site, which
// forwards /api/* to the backend; one public address is then enough.
const backendUrl = (process.env.BACKEND_URL || "http://127.0.0.1:8001").replace(/\/$/, "");

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  experimental: {
    // Forwarded uploads are buffered up to this size; anything larger is cut off.
    proxyClientMaxBodySize: "1gb",
    // "New analysis" waits for the whole analysis (about a minute per clip).
    proxyTimeout: 15 * 60 * 1000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/:path*` }];
  },
};

export default nextConfig;
