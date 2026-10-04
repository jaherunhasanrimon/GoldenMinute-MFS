/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        bengali: ['"Noto Sans Bengali"', 'sans-serif'],
      },
      colors: {
        upay: {
          primary: '#0F766E', // Deep teal
          accent: '#F59E0B',  // Amber
          dark: '#0F172A',    // Slate dark
          surface: '#1E293B',
          card: '#1E293B',
        }
      }
    },
  },
  plugins: [],
}
