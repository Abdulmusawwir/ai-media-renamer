/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0f1115",
        "bg-elev": "#171a21",
        "bg-elev-2": "#1f232c",
        border: "#2a2f3a",
        text: "#e6e9ef",
        "text-dim": "#9aa3b2",
        accent: "#3b82f6",
        "accent-2": "#2563eb",
        ok: "#22c55e",
        warn: "#f59e0b",
        danger: "#ef4444",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
