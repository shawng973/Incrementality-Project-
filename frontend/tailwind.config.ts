import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Terroir brand palette — update once brand guidelines are confirmed
        brand: {
          50: "#f0f4f0",
          100: "#d9e5d9",
          500: "#4a7c59",
          600: "#3d6849",
          700: "#2f5239",
          900: "#1a2e20",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
