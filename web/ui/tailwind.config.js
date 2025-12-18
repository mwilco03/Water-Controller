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
        'scada-bg': '#1a1a2e',
        'scada-panel': '#16213e',
        'scada-accent': '#0f3460',
        'scada-highlight': '#e94560',
        'sensor-good': '#00ff88',
        'sensor-warn': '#ffaa00',
        'sensor-bad': '#ff4444',
        'alarm-critical': '#ff0000',
        'alarm-warning': '#ffaa00',
        'alarm-info': '#00aaff',
      },
    },
  },
  plugins: [],
};
