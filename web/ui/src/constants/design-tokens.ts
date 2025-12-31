/**
 * SCADA HMI Design Tokens
 * Comprehensive design system following ISA-101 standards
 *
 * Core Design Principles:
 * 1. Gray is Normal, Color is Abnormal
 * 2. Mobile-forward with full desktop parity
 * 3. Touch-first interaction (44px minimum targets)
 * 4. Semantic color usage only
 * 5. Accessibility mandatory (WCAG 2.1 AA)
 */

// ============================================
// SPACING SCALE
// ============================================

export const SPACING = {
  /** 4px - Minimal internal padding */
  xs: '0.25rem',
  /** 8px - Compact spacing */
  sm: '0.5rem',
  /** 12px - Between spacing */
  md: '0.75rem',
  /** 16px - Standard spacing */
  base: '1rem',
  /** 20px - Comfortable spacing */
  lg: '1.25rem',
  /** 24px - Section spacing */
  xl: '1.5rem',
  /** 32px - Component separation */
  '2xl': '2rem',
  /** 48px - Major section separation */
  '3xl': '3rem',
  /** 64px - Page section separation */
  '4xl': '4rem',
} as const;

// ============================================
// TYPOGRAPHY SCALE
// ============================================

export const TYPOGRAPHY = {
  fontSize: {
    /** 10px - Micro labels */
    xs: '0.625rem',
    /** 12px - Captions, badges */
    sm: '0.75rem',
    /** 14px - Secondary text, inputs */
    base: '0.875rem',
    /** 16px - Body text */
    lg: '1rem',
    /** 18px - Subheadings */
    xl: '1.125rem',
    /** 20px - Section headings */
    '2xl': '1.25rem',
    /** 24px - Page headings */
    '3xl': '1.5rem',
    /** 30px - Hero headings */
    '4xl': '1.875rem',
    /** 36px - Large displays */
    '5xl': '2.25rem',
  },
  fontWeight: {
    normal: '400',
    medium: '500',
    semibold: '600',
    bold: '700',
  },
  lineHeight: {
    tight: '1.2',
    normal: '1.5',
    relaxed: '1.75',
  },
  fontFamily: {
    /** System UI stack for body text */
    sans: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    /** Monospace for values and data */
    mono: "'JetBrains Mono', 'Fira Code', Consolas, 'Courier New', monospace",
  },
} as const;

// ============================================
// TOUCH TARGETS & INTERACTION
// ============================================

export const TOUCH = {
  /** 44px - WCAG minimum touch target */
  minTarget: '2.75rem',
  /** 48px - Comfortable touch target */
  comfortableTarget: '3rem',
  /** 56px - List item height */
  listItem: '3.5rem',
  /** 64px - Bottom nav height */
  navBar: '4rem',
} as const;

// ============================================
// BREAKPOINTS (Mobile-first)
// ============================================

export const BREAKPOINTS = {
  /** 360px - Small phones */
  xs: '22.5rem',
  /** 640px - Large phones / small tablets */
  sm: '40rem',
  /** 768px - Tablets */
  md: '48rem',
  /** 1024px - Desktop / landscape tablets */
  lg: '64rem',
  /** 1280px - Large desktop */
  xl: '80rem',
  /** 1536px - Extra large displays */
  '2xl': '96rem',
} as const;

// ============================================
// COLOR PALETTE (ISA-101 Compliant)
// ============================================

