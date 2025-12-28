'use client';

import { useState, useCallback } from 'react';
import { ISA101_COLORS } from '@/constants';

export type RtuState = 'OFFLINE' | 'CONNECTING' | 'DISCOVERY' | 'RUNNING' | 'ERROR';

interface RtuStateConfig {
  color: string;
  bgColor: string;
  borderColor: string;
  label: string;
  icon: 'circle' | 'pulse' | 'error';
  glowColor: string;
}

// Helper to create rgba color with opacity
const withOpacity = (hex: string, opacity: number): string => {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
};

const STATE_CONFIG: Record<RtuState, RtuStateConfig> = {
  OFFLINE: {
    color: ISA101_COLORS.states.offline,
    bgColor: withOpacity(ISA101_COLORS.states.offline, 0.2),
    borderColor: withOpacity(ISA101_COLORS.states.offline, 0.4),
    label: 'Offline',
    icon: 'circle',
    glowColor: withOpacity(ISA101_COLORS.states.offline, 0.3),
  },
  CONNECTING: {
    color: ISA101_COLORS.states.connecting,
    bgColor: withOpacity(ISA101_COLORS.states.connecting, 0.2),
    borderColor: withOpacity(ISA101_COLORS.states.connecting, 0.4),
    label: 'Connecting',
    icon: 'pulse',
    glowColor: withOpacity(ISA101_COLORS.states.connecting, 0.4),
  },
  DISCOVERY: {
    color: ISA101_COLORS.states.discovery,
    bgColor: withOpacity(ISA101_COLORS.states.discovery, 0.2),
    borderColor: withOpacity(ISA101_COLORS.states.discovery, 0.4),
    label: 'Discovering',
    icon: 'pulse',
    glowColor: withOpacity(ISA101_COLORS.states.discovery, 0.4),
  },
  RUNNING: {
    color: ISA101_COLORS.states.running,
    bgColor: withOpacity(ISA101_COLORS.states.running, 0.2),
    borderColor: withOpacity(ISA101_COLORS.states.running, 0.4),
    label: 'Running',
    icon: 'circle',
    glowColor: withOpacity(ISA101_COLORS.states.running, 0.4),
  },
  ERROR: {
    color: ISA101_COLORS.states.error,
    bgColor: withOpacity(ISA101_COLORS.states.error, 0.2),
    borderColor: withOpacity(ISA101_COLORS.states.error, 0.4),
    label: 'Error',
    icon: 'error',
    glowColor: withOpacity(ISA101_COLORS.states.error, 0.4),
  },
};

interface ActionConfig {
  label: string;
  variant: 'primary' | 'warning' | 'danger' | 'secondary';
  action: 'connect' | 'disconnect' | 'retry' | 'cancel' | 'edit' | 'delete' | 'view' | 'configure';
}

function getAvailableActions(state: RtuState): ActionConfig[] {
  switch (state) {
    case 'OFFLINE':
      return [
        { label: 'Connect', variant: 'primary', action: 'connect' },
        { label: 'Edit', variant: 'secondary', action: 'edit' },
        { label: 'Delete', variant: 'danger', action: 'delete' },
      ];
    case 'CONNECTING':
    case 'DISCOVERY':
      return [
        { label: 'Cancel', variant: 'warning', action: 'cancel' },
      ];
    case 'RUNNING':
      return [
        { label: 'Disconnect', variant: 'warning', action: 'disconnect' },
        { label: 'View', variant: 'secondary', action: 'view' },
        { label: 'Configure', variant: 'secondary', action: 'configure' },
      ];
    case 'ERROR':
      return [
        { label: 'Retry', variant: 'primary', action: 'retry' },
        { label: 'View Error', variant: 'secondary', action: 'view' },
        { label: 'Disconnect', variant: 'warning', action: 'disconnect' },
      ];
    default:
      return [];
  }
}

interface Props {
  state: RtuState | string;
  stationName: string;
  errorMessage?: string;
  onConnect?: () => void | Promise<void>;
  onDisconnect?: () => void | Promise<void>;
  onRetry?: () => void | Promise<void>;
  onCancel?: () => void | Promise<void>;
  onEdit?: () => void;
  onDelete?: () => void;
  onView?: () => void;
  onConfigure?: () => void;
  size?: 'sm' | 'md' | 'lg';
  showActions?: boolean;
  showLabel?: boolean;
}

