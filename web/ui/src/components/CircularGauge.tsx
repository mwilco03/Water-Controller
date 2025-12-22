'use client';

import { useMemo } from 'react';

// Quality code constants (OPC UA compatible - 5-byte sensor format)
const QUALITY_GOOD = 0x00;
const QUALITY_UNCERTAIN = 0x40;
const QUALITY_BAD = 0x80;
const QUALITY_NOT_CONNECTED = 0xC0;

interface Props {
  value: number;
  min: number;
  max: number;
  label: string;
  unit: string;
  quality?: number;  /* OPC UA quality code from 5-byte format */
  thresholds?: {
    warning?: number;
    danger?: number;
  };
  size?: 'sm' | 'md' | 'lg';
  showTicks?: boolean;
}

export default function CircularGauge({
  value,
  min,
  max,
  label,
  unit,
  quality = QUALITY_GOOD,
  thresholds,
  size = 'md',
  showTicks = true,
}: Props) {
  /* Quality check for 5-byte sensor format */
  const isGoodQuality = quality === QUALITY_GOOD;
  const isUncertainQuality = quality === QUALITY_UNCERTAIN;
  const isBadQuality = quality === QUALITY_BAD;
  const isNotConnected = quality === QUALITY_NOT_CONNECTED;

  /* Get quality indicator per ISA-101 */
  const getQualityIndicator = () => {
    if (isGoodQuality) return null;
    if (isUncertainQuality) return '?';
    if (isBadQuality) return 'X';
    if (isNotConnected) return '-';
    return '!';
  };
  const dimensions = useMemo(() => {
    switch (size) {
      case 'sm': return { width: 120, strokeWidth: 8, fontSize: 18, labelSize: 10 };
      case 'lg': return { width: 200, strokeWidth: 14, fontSize: 32, labelSize: 14 };
      default: return { width: 160, strokeWidth: 12, fontSize: 26, labelSize: 12 };
    }
  }, [size]);

  const { width, strokeWidth, fontSize, labelSize } = dimensions;
  const radius = (width - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const arcLength = circumference * 0.75; // 270 degrees

  const normalizedValue = Math.max(min, Math.min(max, value));
  const percentage = (normalizedValue - min) / (max - min);
  const offset = arcLength - (percentage * arcLength);

  const getColor = () => {
    /* Override color for bad quality */
    if (!isGoodQuality) {
      if (isUncertainQuality) return '#f59e0b'; /* Yellow for uncertain */
      return '#ef4444'; /* Red for bad/not connected */
    }
    if (thresholds?.danger && value >= thresholds.danger) return '#ef4444';
    if (thresholds?.warning && value >= thresholds.warning) return '#f59e0b';
    return '#10b981';
  };

  const color = getColor();

  // Generate tick marks
  const ticks = useMemo(() => {
    if (!showTicks) return [];
    const tickCount = 9;
    const startAngle = 135;
    const endAngle = 405;
    const angleRange = endAngle - startAngle;

    return Array.from({ length: tickCount }, (_, i) => {
      const angle = startAngle + (angleRange / (tickCount - 1)) * i;
      const radian = (angle * Math.PI) / 180;
      const innerRadius = radius - 8;
      const outerRadius = radius + 2;

      const x1 = width / 2 + Math.cos(radian) * innerRadius;
      const y1 = width / 2 + Math.sin(radian) * innerRadius;
      const x2 = width / 2 + Math.cos(radian) * outerRadius;
      const y2 = width / 2 + Math.sin(radian) * outerRadius;

      const tickValue = min + ((max - min) / (tickCount - 1)) * i;

      return { x1, y1, x2, y2, value: tickValue, angle };
    });
  }, [width, radius, min, max, showTicks]);

  return (
    <div className="relative inline-flex flex-col items-center">
      <svg width={width} height={width} viewBox={`0 0 ${width} ${width}`}>
        <defs>
          <linearGradient id={`gauge-gradient-${label.replace(/\s/g, '')}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={color} stopOpacity="0.8" />
            <stop offset="100%" stopColor={color} stopOpacity="1" />
          </linearGradient>
          <filter id={`gauge-glow-${label.replace(/\s/g, '')}`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="innerShadow">
            <feOffset dx="0" dy="2" />
            <feGaussianBlur stdDeviation="2" result="offset-blur" />
            <feComposite operator="out" in="SourceGraphic" in2="offset-blur" result="inverse" />
            <feFlood floodColor="black" floodOpacity="0.3" result="color" />
            <feComposite operator="in" in="color" in2="inverse" result="shadow" />
            <feComposite operator="over" in="shadow" in2="SourceGraphic" />
          </filter>
        </defs>

        {/* Background circle */}
        <circle
          cx={width / 2}
          cy={width / 2}
          r={radius}
          fill="none"
          stroke="rgba(30, 41, 59, 0.8)"
          strokeWidth={strokeWidth + 4}
          strokeDasharray={arcLength}
          strokeDashoffset={0}
          strokeLinecap="round"
          transform={`rotate(135 ${width / 2} ${width / 2})`}
        />

        {/* Track */}
        <circle
          cx={width / 2}
          cy={width / 2}
          r={radius}
          fill="none"
          stroke="rgba(71, 85, 105, 0.4)"
          strokeWidth={strokeWidth}
          strokeDasharray={arcLength}
          strokeDashoffset={0}
          strokeLinecap="round"
          transform={`rotate(135 ${width / 2} ${width / 2})`}
        />

        {/* Value arc */}
        <circle
          cx={width / 2}
          cy={width / 2}
          r={radius}
          fill="none"
          stroke={`url(#gauge-gradient-${label.replace(/\s/g, '')})`}
          strokeWidth={strokeWidth}
          strokeDasharray={arcLength}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(135 ${width / 2} ${width / 2})`}
          filter={`url(#gauge-glow-${label.replace(/\s/g, '')})`}
          className="transition-all duration-500 ease-out"
        />

        {/* Tick marks */}
        {showTicks && ticks.map((tick, i) => (
          <g key={i}>
            <line
              x1={tick.x1}
              y1={tick.y1}
              x2={tick.x2}
              y2={tick.y2}
              stroke="rgba(148, 163, 184, 0.5)"
              strokeWidth={1.5}
            />
          </g>
        ))}

        {/* Center circle */}
        <circle
          cx={width / 2}
          cy={width / 2}
          r={radius - strokeWidth - 8}
          fill="rgba(15, 23, 42, 0.9)"
          filter="url(#innerShadow)"
        />

        {/* Value display */}
        <text
          x={width / 2}
          y={width / 2 - 5}
          textAnchor="middle"
          dominantBaseline="middle"
          fill={color}
          fontSize={fontSize}
          fontWeight="bold"
          fontFamily="JetBrains Mono, monospace"
          style={{ textShadow: `0 0 20px ${color}` }}
        >
          {typeof value === 'number' ? value.toFixed(1) : '--'}
        </text>

        {/* Unit */}
        <text
          x={width / 2}
          y={width / 2 + fontSize / 2 + 5}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="#64748b"
          fontSize={labelSize}
        >
          {unit}
        </text>

        {/* Min/Max labels */}
        <text
          x={strokeWidth + 10}
          y={width - 10}
          textAnchor="start"
          fill="#475569"
          fontSize={10}
        >
          {min}
        </text>
        <text
          x={width - strokeWidth - 10}
          y={width - 10}
          textAnchor="end"
          fill="#475569"
          fontSize={10}
        >
          {max}
        </text>
      </svg>

      {/* Label */}
      <div className="mt-2 text-center">
        <span
          className="text-sm font-medium"
          style={{ color: '#94a3b8' }}
        >
          {label}
        </span>
        {/* Quality indicator per ISA-101 */}
        {!isGoodQuality && (
          <span
            className={`ml-1 text-sm font-bold ${isUncertainQuality ? 'text-yellow-500' : 'text-red-500'}`}
            title={isUncertainQuality ? 'Uncertain quality' : isBadQuality ? 'Bad quality' : isNotConnected ? 'Not connected' : 'Unknown quality'}
          >
            {getQualityIndicator()}
          </span>
        )}
      </div>
    </div>
  );
}
