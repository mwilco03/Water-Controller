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
        // ISA-101 HMI Color Palette - Gray is Normal, Color is Abnormal
        'hmi': {
          'bg': '#F0F0F0',           // Light gray page background
          'bg-alt': '#E5E5E5',       // Alternate background
          'panel': '#FFFFFF',        // Card/panel background
          'border': '#D0D0D0',       // Card borders
          'text': '#1A1A1A',         // Primary text
          'text-secondary': '#666666', // Secondary/muted text
          'equipment': '#808080',    // Normal equipment gray
          'offline': '#9E9E9E',      // Disconnected/inactive gray
        },
        // ISA-101 Alarm Colors
        'alarm': {
          'red': '#D32F2F',          // Active alarms, faults, stop, danger
          'yellow': '#FFA000',       // Warnings, caution, abnormal
          'green': '#388E3C',        // Running, open, safe (use sparingly)
          'blue': '#1976D2',         // Informational, manual mode
          'cyan': '#0097A7',         // PID in auto, setpoint active
        },
        // Data Quality Background Tints
        'quality': {
          'uncertain-bg': '#FFF8E1',  // Light yellow tint
          'bad-bg': '#FFEBEE',        // Light red tint
          'stale-bg': '#F5F5F5',      // Gray tint
        },
        // Legacy colors for backwards compatibility
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
        'alarm-flash': 'alarm-flash 1s step-end infinite', // 1Hz alarm flash per ISA-101
      },
      keyframes: {
        flow: {
          '0%': { strokeDashoffset: '20' },
          '100%': { strokeDashoffset: '0' },
        },
        'alarm-flash': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        },
      },
      boxShadow: {
        'glow-blue': '0 0 20px rgba(56, 189, 248, 0.3)',
        'glow-green': '0 0 20px rgba(16, 185, 129, 0.3)',
        'glow-red': '0 0 20px rgba(239, 68, 68, 0.3)',
        'glow-amber': '0 0 20px rgba(245, 158, 11, 0.3)',
        'hmi-card': '0 1px 3px rgba(0, 0, 0, 0.1)', // Subtle shadow for HMI cards
      },
    },
  },
  plugins: [],
};
