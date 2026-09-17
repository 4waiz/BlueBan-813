import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void:   "#070A16",
        deep:   "#0A0F22",
        panel:  "#10162F",
        edge:   "#1B2444",
        line:   "#243056",
        ink:    "#F4F6FF",
        muted:  "#8A93B8",
        dim:    "#5A6490",
        beam:   "#3186FF",
        beam2:  "#4A93FF",
        nominal:"#3FD1A0",
        caution:"#F5C451",
        alert:  "#FF7A45",
        critical:"#FF4D4D",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "ui-monospace", "monospace"],
      },
      letterSpacing: { hud: "0.18em", wide2: "0.1em" },
    },
  },
  plugins: [],
} satisfies Config;
