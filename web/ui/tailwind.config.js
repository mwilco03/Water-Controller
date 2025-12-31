/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      /*
       * ISA-101 SCADA HMI Color Palette
       * Core principle: Gray is Normal, Color is Abnormal
       */
      colors: {
        // Background & Surface
        'hmi': {
          'bg': '#F5F5F5',           // Page background (light gray)
          'panel': '#FFFFFF',         // Cards, panels
          'border': '#E0E0E0',        // Borders, dividers
          'text': '#212121',          // Primary text
          'muted': '#757575',         // Secondary text
          'equipment': '#9E9E9E',     // Normal equipment state
        },
        // Status Colors (ISA-101 compliant)
        'status': {
          'ok': '#4CAF50',            // Running, safe (use sparingly)
          'warning': '#FF9800',       // Caution, abnormal
          'alarm': '#F44336',         // Critical, danger, stop
          'info': '#2196F3',          // Informational, manual
          'offline': '#9E9E9E',       // Disconnected, inactive
        },
        // Data quality backgrounds
        'quality': {
          'good': '#FFFFFF',
          'uncertain': '#FFF8E1',     // Light amber
          'bad': '#FFEBEE',           // Light red
          'stale': '#FAFAFA',         // Light gray
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      // Responsive breakpoints (standard Tailwind)
      screens: {
        'sm': '640px',
        'md': '768px',
        'lg': '1024px',
        'xl': '1280px',
        '2xl': '1536px',
      },
      // Minimal animations
      animation: {
        'alarm-flash': 'alarm-flash 1s step-end infinite',
        'spin-slow': 'spin 2s linear infinite',
      },
      keyframes: {
        'alarm-flash': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
      },
      // Clean shadows
      boxShadow: {
        'card': '0 1px 3px rgba(0, 0, 0, 0.08)',
        'card-hover': '0 4px 12px rgba(0, 0, 0, 0.1)',
        'nav': '0 1px 3px rgba(0, 0, 0, 0.05)',
      },
      // Spacing extensions
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
        '128': '32rem',
      },
      // Max-width for containers
      maxWidth: {
        'hmi': '1600px',
      },
    },
  },
  plugins: [],
};
