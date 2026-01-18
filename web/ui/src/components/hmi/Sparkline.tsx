'use client';

/**
 * Sparkline - Inline mini trend visualization
 *
 * Design principles:
 * - 15 minute window default (configurable)
 * - 5 minute average smoothing (configurable)
 * - Shows trend direction with arrow
 * - Monochrome by default, color for abnormal
 * - Small footprint (60-80px wide, 16-20px tall)
 */

import { useMemo } from 'react';

interface SparklineProps {
  /** Array of data points with timestamp and value */
  data: Array<{ timestamp: string | Date; value: number }>;
  /** Width in pixels (default: 60) */
  width?: number;
  /** Height in pixels (default: 16) */
  height?: number;
  /** Time window in minutes (default: 15) */
  windowMinutes?: number;
  /** Show trend direction arrow (default: true) */
  showTrend?: boolean;
  /** Color for the line (default: hmi-muted) */
  color?: 'normal' | 'warning' | 'alarm' | 'ok';
  /** High threshold - line turns warning/alarm color above this */
  highThreshold?: number;
  /** Low threshold - line turns warning/alarm color below this */
  lowThreshold?: number;
  /** Show min/max values */
  showMinMax?: boolean;
}

interface ProcessedData {
  points: Array<{ x: number; y: number; value: number }>;
  min: number;
  max: number;
  first: number;
  last: number;
  trend: 'up' | 'down' | 'stable';
  percentChange: number;
}

function processData(
  data: Array<{ timestamp: string | Date; value: number }>,
  windowMinutes: number
): ProcessedData | null {
  if (!data || data.length === 0) {
    return null;
  }

  const now = new Date();
  const windowStart = new Date(now.getTime() - windowMinutes * 60 * 1000);

  // Filter to window and sort by time
  const filtered = data
    .filter(d => new Date(d.timestamp) >= windowStart)
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  if (filtered.length === 0) {
    return null;
  }

  // Calculate 5-minute averages for smoothing
  const bucketSize = 5 * 60 * 1000; // 5 minutes in ms
  const buckets = new Map<number, number[]>();

  filtered.forEach(d => {
    const time = new Date(d.timestamp).getTime();
    const bucketKey = Math.floor(time / bucketSize) * bucketSize;
    if (!buckets.has(bucketKey)) {
      buckets.set(bucketKey, []);
    }
    buckets.get(bucketKey)!.push(d.value);
  });

  // Average each bucket
  const averaged = Array.from(buckets.entries())
    .map(([time, values]) => ({
      time,
      value: values.reduce((a, b) => a + b, 0) / values.length,
    }))
    .sort((a, b) => a.time - b.time);

  if (averaged.length === 0) {
    return null;
  }

  const values = averaged.map(d => d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const first = values[0];
  const last = values[values.length - 1];

  // Calculate trend
  const percentChange = first !== 0 ? ((last - first) / Math.abs(first)) * 100 : 0;
  let trend: 'up' | 'down' | 'stable' = 'stable';
  if (percentChange > 2) trend = 'up';
  else if (percentChange < -2) trend = 'down';

  // Normalize to 0-1 range for drawing
  const range = max - min || 1;
  const timeRange = averaged[averaged.length - 1].time - averaged[0].time || 1;

  const points = averaged.map(d => ({
    x: (d.time - averaged[0].time) / timeRange,
    y: 1 - (d.value - min) / range, // Invert Y for SVG coordinates
    value: d.value,
  }));

  return { points, min, max, first, last, trend, percentChange };
}

export function Sparkline({
  data,
  width = 60,
  height = 16,
  windowMinutes = 15,
  showTrend = true,
  color = 'normal',
  highThreshold,
  lowThreshold,
  showMinMax = false,
}: SparklineProps) {
  const processed = useMemo(
    () => processData(data, windowMinutes),
    [data, windowMinutes]
  );

  if (!processed || processed.points.length < 2) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-hmi-muted">
        <span className="w-[60px] h-[16px] bg-hmi-bg rounded flex items-center justify-center text-[10px]">
          --
        </span>
      </span>
    );
  }

  // Determine color based on thresholds
  let lineColor = color;
  if (highThreshold !== undefined && processed.last > highThreshold) {
    lineColor = 'alarm';
  } else if (lowThreshold !== undefined && processed.last < lowThreshold) {
    lineColor = 'warning';
  }

  const colorClasses = {
    normal: 'stroke-hmi-muted',
    warning: 'stroke-status-warning',
    alarm: 'stroke-status-alarm',
    ok: 'stroke-status-ok',
  };

  const trendArrows = {
    up: '↑',
    down: '↓',
    stable: '→',
  };

  const trendColors = {
    up: 'text-status-alarm',
    down: 'text-status-ok',
    stable: 'text-hmi-muted',
  };

  // Build SVG path
  const pathData = processed.points
    .map((p, i) => {
      const x = p.x * (width - 4) + 2;
      const y = p.y * (height - 4) + 2;
      return i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`;
    })
    .join(' ');

  return (
    <span className="inline-flex items-center gap-1">
      <svg
        width={width}
        height={height}
        className="flex-shrink-0"
        role="img"
        aria-label={`Trend: ${processed.trend}, ${processed.percentChange.toFixed(1)}% change`}
      >
        {/* Background */}
        <rect
          x="0"
          y="0"
          width={width}
          height={height}
          className="fill-hmi-bg"
          rx="2"
        />
        {/* Threshold lines */}
        {highThreshold !== undefined && processed.max >= highThreshold && (
          <line
            x1="2"
            y1={2 + (1 - (highThreshold - processed.min) / (processed.max - processed.min || 1)) * (height - 4)}
            x2={width - 2}
            y2={2 + (1 - (highThreshold - processed.min) / (processed.max - processed.min || 1)) * (height - 4)}
            className="stroke-status-alarm/30"
            strokeWidth="1"
            strokeDasharray="2,2"
          />
        )}
        {lowThreshold !== undefined && processed.min <= lowThreshold && (
          <line
            x1="2"
            y1={2 + (1 - (lowThreshold - processed.min) / (processed.max - processed.min || 1)) * (height - 4)}
            x2={width - 2}
            y2={2 + (1 - (lowThreshold - processed.min) / (processed.max - processed.min || 1)) * (height - 4)}
            className="stroke-status-warning/30"
            strokeWidth="1"
            strokeDasharray="2,2"
          />
        )}
        {/* Sparkline */}
        <path
          d={pathData}
          className={colorClasses[lineColor]}
          strokeWidth="1.5"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* End point dot */}
        <circle
          cx={processed.points[processed.points.length - 1].x * (width - 4) + 2}
          cy={processed.points[processed.points.length - 1].y * (height - 4) + 2}
          r="2"
          className={`fill-current ${trendColors[processed.trend]}`}
        />
      </svg>
      {showTrend && (
        <span className={`text-xs font-medium ${trendColors[processed.trend]}`}>
          {trendArrows[processed.trend]}
        </span>
      )}
      {showMinMax && (
        <span className="text-[10px] text-hmi-muted">
          {processed.min.toFixed(1)}-{processed.max.toFixed(1)}
        </span>
      )}
    </span>
  );
}

export default Sparkline;
