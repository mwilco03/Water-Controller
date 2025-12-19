'use client';

interface Props {
  level: number;
  label: string;
  capacity?: number;
  unit?: string;
  showWarnings?: boolean;
  lowThreshold?: number;
  highThreshold?: number;
  width?: number;
  height?: number;
}

export default function TankLevel({
  level,
  label,
  capacity,
  unit = '%',
  showWarnings = true,
  lowThreshold = 20,
  highThreshold = 90,
  width = 100,
  height = 180,
}: Props) {
  const normalizedLevel = Math.max(0, Math.min(100, level));

  const getStatusColor = () => {
    if (normalizedLevel <= lowThreshold) return { main: '#ef4444', glow: 'rgba(239, 68, 68, 0.5)' };
    if (normalizedLevel >= highThreshold) return { main: '#f59e0b', glow: 'rgba(245, 158, 11, 0.5)' };
    return { main: '#10b981', glow: 'rgba(16, 185, 129, 0.5)' };
  };

  const status = getStatusColor();
  const waterHeight = (normalizedLevel / 100) * (height - 40);
  const tankWidth = width - 20;
  const tankHeight = height - 40;

  return (
    <div className="flex flex-col items-center">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          {/* Water gradient */}
          <linearGradient id={`water-${label.replace(/\s/g, '')}`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.85" />
            <stop offset="30%" stopColor="#0ea5e9" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#0284c7" stopOpacity="0.95" />
          </linearGradient>

          {/* Tank gradient */}
          <linearGradient id={`tank-${label.replace(/\s/g, '')}`} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#1e293b" />
            <stop offset="50%" stopColor="#334155" />
            <stop offset="100%" stopColor="#1e293b" />
          </linearGradient>

          {/* Glow effect */}
          <filter id={`glow-${label.replace(/\s/g, '')}`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Wave clip path */}
          <clipPath id={`tank-clip-${label.replace(/\s/g, '')}`}>
            <rect
              x={10}
              y={20}
              width={tankWidth}
              height={tankHeight}
              rx={8}
            />
          </clipPath>
        </defs>

        {/* Tank body */}
        <rect
          x={10}
          y={20}
          width={tankWidth}
          height={tankHeight}
          rx={8}
          fill={`url(#tank-${label.replace(/\s/g, '')})`}
          stroke="rgba(56, 189, 248, 0.3)"
          strokeWidth={2}
        />

        {/* Water fill */}
        <g clipPath={`url(#tank-clip-${label.replace(/\s/g, '')})`}>
          <rect
            x={12}
            y={20 + tankHeight - waterHeight}
            width={tankWidth - 4}
            height={waterHeight}
            fill={`url(#water-${label.replace(/\s/g, '')})`}
            className="transition-all duration-500 ease-out"
          />

          {/* Wave effect on top */}
          <path
            d={`M12 ${20 + tankHeight - waterHeight}
                Q${10 + tankWidth * 0.25} ${18 + tankHeight - waterHeight},
                 ${10 + tankWidth * 0.5} ${20 + tankHeight - waterHeight}
                T${tankWidth + 8} ${20 + tankHeight - waterHeight}`}
            fill="rgba(255,255,255,0.2)"
          >
            <animate
              attributeName="d"
              values={`M12 ${20 + tankHeight - waterHeight}
                       Q${10 + tankWidth * 0.25} ${18 + tankHeight - waterHeight},
                        ${10 + tankWidth * 0.5} ${20 + tankHeight - waterHeight}
                       T${tankWidth + 8} ${20 + tankHeight - waterHeight};
                       M12 ${20 + tankHeight - waterHeight}
                       Q${10 + tankWidth * 0.25} ${22 + tankHeight - waterHeight},
                        ${10 + tankWidth * 0.5} ${20 + tankHeight - waterHeight}
                       T${tankWidth + 8} ${20 + tankHeight - waterHeight};
                       M12 ${20 + tankHeight - waterHeight}
                       Q${10 + tankWidth * 0.25} ${18 + tankHeight - waterHeight},
                        ${10 + tankWidth * 0.5} ${20 + tankHeight - waterHeight}
                       T${tankWidth + 8} ${20 + tankHeight - waterHeight}`}
              dur="3s"
              repeatCount="indefinite"
            />
          </path>

          {/* Bubbles */}
          {normalizedLevel > 10 && (
            <>
              <circle r="3" fill="rgba(255,255,255,0.3)">
                <animate
                  attributeName="cx"
                  values={`${20};${25};${20}`}
                  dur="4s"
                  repeatCount="indefinite"
                />
                <animate
                  attributeName="cy"
                  values={`${20 + tankHeight - 10};${20 + tankHeight - waterHeight + 10}`}
                  dur="4s"
                  repeatCount="indefinite"
                />
                <animate
                  attributeName="opacity"
                  values="0.3;0.5;0"
                  dur="4s"
                  repeatCount="indefinite"
                />
              </circle>
              <circle r="2" fill="rgba(255,255,255,0.4)">
                <animate
                  attributeName="cx"
                  values={`${tankWidth - 10};${tankWidth - 15};${tankWidth - 10}`}
                  dur="3s"
                  repeatCount="indefinite"
                />
                <animate
                  attributeName="cy"
                  values={`${20 + tankHeight - 10};${20 + tankHeight - waterHeight + 10}`}
                  dur="3s"
                  repeatCount="indefinite"
                />
                <animate
                  attributeName="opacity"
                  values="0.4;0.6;0"
                  dur="3s"
                  repeatCount="indefinite"
                />
              </circle>
            </>
          )}
        </g>

        {/* Level markers */}
        {[0, 25, 50, 75, 100].map((mark) => (
          <g key={mark}>
            <line
              x1={tankWidth + 12}
              y1={20 + tankHeight - (mark / 100) * tankHeight}
              x2={tankWidth + 18}
              y2={20 + tankHeight - (mark / 100) * tankHeight}
              stroke="rgba(148, 163, 184, 0.5)"
              strokeWidth={1}
            />
            <text
              x={tankWidth + 22}
              y={20 + tankHeight - (mark / 100) * tankHeight + 4}
              fill="#64748b"
              fontSize={8}
            >
              {mark}
            </text>
          </g>
        ))}

        {/* Warning/threshold lines */}
        {showWarnings && (
          <>
            <line
              x1={12}
              y1={20 + tankHeight - (lowThreshold / 100) * tankHeight}
              x2={tankWidth + 8}
              y2={20 + tankHeight - (lowThreshold / 100) * tankHeight}
              stroke="#ef4444"
              strokeWidth={1}
              strokeDasharray="4 2"
              opacity={0.6}
            />
            <line
              x1={12}
              y1={20 + tankHeight - (highThreshold / 100) * tankHeight}
              x2={tankWidth + 8}
              y2={20 + tankHeight - (highThreshold / 100) * tankHeight}
              stroke="#f59e0b"
              strokeWidth={1}
              strokeDasharray="4 2"
              opacity={0.6}
            />
          </>
        )}

        {/* Level value display */}
        <text
          x={width / 2 - 5}
          y={height - 10}
          textAnchor="middle"
          fill={status.main}
          fontSize={18}
          fontWeight="bold"
          fontFamily="JetBrains Mono, monospace"
          filter={`url(#glow-${label.replace(/\s/g, '')})`}
        >
          {normalizedLevel.toFixed(1)}{unit}
        </text>
      </svg>

      {/* Label */}
      <div className="mt-1 text-center">
        <span className="text-xs text-slate-400 font-medium">{label}</span>
        {capacity && (
          <div className="text-xs text-slate-500">
            {((normalizedLevel / 100) * capacity).toFixed(0)} / {capacity} L
          </div>
        )}
      </div>

      {/* Status indicator */}
      <div
        className="mt-2 px-2 py-0.5 rounded-full text-xs font-medium"
        style={{
          backgroundColor: `${status.main}20`,
          color: status.main,
          border: `1px solid ${status.main}40`,
        }}
      >
        {normalizedLevel <= lowThreshold ? 'LOW' : normalizedLevel >= highThreshold ? 'HIGH' : 'NORMAL'}
      </div>
    </div>
  );
}
