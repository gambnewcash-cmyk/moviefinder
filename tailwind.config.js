/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        bg: '#0f0f0f',
        card: '#1a1a1a',
        accent: '#e50914',
        'accent-hover': '#c40812',
        border: '#2a2a2a',
        muted: '#888888',
      }
    }
  },
  plugins: [],
}
