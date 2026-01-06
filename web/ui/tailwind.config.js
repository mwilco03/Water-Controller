/** @type {import('tailwindcss').Config} */

/*
 * SCADA HMI Tailwind Configuration
 *
 * Design Principles:
 * 1. Gray is Normal, Color is Abnormal (ISA-101)
 * 2. Mobile-forward with full desktop parity
 * 3. Touch-first (44px minimum targets)
 * 4. Semantic color usage only
 * 5. WCAG 2.1 AA accessibility
 */

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
        // Background & Surface - Using CSS variables for dark mode support
        'hmi': {
          'bg': 'var(--hmi-bg)',           // Page background
          'bg-alt': '#EEEEEE',             // Alternate background
          'panel': 'var(--hmi-panel)',     // Cards, panels
          'border': 'var(--hmi-border)',   // Borders, dividers
          'text': 'var(--hmi-text)',       // Primary text
          'text-secondary': 'var(--hmi-text-muted)', // Secondary text (alias)
          'muted': 'var(--hmi-text-muted)', // Secondary text
          'equipment': 'var(--hmi-equipment)', // Normal equipment state
          'offline': 'var(--status-offline)',  // Offline state
          'disabled': '#BDBDBD',           // Disabled elements
        },
        // Status Colors (ISA-101 compliant) - Using CSS variables for dark mode
        'status': {
          'ok': 'var(--status-ok)',            // Running, safe (use sparingly)
          'ok-light': 'var(--status-ok-light)', // OK background
          'ok-dark': '#2E7D32',                // OK text on light
          'warning': 'var(--status-warning)',  // Caution, abnormal
          'warning-light': 'var(--status-warning-light)', // Warning background
          'warning-dark': '#E65100',           // Warning text on light
          'alarm': 'var(--status-alarm)',      // Critical, danger, stop
          'alarm-light': 'var(--status-alarm-light)', // Alarm background
          'alarm-dark': '#C62828',             // Alarm text on light
          'info': 'var(--status-info)',        // Informational, manual
          'info-light': 'var(--status-info-light)', // Info background
          'info-dark': '#1565C0',              // Info text on light
          'offline': 'var(--status-offline)',  // Disconnected, inactive
          'offline-light': '#FAFAFA',          // Offline background
          'offline-dark': '#616161',           // Offline text on light
        },
        // Alarm severity colors (backward compatibility + new)
        'alarm': {
          'emergency': '#B71C1C',     // Emergency (dark red)
          'critical': '#D32F2F',      // Critical alarm
          'high': '#F57C00',          // High priority
          'medium': '#FFA000',        // Medium priority
          'low': '#FBC02D',           // Low priority
          'info': '#1976D2',          // Informational
          // Legacy aliases
          'red': '#F44336',
          'yellow': '#FF9800',
          'blue': '#2196F3',
          'green': '#388E3C',
        },
        // Control mode colors
        'control': {
          'auto': '#2196F3',          // Automatic mode
          'manual': '#9C27B0',        // Manual mode
          'local': '#FF9800',         // Local control
          'remote': '#009688',        // Remote control
        },
        // SCADA accent colors (backward compatibility)
        'scada': {
          'accent': '#2196F3',        // Primary accent
          'highlight': '#1976D2',     // Highlighted elements
        },
        // Data quality backgrounds
        'quality': {
          'good': '#FFFFFF',
          'good-bg': '#E8F5E9',       // Light green background
          'uncertain': '#FFF8E1',     // Light amber
          'uncertain-bg': '#FFF8E1',  // Light amber background
          'bad': '#FFEBEE',           // Light red
          'bad-bg': '#FFEBEE',        // Light red background
          'stale': '#FAFAFA',         // Light gray
        },
      },

      // Typography
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      fontSize: {
        'xs': ['0.625rem', { lineHeight: '1rem' }],     // 10px
        'sm': ['0.75rem', { lineHeight: '1rem' }],      // 12px
        'base': ['0.875rem', { lineHeight: '1.25rem' }], // 14px
        'lg': ['1rem', { lineHeight: '1.5rem' }],       // 16px
        'xl': ['1.125rem', { lineHeight: '1.75rem' }],  // 18px
        '2xl': ['1.25rem', { lineHeight: '1.75rem' }],  // 20px
        '3xl': ['1.5rem', { lineHeight: '2rem' }],      // 24px
        '4xl': ['1.875rem', { lineHeight: '2.25rem' }], // 30px
        '5xl': ['2.25rem', { lineHeight: '2.5rem' }],   // 36px
      },

      // Responsive breakpoints (mobile-first)
      screens: {
        'xs': '360px',    // Small phones
        'sm': '640px',    // Large phones / small tablets
        'md': '768px',    // Tablets
        'lg': '1024px',   // Desktop / landscape tablets
        'xl': '1280px',   // Large desktop
        '2xl': '1536px',  // Extra large displays
      },

      // Touch-friendly spacing
      spacing: {
        '4.5': '1.125rem',  // 18px
        '13': '3.25rem',    // 52px
        '15': '3.75rem',    // 60px
        '18': '4.5rem',     // 72px
        '22': '5.5rem',     // 88px
        '88': '22rem',      // 352px
        '128': '32rem',     // 512px
        // Touch target sizes
        'touch-min': '2.75rem',       // 44px WCAG minimum
        'touch-comfortable': '3rem',   // 48px comfortable
        'touch-list': '3.5rem',        // 56px list items
        'touch-nav': '4rem',           // 64px nav items
      },

      // Border radius
      borderRadius: {
        'hmi': '0.5rem',       // 8px - Standard HMI rounding
        'hmi-sm': '0.375rem',  // 6px - Subtle rounding
        'hmi-lg': '0.75rem',   // 12px - Modal rounding
      },

      // Minimal animations
      animation: {
        'alarm-flash': 'alarm-flash 1s step-end infinite',
        'spin-slow': 'spin 2s linear infinite',
        'pulse-subtle': 'pulse-subtle 2s ease-in-out infinite',
        'slide-up': 'slide-up 0.25s ease-out',
        'slide-down': 'slide-down 0.25s ease-out',
        'fade-in': 'fade-in 0.15s ease-out',
        'scale-in': 'scale-in 0.2s ease-out',
      },
      keyframes: {
        'alarm-flash': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        'pulse-subtle': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.8' },
        },
        'slide-up': {
          '0%': { transform: 'translateY(0.5rem)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        'slide-down': {
          '0%': { transform: 'translateY(-0.5rem)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'scale-in': {
          '0%': { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
      },

      // Transition timing
      transitionDuration: {
        'instant': '100ms',
        'fast': '150ms',
        'normal': '250ms',
        'slow': '350ms',
      },

      // Clean shadows
      boxShadow: {
        'hmi-card': '0 1px 3px rgba(0, 0, 0, 0.08)',
        'hmi-card-hover': '0 4px 12px rgba(0, 0, 0, 0.1)',
        'hmi-nav': '0 1px 3px rgba(0, 0, 0, 0.05)',
        'hmi-bottom-nav': '0 -2px 10px rgba(0, 0, 0, 0.08)',
        'hmi-modal': '0 20px 40px rgba(0, 0, 0, 0.2)',
        'hmi-dropdown': '0 4px 16px rgba(0, 0, 0, 0.12)',
        // Legacy aliases
        'card': '0 1px 3px rgba(0, 0, 0, 0.08)',
        'card-hover': '0 4px 12px rgba(0, 0, 0, 0.1)',
        'nav': '0 1px 3px rgba(0, 0, 0, 0.05)',
      },

      // Z-index scale
      zIndex: {
        'behind': '-1',
        'raised': '10',
        'sticky': '20',
        'dropdown': '30',
        'fixed': '40',
        'overlay': '50',
        'modal-backdrop': '55',
        'modal': '60',
        'toast': '70',
        'tooltip': '80',
        'alert': '100',
      },

      // Max-width for containers
      maxWidth: {
        'hmi': '100rem',        // 1600px
        'hmi-sm': '40rem',      // 640px
        'hmi-md': '48rem',      // 768px
        'hmi-dialog': '25rem',  // 400px
      },

      // Min-height for touch targets
      minHeight: {
        'touch': '2.75rem',     // 44px
        'touch-lg': '3rem',     // 48px
        'touch-xl': '3.5rem',   // 56px
      },

      // Min-width for touch targets
      minWidth: {
        'touch': '2.75rem',     // 44px
        'touch-lg': '3rem',     // 48px
        'touch-xl': '3.5rem',   // 56px
      },

      // Aspect ratios for gauges and displays
      aspectRatio: {
        'gauge': '1 / 1',
        'wide': '16 / 9',
        'tank': '1 / 2',
      },
    },
  },
  plugins: [],
};
