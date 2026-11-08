import type { Config } from "tailwindcss";

export default {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0D1210",
        surface: {
          DEFAULT: "#151C19",
          2: "#1B2420",
        },
        border: "#27332D",
        text: {
          DEFAULT: "#E8EEEA",
          muted: "#9BA9A2",
          soft: "#C9D3CE",
        },
        accent: {
          DEFAULT: "#3DD68C",
          soft: "#7BE6B0",
        },
        warn: "#F2B84B",
        danger: "#FF8F87",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "sans-serif"],
      },
      maxWidth: {
        page: "1280px",
      },
      borderRadius: {
        card: "20px",
      },
    },
  },
  plugins: [],
} satisfies Config;
