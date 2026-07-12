/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      animation: {
        grain: "grain 8s steps(10) infinite",
      },
      keyframes: {
        grain: {
          "0%, 100%": { transform: "translate(0, 0)" },
          "10%": { transform: "translate(-2%, -5%)" },
          "50%": { transform: "translate(4%, 4%)" },
        },
      },
    },
  },
  plugins: [],
}
