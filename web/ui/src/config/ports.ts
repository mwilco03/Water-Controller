/**
 * Water Treatment Controller - Centralized Port Configuration
 *
 * DRY-COMPLIANT PORT CONFIGURATION
 * ================================
 * Port values are read from environment variables set by config/ports.env.
 * The hardcoded fallbacks are only used if environment variables are not set.
 *
 * Environment variables:
 * - WTC_API_PORT / NEXT_PUBLIC_API_PORT: API server port (default: 8000)
 * - WTC_UI_PORT / NEXT_PUBLIC_UI_PORT: UI server port (default: 8080)
 * - NEXT_PUBLIC_API_URL: Full API URL (default: constructed from host + port)
 *
 * IMPORTANT: config/ports.env is the SINGLE SOURCE OF TRUTH.
 * Ensure ports.env is loaded before Next.js starts (via dotenv in next.config.js).
 */

// -----------------------------------------------------------------------------
// Environment Variable Helpers
// -----------------------------------------------------------------------------

/**
 * Safely get an environment variable as an integer
 */
function getEnvInt(key: string, fallback: number): number {
  if (typeof process !== 'undefined' && process.env[key]) {
    const parsed = parseInt(process.env[key] as string, 10);
    return isNaN(parsed) ? fallback : parsed;
  }
  return fallback;
}

// -----------------------------------------------------------------------------
// Port Defaults (loaded from environment, with hardcoded fallbacks)
// -----------------------------------------------------------------------------

/**
 * Port defaults - values come from environment variables (set by config/ports.env)
 * The hardcoded fallbacks (8000, 8080, etc.) are only used if env vars are not set.
 *
 * IMPORTANT: If you change default ports, update config/ports.env - NOT this file.
 */
export const PORT_DEFAULTS = {
  /** FastAPI backend port - from WTC_API_PORT */
  get API() {
    return getEnvInt('WTC_API_PORT', 8000);
  },

  /** Next.js UI port - from WTC_UI_PORT */
  get UI() {
    return getEnvInt('WTC_UI_PORT', 8080);
  },

  /** UI HTTPS port (when TLS enabled) - from WTC_UI_HTTPS_PORT */
  get UI_HTTPS() {
    return getEnvInt('WTC_UI_HTTPS_PORT', 8443);
  },

  /** Docker internal UI port - from WTC_DOCKER_UI_INTERNAL_PORT */
  get DOCKER_UI_INTERNAL() {
    return getEnvInt('WTC_DOCKER_UI_INTERNAL_PORT', 3000);
  },

  /** PostgreSQL database port - from WTC_DB_PORT */
  get DATABASE() {
    return getEnvInt('WTC_DB_PORT', 5432);
  },

  /** PROFINET UDP discovery - from WTC_PROFINET_UDP_PORT */
  get PROFINET_UDP() {
    return getEnvInt('WTC_PROFINET_UDP_PORT', 34964);
  },

  /** Modbus TCP - from WTC_MODBUS_TCP_PORT */
  get MODBUS_TCP() {
    return getEnvInt('WTC_MODBUS_TCP_PORT', 1502);
  },

  /** Grafana - from WTC_GRAFANA_PORT */
  get GRAFANA() {
    return getEnvInt('WTC_GRAFANA_PORT', 3000);
  },
} as const;

// -----------------------------------------------------------------------------
// Runtime Port Configuration
// -----------------------------------------------------------------------------

/**
 * Get the API server port from environment or default
 */
export function getApiPort(): number {
  if (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_API_PORT) {
    return parseInt(process.env.NEXT_PUBLIC_API_PORT, 10);
  }
  return PORT_DEFAULTS.API;
}

/**
 * Get the UI server port from environment or default
 */
export function getUiPort(): number {
  if (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_UI_PORT) {
    return parseInt(process.env.NEXT_PUBLIC_UI_PORT, 10);
  }
  return PORT_DEFAULTS.UI;
}

/**
 * Get the full API base URL
 *
 * Priority:
 * 1. NEXT_PUBLIC_API_URL environment variable
 * 2. Constructed from window.location.origin (client-side, same-origin)
 * 3. Constructed from localhost + API port (server-side/fallback)
 */
export function getApiUrl(): string {
  // Check for explicit API URL override
  if (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  // Client-side: API is proxied through same origin
  if (typeof window !== 'undefined') {
    return ''; // Empty string = same origin (Next.js rewrites handle proxy)
  }

  // Server-side fallback
  return `http://localhost:${getApiPort()}`;
}

/**
 * Get the WebSocket URL for live updates
 *
 * Priority:
 * 1. NEXT_PUBLIC_WS_URL environment variable
 * 2. Constructed from current window location (client-side)
 * 3. Constructed from localhost + API port (server-side/fallback)
 */
export function getWebSocketUrl(): string {
  // Check for explicit WebSocket URL override
  if (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_WS_URL) {
    return process.env.NEXT_PUBLIC_WS_URL;
  }

  // Client-side: derive from current location
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/api/v1/ws/live`;
  }

  // Server-side fallback
  return `ws://localhost:${getApiPort()}/api/v1/ws/live`;
}

/**
 * Get the current host for display purposes
 */
export function getCurrentHost(): string {
  if (typeof window !== 'undefined') {
    return window.location.host;
  }
  return `localhost:${getUiPort()}`;
}

// -----------------------------------------------------------------------------
// Exported Configuration Object
// -----------------------------------------------------------------------------

/**
 * Complete port configuration object
 *
 * Usage:
 *   import { PORTS } from '@/config/ports';
 *   console.log(`API running on port ${PORTS.api}`);
 */
export const PORTS = {
  get api() {
    return getApiPort();
  },
  get ui() {
    return getUiPort();
  },
  get uiHttps() {
    return PORT_DEFAULTS.UI_HTTPS;
  },
  get database() {
    return PORT_DEFAULTS.DATABASE;
  },
  get profinetUdp() {
    return PORT_DEFAULTS.PROFINET_UDP;
  },
  get modbusTcp() {
    return PORT_DEFAULTS.MODBUS_TCP;
  },
  get grafana() {
    return PORT_DEFAULTS.GRAFANA;
  },
} as const;

/**
 * Complete URL configuration object
 *
 * Usage:
 *   import { URLS } from '@/config/ports';
 *   fetch(`${URLS.api}/v1/rtus`);
 */
export const URLS = {
  get api() {
    return getApiUrl();
  },
  get websocket() {
    return getWebSocketUrl();
  },
  get currentHost() {
    return getCurrentHost();
  },
} as const;

// Default export for convenience
export default { PORTS, URLS, PORT_DEFAULTS };
