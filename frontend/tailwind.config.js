/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: { navy: { 900: '#0b1f3a', 800: '#12305a', 700: '#1c4279', 100: '#e6ecf5', 50: '#f3f6fb' } },
      fontFamily: { sans: ['system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Arial', 'sans-serif'] },
    },
  },
  plugins: [],
}
