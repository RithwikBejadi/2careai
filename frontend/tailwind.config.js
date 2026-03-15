/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        primary: "#4cd7f6",
        "primary-container": "#06b6d4",
        tertiary: "#ffb2b7",
        "surface-container-highest": "#2d3449",
        "on-surface": "#dae2fd",
        "outline-variant": "#3d494c",
      },
      fontFamily: {
        headline: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      animation: {
        "pulse-fast": "pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "spin-slow": "spin 10s linear infinite",
        flicker: "flicker 2s infinite",
      },
      keyframes: {
        flicker: {
          "0%, 100%": { opacity: "1" },
          "33%": { opacity: "0.98" },
          "66%": { opacity: "0.99" },
          "77%": { opacity: "1" },
          "88%": { opacity: "0.97" },
          "95%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};
