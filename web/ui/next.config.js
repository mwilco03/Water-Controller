/** @type {import('next').NextConfig} */

// -----------------------------------------------------------------------------
// DRY-COMPLIANT PORT CONFIGURATION
// -----------------------------------------------------------------------------
// Port values are loaded from config/ports.env using dotenv.
// This ensures config/ports.env is the SINGLE SOURCE OF TRUTH.
//
// The hardcoded fallbacks (8000, 8080) are only used if:
// 1. config/ports.env cannot be found
// 2. The environment variables are not set
// -----------------------------------------------------------------------------

const path = require('path');
const fs = require('fs');

/**
 * Find and load the ports.env configuration file
 */
function loadPortsEnv() {
  // Possible locations for ports.env
  const searchPaths = [
    // Explicit config directory
    process.env.WTC_CONFIG_DIR && path.join(process.env.WTC_CONFIG_DIR, 'ports.env'),
    // Production location
    '/opt/water-controller/config/ports.env',
    // Development: relative to this file (web/ui/next.config.js -> config/ports.env)
    path.resolve(__dirname, '../../config/ports.env'),
    // Docker: mounted config
    '/app/config/ports.env',
  ].filter(Boolean);

  for (const envPath of searchPaths) {
    if (fs.existsSync(envPath)) {
      try {
        const content = fs.readFileSync(envPath, 'utf8');
        const result = {};
        for (const line of content.split('\n')) {
          const trimmed = line.trim();
          // Skip comments and empty lines
          if (!trimmed || trimmed.startsWith('#')) continue;
          // Parse KEY=VALUE
          const match = trimmed.match(/^([A-Z_][A-Z0-9_]*)=(.*)$/);
          if (match) {
            let [, key, value] = match;
            // Strip quotes if present
            value = value.replace(/^["']|["']$/g, '');
            // Only set if not already in environment
            if (!process.env[key]) {
              process.env[key] = value;
            }
            result[key] = value;
          }
        }
        console.log(`[next.config.js] Loaded port configuration from ${envPath}`);
        return result;
      } catch (err) {
        console.warn(`[next.config.js] Could not read ${envPath}: ${err.message}`);
      }
    }
  }
  console.warn('[next.config.js] ports.env not found, using hardcoded fallbacks');
  return {};
}

// Load configuration from ports.env
loadPortsEnv();

// Get port values from environment (now populated from ports.env)
// Hardcoded fallbacks (8000, 8080) are last resort only
const apiPort = process.env.WTC_API_PORT || process.env.API_PORT || '8000';
const apiHost = process.env.WTC_API_HOST || process.env.API_HOST || 'localhost';
const apiUrl = process.env.API_URL || process.env.WTC_API_URL || `http://${apiHost}:${apiPort}`;

const nextConfig = {
  reactStrictMode: false,
  experimental: {
    serverComponentsExternalPackages: ['react-server-components'],
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
      {
        source: '/ws/:path*',
        destination: `${apiUrl}/ws/:path*`,
      },
      {
        source: '/health',
        destination: `${apiUrl}/health`,
      },
    ];
  },
};

module.exports = nextConfig;
