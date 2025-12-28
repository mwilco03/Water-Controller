/**
 * Quality Code Constants
 * OPC UA compatible quality codes for sensor data
 * Based on 5-byte sensor format
 */

export const QUALITY_CODES = {
  GOOD: 0x00,
  UNCERTAIN: 0x40,
  BAD: 0x80,
  NOT_CONNECTED: 0xC0,
} as const;

export type QualityCode = typeof QUALITY_CODES[keyof typeof QUALITY_CODES];

/**
 * Check if quality code indicates good quality
 */
export function isGoodQuality(code: number): boolean {
  return code === QUALITY_CODES.GOOD;
}

/**
 * Check if quality code indicates uncertain quality
 */
export function isUncertainQuality(code: number): boolean {
  return (code & 0xC0) === QUALITY_CODES.UNCERTAIN;
}

/**
 * Check if quality code indicates bad quality
 */
export function isBadQuality(code: number): boolean {
  return (code & 0xC0) === QUALITY_CODES.BAD;
}

/**
 * Check if quality code indicates not connected
 */
export function isNotConnected(code: number): boolean {
  return (code & 0xC0) === QUALITY_CODES.NOT_CONNECTED;
}

/**
 * Get a human-readable label for a quality code
 */
export function getQualityLabel(code: number): string {
  if (code === QUALITY_CODES.GOOD) return 'Good';
  if ((code & 0xC0) === QUALITY_CODES.UNCERTAIN) return 'Uncertain';
  if ((code & 0xC0) === QUALITY_CODES.BAD) return 'Bad';
  if ((code & 0xC0) === QUALITY_CODES.NOT_CONNECTED) return 'Not Connected';
  return 'Unknown';
}

/**
 * Get the quality category from a code
 */
export function getQualityCategory(code: number): 'good' | 'uncertain' | 'bad' | 'not_connected' {
  if (code === QUALITY_CODES.GOOD) return 'good';
  if ((code & 0xC0) === QUALITY_CODES.UNCERTAIN) return 'uncertain';
  if ((code & 0xC0) === QUALITY_CODES.BAD) return 'bad';
  return 'not_connected';
}
