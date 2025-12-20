'use client';

import { useMemo } from 'react';

interface SensorData {
  slot: number;
  name: string;
  value: number;
  unit: string;
  quality: string;
}

interface ActuatorData {
  slot: number;
  name: string;
  state: 'ON' | 'OFF' | 'PWM';
  pwm_duty?: number;
}

interface Props {
  sensors: SensorData[];
  actuators?: ActuatorData[];
  tankLevel?: number;
  phValue?: number;
  tdsValue?: number;
  turbidity?: number;
  temperature?: number;
  flowRate?: number;
  pump1Running?: boolean;
  pump2Running?: boolean;
  valveOpen?: boolean;
}

export default function ProcessDiagram({
  sensors = [],
  actuators = [],
  tankLevel = 65,
  phValue,
  tdsValue,
  turbidity,
  temperature,
  flowRate,
  pump1Running = false,
  pump2Running = false,
  valveOpen = true,
}: Props) {
  // Extract values from sensors if available
  const sensorValues = useMemo(() => {
    const getValue = (namePattern: string) => {
      const sensor = sensors.find(s =>
        s.name.toLowerCase().includes(namePattern.toLowerCase())
      );
      return sensor?.value;
    };

    return {
      level: getValue('level') ?? tankLevel,
      ph: getValue('ph') ?? phValue ?? 7.2,
      tds: getValue('tds') ?? tdsValue ?? 450,
      turbidity: getValue('turbidity') ?? turbidity ?? 2.5,
      temperature: getValue('temp') ?? temperature ?? 22.5,
      flow: getValue('flow') ?? flowRate ?? 125.5,
    };
  }, [sensors, tankLevel, phValue, tdsValue, turbidity, temperature, flowRate]);

  // Derive pump states from actuators if available
  const pumpStates = useMemo(() => {
    const pump1 = actuators.find(a => a.name.toLowerCase().includes('pump') && a.slot === 9);
    const pump2 = actuators.find(a => a.name.toLowerCase().includes('pump') && a.slot === 10);
    const valve = actuators.find(a => a.name.toLowerCase().includes('valve'));

    return {
      pump1: pump1?.state === 'ON' || pump1Running,
      pump2: pump2?.state === 'ON' || pump2Running,
      valve: valve?.state === 'ON' ?? valveOpen,
    };
  }, [actuators, pump1Running, pump2Running, valveOpen]);

  const getQualityColor = (value: number, type: 'ph' | 'tds' | 'turbidity') => {
    switch (type) {
      case 'ph':
        if (value >= 6.5 && value <= 8.5) return '#10b981';
        if (value >= 6.0 && value <= 9.0) return '#f59e0b';
        return '#ef4444';
      case 'tds':
        if (value < 300) return '#10b981';
        if (value < 600) return '#f59e0b';
        return '#ef4444';
      case 'turbidity':
        if (value < 4) return '#10b981';
        if (value < 10) return '#f59e0b';
        return '#ef4444';
      default:
        return '#38bdf8';
    }
  };

  return (
    <div className="mimic-container p-6">
      <svg viewBox="0 0 800 450" className="w-full h-auto">
        <defs>
          {/* Gradients */}
          <linearGradient id="tankGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#1e293b" />
            <stop offset="100%" stopColor="#0f172a" />
          </linearGradient>
          <linearGradient id="waterGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.9" />
            <stop offset="50%" stopColor="#0ea5e9" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#0284c7" stopOpacity="0.95" />
          </linearGradient>
          <linearGradient id="pipeGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#475569" />
            <stop offset="50%" stopColor="#64748b" />
            <stop offset="100%" stopColor="#475569" />
          </linearGradient>
          <linearGradient id="pumpGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#1d4ed8" />
          </linearGradient>
          <linearGradient id="pumpOffGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#475569" />
            <stop offset="100%" stopColor="#334155" />
          </linearGradient>

          {/* Glow filters */}
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="waterGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Wave pattern for water surface */}
          <pattern id="wavePattern" x="0" y="0" width="40" height="10" patternUnits="userSpaceOnUse">
            <path
              d="M0 5 Q10 0, 20 5 T40 5"
              fill="none"
              stroke="rgba(255,255,255,0.3)"
              strokeWidth="2"
            >
              <animate
                attributeName="d"
                values="M0 5 Q10 0, 20 5 T40 5;M0 5 Q10 10, 20 5 T40 5;M0 5 Q10 0, 20 5 T40 5"
                dur="2s"
                repeatCount="indefinite"
              />
            </path>
          </pattern>
        </defs>

        {/* Title */}
        <text x="400" y="30" textAnchor="middle" fill="#94a3b8" fontSize="18" fontWeight="600">
          Water Treatment Process Overview
        </text>

        {/* === INTAKE SECTION === */}
        <g transform="translate(50, 80)">
          {/* Raw Water Tank */}
          <rect x="0" y="0" width="120" height="180" rx="8" fill="url(#tankGradient)" stroke="#38bdf8" strokeWidth="2" opacity="0.8" />

          {/* Water in tank */}
          <rect
            x="4"
            y={180 - (sensorValues.level * 1.72)}
            width="112"
            height={sensorValues.level * 1.72}
            rx="4"
            fill="url(#waterGradient)"
            filter="url(#waterGlow)"
          >
            <animate
              attributeName="height"
              values={`${sensorValues.level * 1.72};${sensorValues.level * 1.72 + 3};${sensorValues.level * 1.72}`}
              dur="3s"
              repeatCount="indefinite"
            />
          </rect>

          {/* Wave surface */}
          <rect
            x="4"
            y={180 - (sensorValues.level * 1.72) - 5}
            width="112"
            height="10"
            fill="url(#wavePattern)"
            opacity="0.8"
          />

          {/* Tank label */}
          <text x="60" y="-10" textAnchor="middle" fill="#94a3b8" fontSize="12" fontWeight="500">
            RAW WATER
          </text>

          {/* Level indicator */}
          <text x="60" y="100" textAnchor="middle" fill="white" fontSize="28" fontWeight="bold" filter="url(#glow)">
            {sensorValues.level.toFixed(1)}%
          </text>
          <text x="60" y="120" textAnchor="middle" fill="#64748b" fontSize="11">
            LEVEL
          </text>
        </g>

        {/* === PIPE FROM RAW TO PUMP 1 === */}
        <g>
          <rect x="170" y="160" width="60" height="12" fill="url(#pipeGradient)" rx="2" />
          {pumpStates.pump1 && (
            <line x1="175" y1="166" x2="225" y2="166" stroke="#38bdf8" strokeWidth="4" className="flow-line" strokeLinecap="round" />
          )}
        </g>

        {/* === PUMP 1 === */}
        <g transform="translate(230, 130)">
          <circle
            cx="35"
            cy="35"
            r="30"
            fill={pumpStates.pump1 ? 'url(#pumpGradient)' : 'url(#pumpOffGradient)'}
            stroke={pumpStates.pump1 ? '#60a5fa' : '#475569'}
            strokeWidth="3"
            filter={pumpStates.pump1 ? 'url(#glow)' : undefined}
          />

          {/* Pump impeller */}
          <g transform="translate(35, 35)">
            <g className={pumpStates.pump1 ? 'pump-icon running' : ''}>
              <line x1="-15" y1="0" x2="15" y2="0" stroke="white" strokeWidth="3" strokeLinecap="round" />
              <line x1="0" y1="-15" x2="0" y2="15" stroke="white" strokeWidth="3" strokeLinecap="round" />
              <line x1="-10" y1="-10" x2="10" y2="10" stroke="white" strokeWidth="3" strokeLinecap="round" />
              <line x1="-10" y1="10" x2="10" y2="-10" stroke="white" strokeWidth="3" strokeLinecap="round" />
            </g>
          </g>

          <text x="35" y="85" textAnchor="middle" fill="#94a3b8" fontSize="11">PUMP 1</text>
          <text x="35" y="100" textAnchor="middle" fill={pumpStates.pump1 ? '#10b981' : '#ef4444'} fontSize="10" fontWeight="600">
            {pumpStates.pump1 ? 'RUNNING' : 'STOPPED'}
          </text>
        </g>

        {/* === PIPE FROM PUMP 1 TO TREATMENT TANK === */}
        <g>
          <rect x="300" y="160" width="80" height="12" fill="url(#pipeGradient)" rx="2" />
          {pumpStates.pump1 && (
            <line x1="305" y1="166" x2="375" y2="166" stroke="#38bdf8" strokeWidth="4" className="flow-line" strokeLinecap="round" />
          )}
        </g>

        {/* === TREATMENT TANK === */}
        <g transform="translate(380, 60)">
          {/* Main tank body */}
          <rect x="0" y="0" width="160" height="220" rx="10" fill="url(#tankGradient)" stroke="#38bdf8" strokeWidth="2" opacity="0.9" />

          {/* Water level */}
          <rect
            x="5"
            y={220 - (sensorValues.level * 2.1)}
            width="150"
            height={sensorValues.level * 2.1}
            rx="6"
            fill="url(#waterGradient)"
            filter="url(#waterGlow)"
          />

          {/* Tank label */}
          <text x="80" y="-10" textAnchor="middle" fill="#94a3b8" fontSize="13" fontWeight="500">
            TREATMENT TANK
          </text>

          {/* Sensor displays inside tank */}
          <g transform="translate(15, 30)">
            {/* pH */}
            <rect x="0" y="0" width="60" height="45" rx="6" fill="rgba(15,23,42,0.8)" stroke={getQualityColor(sensorValues.ph, 'ph')} strokeWidth="1.5" />
            <text x="30" y="18" textAnchor="middle" fill="#94a3b8" fontSize="9">pH</text>
            <text x="30" y="36" textAnchor="middle" fill={getQualityColor(sensorValues.ph, 'ph')} fontSize="16" fontWeight="bold">
              {sensorValues.ph.toFixed(1)}
            </text>

            {/* TDS */}
            <rect x="70" y="0" width="60" height="45" rx="6" fill="rgba(15,23,42,0.8)" stroke={getQualityColor(sensorValues.tds, 'tds')} strokeWidth="1.5" />
            <text x="100" y="18" textAnchor="middle" fill="#94a3b8" fontSize="9">TDS ppm</text>
            <text x="100" y="36" textAnchor="middle" fill={getQualityColor(sensorValues.tds, 'tds')} fontSize="16" fontWeight="bold">
              {sensorValues.tds.toFixed(0)}
            </text>
          </g>

          <g transform="translate(15, 85)">
            {/* Turbidity */}
            <rect x="0" y="0" width="60" height="45" rx="6" fill="rgba(15,23,42,0.8)" stroke={getQualityColor(sensorValues.turbidity, 'turbidity')} strokeWidth="1.5" />
            <text x="30" y="18" textAnchor="middle" fill="#94a3b8" fontSize="9">NTU</text>
            <text x="30" y="36" textAnchor="middle" fill={getQualityColor(sensorValues.turbidity, 'turbidity')} fontSize="16" fontWeight="bold">
              {sensorValues.turbidity.toFixed(1)}
            </text>

            {/* Temperature */}
            <rect x="70" y="0" width="60" height="45" rx="6" fill="rgba(15,23,42,0.8)" stroke="#38bdf8" strokeWidth="1.5" />
            <text x="100" y="18" textAnchor="middle" fill="#94a3b8" fontSize="9">TEMP °C</text>
            <text x="100" y="36" textAnchor="middle" fill="#38bdf8" fontSize="16" fontWeight="bold">
              {sensorValues.temperature.toFixed(1)}
            </text>
          </g>
        </g>

        {/* === PIPE FROM TREATMENT TANK TO PUMP 2 === */}
        <g>
          <rect x="540" y="160" width="60" height="12" fill="url(#pipeGradient)" rx="2" />
          {pumpStates.pump2 && (
            <line x1="545" y1="166" x2="595" y2="166" stroke="#38bdf8" strokeWidth="4" className="flow-line" strokeLinecap="round" />
          )}
        </g>

        {/* === PUMP 2 === */}
        <g transform="translate(600, 130)">
          <circle
            cx="35"
            cy="35"
            r="30"
            fill={pumpStates.pump2 ? 'url(#pumpGradient)' : 'url(#pumpOffGradient)'}
            stroke={pumpStates.pump2 ? '#60a5fa' : '#475569'}
            strokeWidth="3"
            filter={pumpStates.pump2 ? 'url(#glow)' : undefined}
          />

          {/* Pump impeller */}
          <g transform="translate(35, 35)">
            <g className={pumpStates.pump2 ? 'pump-icon running' : ''}>
              <line x1="-15" y1="0" x2="15" y2="0" stroke="white" strokeWidth="3" strokeLinecap="round" />
              <line x1="0" y1="-15" x2="0" y2="15" stroke="white" strokeWidth="3" strokeLinecap="round" />
              <line x1="-10" y1="-10" x2="10" y2="10" stroke="white" strokeWidth="3" strokeLinecap="round" />
              <line x1="-10" y1="10" x2="10" y2="-10" stroke="white" strokeWidth="3" strokeLinecap="round" />
            </g>
          </g>

          <text x="35" y="85" textAnchor="middle" fill="#94a3b8" fontSize="11">PUMP 2</text>
          <text x="35" y="100" textAnchor="middle" fill={pumpStates.pump2 ? '#10b981' : '#ef4444'} fontSize="10" fontWeight="600">
            {pumpStates.pump2 ? 'RUNNING' : 'STOPPED'}
          </text>
        </g>

        {/* === PIPE TO OUTLET WITH VALVE === */}
        <g>
          <rect x="670" y="160" width="80" height="12" fill="url(#pipeGradient)" rx="2" />
          {pumpStates.pump2 && pumpStates.valve && (
            <line x1="675" y1="166" x2="745" y2="166" stroke="#38bdf8" strokeWidth="4" className="flow-line" strokeLinecap="round" />
          )}
        </g>

        {/* === OUTLET VALVE === */}
        <g transform="translate(720, 140)">
          <polygon
            points="15,0 30,20 30,40 15,60 0,40 0,20"
            fill={pumpStates.valve ? '#10b981' : '#ef4444'}
            stroke={pumpStates.valve ? '#34d399' : '#f87171'}
            strokeWidth="2"
            filter="url(#glow)"
          />
          <text x="15" y="75" textAnchor="middle" fill="#94a3b8" fontSize="10">VALVE</text>
          <text x="15" y="88" textAnchor="middle" fill={pumpStates.valve ? '#10b981' : '#ef4444'} fontSize="9" fontWeight="600">
            {pumpStates.valve ? 'OPEN' : 'CLOSED'}
          </text>
        </g>

        {/* === FLOW METER === */}
        <g transform="translate(350, 320)">
          <rect x="0" y="0" width="100" height="60" rx="8" fill="rgba(15,23,42,0.9)" stroke="#8b5cf6" strokeWidth="2" />
          <text x="50" y="18" textAnchor="middle" fill="#94a3b8" fontSize="10">FLOW RATE</text>
          <text x="50" y="42" textAnchor="middle" fill="#8b5cf6" fontSize="22" fontWeight="bold" filter="url(#glow)">
            {sensorValues.flow.toFixed(1)}
          </text>
          <text x="50" y="55" textAnchor="middle" fill="#64748b" fontSize="9">L/min</text>
        </g>

        {/* === LEGEND === */}
        <g transform="translate(50, 400)">
          <rect x="0" y="0" width="700" height="40" rx="8" fill="rgba(15,23,42,0.6)" />

          <g transform="translate(20, 20)">
            <circle cx="0" cy="0" r="6" fill="#10b981" />
            <text x="15" y="4" fill="#94a3b8" fontSize="11">Normal</text>
          </g>

          <g transform="translate(100, 20)">
            <circle cx="0" cy="0" r="6" fill="#f59e0b" />
            <text x="15" y="4" fill="#94a3b8" fontSize="11">Warning</text>
          </g>

          <g transform="translate(190, 20)">
            <circle cx="0" cy="0" r="6" fill="#ef4444" />
            <text x="15" y="4" fill="#94a3b8" fontSize="11">Alarm</text>
          </g>

          <g transform="translate(300, 20)">
            <rect x="-10" y="-6" width="20" height="12" rx="2" fill="url(#pipeGradient)" />
            <text x="25" y="4" fill="#94a3b8" fontSize="11">Pipe</text>
          </g>

          <g transform="translate(380, 20)">
            <line x1="-10" y1="0" x2="10" y2="0" stroke="#38bdf8" strokeWidth="3" strokeDasharray="4 4" />
            <text x="25" y="4" fill="#94a3b8" fontSize="11">Flow</text>
          </g>

          <g transform="translate(460, 20)">
            <circle cx="0" cy="0" r="8" fill="url(#pumpGradient)" />
            <text x="18" y="4" fill="#94a3b8" fontSize="11">Pump Running</text>
          </g>

          <g transform="translate(590, 20)">
            <circle cx="0" cy="0" r="8" fill="url(#pumpOffGradient)" />
            <text x="18" y="4" fill="#94a3b8" fontSize="11">Pump Stopped</text>
          </g>
        </g>
      </svg>
    </div>
  );
}