export const COLORS = {
  // Neutral backgrounds & surfaces
  neutral: {
    /** #FFFFFF - Card, panel backgrounds */
    white: '#FFFFFF',
    /** #F5F5F5 - Page background */
    50: '#F5F5F5',
    /** #EEEEEE - Alternate background */
    100: '#EEEEEE',
    /** #E0E0E0 - Borders, dividers */
    200: '#E0E0E0',
    /** #BDBDBD - Disabled text */
    300: '#BDBDBD',
    /** #9E9E9E - Normal equipment / offline */
    400: '#9E9E9E',
    /** #757575 - Secondary text */
    500: '#757575',
    /** #616161 - Muted text */
    600: '#616161',
    /** #424242 - Strong secondary */
    700: '#424242',
    /** #212121 - Primary text */
    900: '#212121',
  },

  // Status colors (use sparingly - color = abnormal)
  status: {
    /** Green - Running, safe, healthy */
    ok: {
      base: '#4CAF50',
      light: '#E8F5E9',
      dark: '#2E7D32',
      contrast: '#FFFFFF',
    },
    /** Amber - Warning, caution, pending */
    warning: {
      base: '#FF9800',
      light: '#FFF3E0',
      dark: '#E65100',
      contrast: '#FFFFFF',
    },
    /** Red - Alarm, critical, danger */
    alarm: {
      base: '#F44336',
      light: '#FFEBEE',
      dark: '#C62828',
      contrast: '#FFFFFF',
    },
    /** Blue - Info, manual mode, discovery */
    info: {
      base: '#2196F3',
      light: '#E3F2FD',
      dark: '#1565C0',
      contrast: '#FFFFFF',
    },
    /** Gray - Offline, disconnected */
    offline: {
      base: '#9E9E9E',
      light: '#FAFAFA',
      dark: '#616161',
      contrast: '#FFFFFF',
    },
  },

  // Alarm severity colors (ISA-101)
  alarm: {
    /** Emergency - Dark red, flashing required */
    emergency: '#B71C1C',
    /** Critical - Red */
    critical: '#D32F2F',
    /** High - Orange */
    high: '#F57C00',
    /** Medium - Amber */
    medium: '#FFA000',
    /** Low - Yellow */
    low: '#FBC02D',
    /** Info - Blue */
    info: '#1976D2',
  },

  // Control mode colors
  control: {
    /** Auto mode - Blue accent */
    auto: '#2196F3',
    /** Manual mode - Purple accent */
    manual: '#9C27B0',
    /** Local mode - Orange */
    local: '#FF9800',
    /** Remote mode - Teal */
    remote: '#009688',
  },
} as const;

// ============================================
// BORDER RADIUS
// ============================================

export const RADIUS = {
  /** 0px - No radius */
  none: '0',
  /** 4px - Subtle rounding */
  sm: '0.25rem',
  /** 6px - Standard rounding */
  base: '0.375rem',
  /** 8px - Card rounding */
  md: '0.5rem',
  /** 12px - Modal rounding */
  lg: '0.75rem',
  /** 16px - Large panels */
  xl: '1rem',
  /** Full circle */
  full: '9999px',
} as const;

// ============================================
// SHADOWS
// ============================================

export const SHADOWS = {
  /** No shadow */
  none: 'none',
  /** Subtle card shadow */
  sm: '0 1px 2px rgba(0, 0, 0, 0.05)',
  /** Standard card shadow */
  base: '0 1px 3px rgba(0, 0, 0, 0.08)',
  /** Elevated element shadow */
  md: '0 4px 6px rgba(0, 0, 0, 0.1)',
  /** Modal / dropdown shadow */
  lg: '0 10px 15px rgba(0, 0, 0, 0.1)',
  /** Top navigation shadow */
  nav: '0 1px 3px rgba(0, 0, 0, 0.05)',
  /** Bottom navigation shadow */
  bottomNav: '0 -2px 10px rgba(0, 0, 0, 0.08)',
} as const;

// ============================================
// Z-INDEX SCALE
// ============================================

export const Z_INDEX = {
  /** Behind content */
  behind: -1,
  /** Normal content */
  base: 0,
  /** Raised elements */
  raised: 10,
  /** Sticky headers */
  sticky: 20,
  /** Dropdowns */
  dropdown: 30,
  /** Fixed elements */
  fixed: 40,
  /** Overlays / backdrops */
  overlay: 50,
  /** Modal dialogs */
  modal: 60,
  /** Toasts / notifications */
  toast: 70,
  /** Tooltips */
  tooltip: 80,
  /** Critical alerts */
  alert: 100,
} as const;

// ============================================
// ANIMATION & TRANSITIONS
// ============================================

export const ANIMATION = {
  duration: {
    /** 100ms - Immediate feedback */
    instant: '100ms',
    /** 150ms - Quick transitions */
    fast: '150ms',
    /** 250ms - Standard transitions */
    normal: '250ms',
    /** 350ms - Deliberate transitions */
    slow: '350ms',
    /** 500ms - Dramatic transitions */
    slower: '500ms',
  },
  easing: {
    /** Standard ease */
    default: 'cubic-bezier(0.4, 0, 0.2, 1)',
    /** Enter ease */
    enter: 'cubic-bezier(0, 0, 0.2, 1)',
    /** Exit ease */
    exit: 'cubic-bezier(0.4, 0, 1, 1)',
    /** Spring ease */
    spring: 'cubic-bezier(0.175, 0.885, 0.32, 1.275)',
  },
  /** ISA-101 alarm flash: 1Hz (1 second cycle) */
  alarmFlashDuration: '1s',
} as const;

// ============================================
// COMPONENT TOKENS
// ============================================

