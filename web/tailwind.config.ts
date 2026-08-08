import type { Config } from "tailwindcss";

// The palette from docs/DESIGN-TOKENS.md. Contrast is computed there, not
// asserted: ink 13.85:1 (AAA), indigo 6.92:1, brass 5.62:1, oxide 6.02:1, all
// against paper. `rule` sits at 1.44:1 — it may carry STRUCTURE and must never
// carry STATE, because at that ratio it is invisible to a lot of readers.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17233A",
        paper: "#EEF1F4",
        card: "#F7F9FA",
        indigo: "#35508C",
        brass: "#7A5A12",
        oxide: "#9C3B2E",
        rule: "#C2CCD6",
      },
      fontFamily: {
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        body: ["var(--font-body)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: { DEFAULT: "4px" },
    },
  },
  plugins: [],
};
export default config;
