import type { Metadata, Viewport } from "next";
import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";
import AppShell from "@/components/shell/AppShell";

export const metadata: Metadata = {
  title: "BLUEBAN 813 - UAE Coastal Intelligence",
  description:
    "Closed-loop coastal incident intelligence for the UAE: Sentinel-2/3 monitoring, spectral diagnosis, human and field verification, and a governed learning loop. Built by Team Kanban.",
  icons: { icon: "/icon.png" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#040915" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Exo+2:wght@500;600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
