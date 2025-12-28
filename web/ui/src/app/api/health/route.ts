/**
 * Frontend Health Check API
 *
 * Returns health status of the frontend application.
 * Used for monitoring and load balancer health checks.
 */

import { NextResponse } from 'next/server';

interface HealthCheckResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  version: string;
  timestamp: string;
  checks: {
    frontend: 'ok' | 'error';
    build: 'ok' | 'error';
  };
  uptime: number;
}

const startTime = Date.now();

export async function GET() {
  const response: HealthCheckResponse = {
    status: 'healthy',
    version: process.env.npm_package_version || '1.0.0',
    timestamp: new Date().toISOString(),
    checks: {
      frontend: 'ok',
      build: 'ok',
    },
    uptime: Math.floor((Date.now() - startTime) / 1000),
  };

  return NextResponse.json(response, {
    status: 200,
    headers: {
      'Cache-Control': 'no-store, max-age=0',
    },
  });
}
