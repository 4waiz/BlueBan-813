/**
 * Two build modes.
 *
 * dev / start  — the FastAPI service runs alongside and /api is proxied to it,
 *                so the app talks to a live pipeline.
 * export       — BLUEBAN_STATIC=1 produces a fully static site. Every visitor
 *                gets a private in-browser workspace (lib/engine/local.ts)
 *                seeded from public/pipeline, which scripts/build_static_site.py
 *                bakes from outputs/ first.
 */
const API = process.env.BLUEBAN_API ?? "http://127.0.0.1:8813";
const STATIC = process.env.BLUEBAN_STATIC === "1";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Trailing slashes keep Cloudflare Pages' static routing predictable for
  // nested routes such as /judge and /spectra.
  trailingSlash: STATIC,
  // The static export builds into its own folder so it never clobbers a
  // running dev server's .next.
  distDir: STATIC ? ".next-static" : ".next",
  ...(STATIC
    ? { output: "export", images: { unoptimized: true } }
    : {
        async rewrites() {
          return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
        },
      }),
};
export default nextConfig;
