import type { Config } from "tailwindcss";

/**
 * BLUEBAN 813 design tokens.
 *
 * Mission-control palette matched to docs/design/dashboard-target.png:
 * a near-black navy field, glassy navy panels with thin blue rules, one blue
 * accent for interaction, and colour reserved for STATE (nominal / caution /
 * alert / critical). Every colour here is a token; components never invent one.
 */
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      screens: {
        // named because arbitrary min-[…] variants are unavailable alongside raw screens
        wide: "1700px",
        short: { raw: "(max-height: 980px)" },
        tiny: { raw: "(max-height: 820px)" },
        mini: { raw: "(max-height: 700px)" },
      },
      colors: {
        void: "#040915",
        deep: "#071024",
        panel: "#0A1630",
        panel2: "#0D1C3B",
        edge: "#16284D",
        line: "#1E3563",
        ink: "#EAF1FF",
        muted: "#93A6CB",
        // 5:1 on the panel colour (was #5D7299, 3.7:1, below WCAG AA for small text)
        dim: "#7088B3",
        beam: "#2F7BFF",
        beam2: "#4D93FF",
        // solid fills that carry white text: 5.2:1 (beam itself is 3.9:1, below WCAG AA)
        "beam-fill": "#2563EB",
        cyan: "#27C3F3",
        nominal: "#23D484",
        caution: "#FFC23D",
        alert: "#FF8A3D",
        critical: "#FF4D5E",
        // white text on it: 4.8:1 (critical itself is 3.2:1)
        "critical-fill": "#D63041",
        violet: "#8B7BFF",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "ui-monospace", "monospace"],
      },
      letterSpacing: { hud: "0.16em", wide2: "0.08em" },
      borderRadius: { panel: "10px" },
      boxShadow: {
        panel: "0 0 0 1px rgba(47,123,255,0.10), 0 12px 40px -18px rgba(0,0,0,0.8)",
        beam: "0 0 0 1px rgba(47,123,255,0.55), 0 0 24px -6px rgba(47,123,255,0.65)",
        alert: "0 0 0 1px rgba(255,77,94,0.5), 0 0 22px -6px rgba(255,77,94,0.55)",
      },
      keyframes: {
        "scan-y": { "0%": { transform: "translateY(-100%)" }, "100%": { transform: "translateY(100%)" } },
      },
      animation: { "scan-y": "scan-y 3.2s linear infinite" },
    },
  },
  plugins: [],
} satisfies Config;
