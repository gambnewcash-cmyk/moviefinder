/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/**/*.js",
  ],
  safelist: [
    // Dynamic badge colors (movie.html sources)
    'bg-accent/20', 'text-accent', 'border-accent/30',
    'bg-green-900/40', 'text-green-400', 'border-green-800',
    // Free sources border/bg
    'border', 'border-green-600/40', 'bg-green-950/20', 'rounded-xl', 'p-3',
    // Label classes
    'text-muted',
    // Review form
    'text-red-400',
    // AI badge
    'bg-purple-900/50', 'text-purple-300', 'border-purple-700/50', 'px-1.5', 'py-0.5',
    // Grid cols
    'grid-cols-1', 'sm:grid-cols-2',
    // Opacity text
    'text-white/50', 'text-white',
    // Score badge
    'bg-accent/20',
    // Cached/live
    'text-xs', 'text-muted',
    // line-clamp
    'line-clamp-2',
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
