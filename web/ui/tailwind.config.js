/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'scada-bg': '#0f172a',
        'scada-panel': '#1e293b',
        'scada-accent': '#334155',
        'scada-highlight': '#0ea5e9',
        'sensor-good': '#10b981',
        'sensor-warn': '#f59e0b',
        'sensor-bad': '#ef4444',
        'alarm-critical': '#ef4444',
        'alarm-warning': '#f59e0b',
        'alarm-info': '#0ea5e9',
        'water-blue': '#38bdf8',
        'water-dark': '#0284c7',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 3s linear infinite',
        'flow': 'flow 1s linear infinite',
      },
      keyframes: {
        flow: {
          '0%': { strokeDashoffset: '20' },
          '100%': { strokeDashoffset: '0' },
        },
      },
      boxShadow: {
        'glow-blue': '0 0 20px rgba(56, 189, 248, 0.3)',
        'glow-green': '0 0 20px rgba(16, 185, 129, 0.3)',
        'glow-red': '0 0 20px rgba(239, 68, 68, 0.3)',
        'glow-amber': '0 0 20px rgba(245, 158, 11, 0.3)',
      },
    },
  },
  plugins: [],
};
