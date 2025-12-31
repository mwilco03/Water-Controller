/** @type {import('next').NextConfig} */

// -----------------------------------------------------------------------------
// Port Configuration - CENTRALIZED
// -----------------------------------------------------------------------------
// All port values should come from environment variables or the central config.
// See: config/ports.env for the single source of truth.
// -----------------------------------------------------------------------------

// Port defaults (must match config/ports.env)
const PORT_DEFAULTS = {
  API: 8000,
  UI: 8080,
};

// Get API port from environment (WTC_API_PORT) or use default
const apiPort = process.env.WTC_API_PORT || process.env.API_PORT || PORT_DEFAULTS.API;

// Get API host from environment or default to localhost
const apiHost = process.env.WTC_API_HOST || process.env.API_HOST || 'localhost';

// Construct API URL from components (prefer explicit URL if provided)
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
