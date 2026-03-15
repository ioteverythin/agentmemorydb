/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'gh-bg': '#0d1117',
        'gh-canvas': '#161b22',
        'gh-surface': '#1c2129',
        'gh-border': '#30363d',
        'gh-border-muted': '#21262d',
        'gh-text': '#e6edf3',
        'gh-muted': '#8b949e',
        'gh-dim': '#484f58',
        'gh-accent': '#58a6ff',
        'gh-accent-dim': 'rgba(88,166,255,0.15)',
        'gh-green': '#3fb950',
        'gh-green-dim': 'rgba(63,185,80,0.15)',
        'gh-orange': '#d29922',
        'gh-orange-dim': 'rgba(210,153,34,0.15)',
        'gh-red': '#f85149',
        'gh-red-dim': 'rgba(248,81,73,0.15)',
        'gh-purple': '#bc8cff',
        'gh-purple-dim': 'rgba(188,140,255,0.15)',
        'gh-cyan': '#39d2c0',
        'gh-cyan-dim': 'rgba(57,210,192,0.15)',
      },
      fontFamily: {
        sans: ['Segoe UI', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['Cascadia Code', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