export default function RtuStateIndicator({
  state: rawState,
  stationName,
  errorMessage,
  onConnect,
  onDisconnect,
  onRetry,
  onCancel,
  onEdit,
  onDelete,
  onView,
  onConfigure,
  size = 'md',
  showActions = true,
  showLabel = true,
}: Props) {
  const [loading, setLoading] = useState<string | null>(null);

  // Normalize state to RtuState
  const state: RtuState = (rawState?.toUpperCase() as RtuState) || 'OFFLINE';
  const config = STATE_CONFIG[state] || STATE_CONFIG.OFFLINE;
  const actions = getAvailableActions(state);

  const handleAction = useCallback(async (action: ActionConfig['action']) => {
    const handlers: Record<string, (() => void | Promise<void>) | undefined> = {
      connect: onConnect,
      disconnect: onDisconnect,
      retry: onRetry,
      cancel: onCancel,
      edit: onEdit,
      delete: onDelete,
      view: onView,
      configure: onConfigure,
    };

    const handler = handlers[action];
    if (!handler) return;

    setLoading(action);
    try {
      await handler();
    } finally {
      setLoading(null);
    }
  }, [onConnect, onDisconnect, onRetry, onCancel, onEdit, onDelete, onView, onConfigure]);

  const getButtonClasses = (variant: ActionConfig['variant'], isLoading: boolean) => {
    const base = 'px-3 py-1.5 rounded text-sm font-medium transition-all disabled:opacity-50';
    const variants = {
      primary: 'bg-blue-600 hover:bg-blue-500 text-white',
      warning: 'bg-amber-600 hover:bg-amber-500 text-white',
      danger: 'bg-red-600 hover:bg-red-500 text-white',
      secondary: 'bg-gray-700 hover:bg-gray-600 text-white',
    };
    return `${base} ${variants[variant]} ${isLoading ? 'opacity-70 cursor-wait' : ''}`;
  };

  const sizeConfig = {
    sm: { indicator: 'w-2 h-2', text: 'text-xs', gap: 'gap-1.5' },
    md: { indicator: 'w-3 h-3', text: 'text-sm', gap: 'gap-2' },
    lg: { indicator: 'w-4 h-4', text: 'text-base', gap: 'gap-3' },
  };

  const sizeStyles = sizeConfig[size];

  const renderIcon = () => {
    if (config.icon === 'error') {
      return (
        <div
          className={`${sizeStyles.indicator} rounded-full flex items-center justify-center`}
          style={{ backgroundColor: config.color }}
        >
          <span className="text-white text-xs font-bold">×</span>
        </div>
      );
    }

    const pulseAnimation = config.icon === 'pulse' ? 'animate-pulse' : '';

    return (
      <div
        className={`${sizeStyles.indicator} rounded-full ${pulseAnimation}`}
        style={{
          backgroundColor: config.color,
          boxShadow: `0 0 8px ${config.glowColor}`,
        }}
      />
    );
  };

  return (
    <div className="flex flex-col gap-2">
      {/* State Display */}
      <div className={`flex items-center ${sizeStyles.gap}`}>
        {renderIcon()}
        {showLabel && (
          <div className="flex flex-col">
            <span
              className={`${sizeStyles.text} font-medium`}
              style={{ color: config.color }}
            >
              {config.label}
            </span>
            {state === 'ERROR' && errorMessage && (
              <span className="text-xs text-gray-400 max-w-xs truncate" title={errorMessage}>
                {errorMessage}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      {showActions && actions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {actions.map((action) => {
            const isLoading = loading === action.action;
            const isDisabled = loading !== null;

            return (
              <button
                key={action.action}
                onClick={() => handleAction(action.action)}
                disabled={isDisabled}
                className={getButtonClasses(action.variant, isLoading)}
              >
                {isLoading ? (
                  <span className="flex items-center gap-1">
                    <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                        fill="none"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                      />
                    </svg>
                    {action.label}
                  </span>
                ) : (
                  action.label
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Export a compact badge variant
export function RtuStateBadge({
  state: rawState,
  size = 'sm',
}: {
  state: RtuState | string;
  size?: 'sm' | 'md';
}) {
  const state: RtuState = (rawState?.toUpperCase() as RtuState) || 'OFFLINE';
  const config = STATE_CONFIG[state] || STATE_CONFIG.OFFLINE;

  const sizeStyles = size === 'sm'
    ? 'px-2 py-0.5 text-xs'
    : 'px-2.5 py-1 text-sm';

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ${sizeStyles}`}
      style={{
        backgroundColor: config.bgColor,
        color: config.color,
        border: `1px solid ${config.borderColor}`,
      }}
    >
      <span
        className={`${size === 'sm' ? 'w-1.5 h-1.5' : 'w-2 h-2'} rounded-full ${config.icon === 'pulse' ? 'animate-pulse' : ''}`}
        style={{ backgroundColor: config.color }}
      />
      {config.label}
    </span>
  );
}
