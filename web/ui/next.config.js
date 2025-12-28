/** @type {import('next').NextConfig} */

// Backend API URL - configurable via environment variable
// Default: http://localhost:8000 (matches systemd service configuration)
const apiUrl = process.env.API_URL || 'http://localhost:8000';

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
