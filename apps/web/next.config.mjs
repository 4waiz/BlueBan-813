/**
 * Two build modes.
 *
 * dev / start  — the FastAPI service runs alongside and /api is proxied to it,
 *                so the app talks to a live pipeline.
 * export       — BLUEBAN_STATIC=1 produces a fully static site. The API is
 *                read-only (it serves artefacts the offline pipeline already
 *                wrote), so the whole product ships as files with no server.
 *                scripts/build_static_site.py bakes those artefacts into
 *                public/data first.
 */
const API = process.env.BLUEBAN_API ?? "http://127.0.0.1:8813";
const STATIC = process.env.BLUEBAN_STATIC === "1";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Trailing slashes keep Cloudflare Pages' static routing predictable for
  // nested routes such as /judge and /spectra.
  trailingSlash: STATIC,
  ...(STATIC
    ? { output: "export", images: { unoptimized: true } }
    : {
        async rewrites() {
          return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
        },
      }),
};
export default nextConfig;
