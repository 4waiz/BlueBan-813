/** @type {import('next').NextConfig} */
const API = process.env.BLUEBAN_API ?? "http://127.0.0.1:8813";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Proxy the API so the browser has a single origin and no CORS surprises.
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};
export default nextConfig;
