/**
 * Water Treatment Controller - Centralized Port Configuration
 *
 * SINGLE SOURCE OF TRUTH for all network ports used by the frontend.
 *
 * All ports should be accessed through this module. Never hardcode port values
 * elsewhere in the codebase.
 *
 * Environment variables can override defaults:
 * - NEXT_PUBLIC_API_PORT: API server port (default: 8000)
 * - NEXT_PUBLIC_UI_PORT: UI server port (default: 8080)
 * - NEXT_PUBLIC_API_URL: Full API URL (default: constructed from host + port)
 */

// -----------------------------------------------------------------------------
// Port Defaults
// -----------------------------------------------------------------------------

/**
 * Default port numbers - MODIFY ONLY HERE if changing defaults
 */
export const PORT_DEFAULTS = {
  /** FastAPI backend port */
  API: 8000,

  /** Next.js UI port */
  UI: 8080,

  /** UI HTTPS port (when TLS enabled) */
  UI_HTTPS: 8443,

  /** Docker internal UI port (container listens here) */
  DOCKER_UI_INTERNAL: 3000,

  /** PostgreSQL database port */
  DATABASE: 5432,

  /** PROFINET UDP discovery */
  PROFINET_UDP: 34964,

  /** Modbus TCP */
  MODBUS_TCP: 1502,

  /** Grafana */
  GRAFANA: 3000,
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
 * 2. Empty string for client-side (same-origin, Next.js rewrites handle proxy)
 *
 * Note: Server-side requires NEXT_PUBLIC_API_URL to be set (e.g., http://api:8000)
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

  // Server-side without config - return empty, will fail visibly if SSR fetch attempted
  // This is better than silently using localhost which doesn't work in containers
  console.warn('getApiUrl: No NEXT_PUBLIC_API_URL set for server-side. SSR API fetches will fail.');
  return '';
}

/**
 * Get the WebSocket URL for live updates
 *
 * Priority:
 * 1. NEXT_PUBLIC_WS_URL environment variable
 * 2. Constructed from current window location (client-side)
 *
 * Note: WebSockets are client-side only. Server-side returns empty string.
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

  // Server-side: WebSockets are client-only, return empty
  // No fake localhost URL that would never work
  return '';
}

/**
 * Get the current host for display purposes
 */
export function getCurrentHost(): string {
  if (typeof window !== 'undefined') {
    return window.location.host;
  }
  // Server-side: return placeholder, actual host only known client-side
  return '[server-side]';
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
