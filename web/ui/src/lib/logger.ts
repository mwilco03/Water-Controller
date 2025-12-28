/**
 * Production-Safe Logger
 *
 * Gates console output based on environment:
 * - Development: All logs enabled
 * - Production: Only errors and warnings (no debug/info/log)
 *
 * Usage:
 *   import { logger } from '@/lib/logger';
 *   logger.info('Connected to WebSocket');
 *   logger.error('Failed to fetch', error);
 *   logger.warn('Retrying connection');
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogMessage {
  level: LogLevel;
  message: string;
  data?: unknown;
  timestamp: string;
  source?: string;
}

const isDevelopment = process.env.NODE_ENV === 'development';

/**
 * Send log to backend for persistent storage (production only)
 */
async function sendToBackend(log: LogMessage): Promise<void> {
  if (isDevelopment) return;

  try {
    await fetch('/api/v1/system/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(log),
    });
  } catch {
    // Silently fail - don't create log loops
  }
}

/**
 * Create a logger instance with optional source prefix
 */
function createLogger(source?: string) {
  const formatMessage = (level: LogLevel, message: string, data?: unknown): LogMessage => ({
    level,
    message,
    data,
    timestamp: new Date().toISOString(),
    source: source || 'frontend',
  });

  return {
    /**
     * Debug-level logging (development only)
     */
    debug: (message: string, ...args: unknown[]): void => {
      if (isDevelopment) {
        console.debug(`[DEBUG]${source ? ` [${source}]` : ''} ${message}`, ...args);
      }
    },

    /**
     * Info-level logging (development only)
     */
    info: (message: string, ...args: unknown[]): void => {
      if (isDevelopment) {
        console.info(`[INFO]${source ? ` [${source}]` : ''} ${message}`, ...args);
      }
    },

    /**
     * Log-level logging (development only, alias for info)
     */
    log: (message: string, ...args: unknown[]): void => {
      if (isDevelopment) {
        console.log(`[LOG]${source ? ` [${source}]` : ''} ${message}`, ...args);
      }
    },

    /**
     * Warning-level logging (all environments)
     */
    warn: (message: string, ...args: unknown[]): void => {
      console.warn(`[WARN]${source ? ` [${source}]` : ''} ${message}`, ...args);
      sendToBackend(formatMessage('warn', message, args.length > 0 ? args : undefined));
    },

    /**
     * Error-level logging (all environments)
     */
    error: (message: string, error?: Error | unknown, ...args: unknown[]): void => {
      console.error(`[ERROR]${source ? ` [${source}]` : ''} ${message}`, error, ...args);
      sendToBackend(formatMessage('error', message, {
        error: error instanceof Error ? {
          name: error.name,
          message: error.message,
          stack: error.stack,
        } : error,
        ...args,
      }));
    },

    /**
     * Create a child logger with a specific source
     */
    child: (childSource: string) => createLogger(source ? `${source}:${childSource}` : childSource),
  };
}

// Default logger instance
export const logger = createLogger();

// Named loggers for different subsystems
export const wsLogger = createLogger('WebSocket');
export const apiLogger = createLogger('API');
export const authLogger = createLogger('Auth');
export const rtuLogger = createLogger('RTU');
export const alarmLogger = createLogger('Alarm');

export default logger;