export const COMPONENTS = {
  button: {
    height: {
      sm: '2rem',
      md: '2.75rem',
      lg: '3rem',
    },
    padding: {
      sm: '0.5rem 0.75rem',
      md: '0.5rem 1rem',
      lg: '0.75rem 1.5rem',
    },
    fontSize: {
      sm: TYPOGRAPHY.fontSize.sm,
      md: TYPOGRAPHY.fontSize.base,
      lg: TYPOGRAPHY.fontSize.lg,
    },
  },
  input: {
    height: {
      sm: '2.25rem',
      md: '2.75rem',
      lg: '3rem',
    },
    padding: {
      sm: '0.5rem 0.75rem',
      md: '0.625rem 0.875rem',
      lg: '0.75rem 1rem',
    },
    fontSize: TYPOGRAPHY.fontSize.base,
  },
  card: {
    padding: {
      sm: SPACING.md,
      md: SPACING.base,
      lg: SPACING.xl,
    },
    radius: RADIUS.md,
  },
  badge: {
    height: {
      sm: '1.25rem',
      md: '1.5rem',
      lg: '1.75rem',
    },
    fontSize: {
      sm: TYPOGRAPHY.fontSize.xs,
      md: TYPOGRAPHY.fontSize.sm,
      lg: TYPOGRAPHY.fontSize.base,
    },
  },
  statusDot: {
    size: {
      sm: '0.5rem',
      md: '0.625rem',
      lg: '0.75rem',
    },
  },
} as const;

// ============================================
// LAYOUT TOKENS
// ============================================

export const LAYOUT = {
  /** Maximum content width */
  maxWidth: '100rem', // 1600px
  /** Container padding */
  containerPadding: {
    mobile: SPACING.base,
    tablet: SPACING.xl,
    desktop: SPACING['2xl'],
  },
  /** Safe area insets for notched devices */
  safeArea: {
    top: 'env(safe-area-inset-top, 0px)',
    bottom: 'env(safe-area-inset-bottom, 0px)',
    left: 'env(safe-area-inset-left, 0px)',
    right: 'env(safe-area-inset-right, 0px)',
  },
  /** Bottom navigation height */
  bottomNavHeight: '4rem',
  /** Top header height */
  headerHeight: '3.5rem',
} as const;

// ============================================
// DATA QUALITY TOKENS
// ============================================

export const DATA_QUALITY = {
  good: {
    border: 'transparent',
    background: COLORS.neutral.white,
    text: COLORS.neutral[900],
  },
  uncertain: {
    border: COLORS.status.warning.base,
    background: COLORS.status.warning.light,
    text: COLORS.status.warning.dark,
  },
  bad: {
    border: COLORS.status.alarm.base,
    background: COLORS.status.alarm.light,
    text: COLORS.status.alarm.dark,
  },
  stale: {
    border: COLORS.neutral[300],
    background: COLORS.neutral[50],
    text: COLORS.neutral[500],
  },
  notConnected: {
    border: COLORS.neutral[200],
    background: COLORS.neutral[50],
    text: COLORS.neutral[400],
  },
} as const;

// ============================================
// ACCESSIBILITY TOKENS
// ============================================

export const A11Y = {
  /** Focus ring width */
  focusRingWidth: '2px',
  /** Focus ring offset */
  focusRingOffset: '2px',
  /** Focus ring color */
  focusRingColor: COLORS.status.info.base,
  /** Minimum contrast ratio (WCAG AA) */
  contrastRatio: {
    normal: 4.5,
    large: 3,
  },
} as const;

// ============================================
// SEMANTIC HELPERS
// ============================================

/**
 * Get status color based on severity
 */
export function getStatusColor(severity: 'ok' | 'warning' | 'alarm' | 'info' | 'offline') {
  return COLORS.status[severity];
}

/**
 * Get alarm color based on severity level
 */
export function getAlarmSeverityColor(severity: 'emergency' | 'critical' | 'high' | 'medium' | 'low' | 'info') {
  return COLORS.alarm[severity];
}

/**
 * Get data quality styles
 */
export function getDataQualityStyle(quality: 'good' | 'uncertain' | 'bad' | 'stale' | 'notConnected') {
  return DATA_QUALITY[quality];
}

// Export all tokens as a single object for convenience
export const DESIGN_TOKENS = {
  spacing: SPACING,
  typography: TYPOGRAPHY,
  touch: TOUCH,
  breakpoints: BREAKPOINTS,
  colors: COLORS,
  radius: RADIUS,
  shadows: SHADOWS,
  zIndex: Z_INDEX,
  animation: ANIMATION,
  components: COMPONENTS,
  layout: LAYOUT,
  dataQuality: DATA_QUALITY,
  a11y: A11Y,
} as const;

export default DESIGN_TOKENS;
