'use client';

import { useState, useCallback } from 'react';
import type { RTUControl } from '@/lib/api';
import { sendControlCommand } from '@/lib/api';
import { controlLogger } from '@/lib/logger';

interface Props {
  control: RTUControl;
  rtuStation: string;
  disabled?: boolean;
  interactive?: boolean; // If false, shows status only (view mode)
  onCommandSent?: () => void;
}

// Confirmation Modal Component
function ConfirmationModal({
  isOpen,
  onConfirm,
  onCancel,
  controlName,
  command,
  value,
}: {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  controlName: string;
  command: string;
  value?: number;
}) {
  if (!isOpen) return null;

  const getCommandDescription = () => {
    switch (command) {
      case 'ON':
        return 'turn ON';
      case 'OFF':
        return 'turn OFF';
      case 'OPEN':
        return 'OPEN';
      case 'CLOSE':
        return 'CLOSE';
      case 'SET':
        return `set to ${value}`;
      case 'PULSE':
        return 'send PULSE';
      default:
        return command;
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4 border border-gray-600">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-yellow-600/20 flex items-center justify-center">
            <svg className="w-6 h-6 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-white">Confirm Control Action</h3>
        </div>

        <p className="text-gray-300 mb-6">
          Are you sure you want to <span className="font-bold text-yellow-400">{getCommandDescription()}</span> the control <span className="font-bold text-white">{controlName}</span>?
        </p>

        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-white rounded font-medium transition-colors"
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ControlWidget({
  control,
  rtuStation,
  disabled = false,
  interactive = true,
  onCommandSent
}: Props) {
  const [loading, setLoading] = useState(false);
  const [sliderValue, setSliderValue] = useState(control.current_value ?? control.range_min ?? 0);
  const [confirmDialog, setConfirmDialog] = useState<{ command: string; value?: number } | null>(null);

  const executeCommand = useCallback(async (command: string, value?: number) => {
    setLoading(true);
    try {
      await sendControlCommand(rtuStation, control.control_id, command, value);
      onCommandSent?.();
    } catch (error) {
      controlLogger.error('Failed to send command', error);
    } finally {
      setLoading(false);
      setConfirmDialog(null);
    }
  }, [rtuStation, control.control_id, onCommandSent]);

  const handleCommand = useCallback((command: string, value?: number) => {
    if (loading || disabled || !interactive) return;
    // Show confirmation dialog
    setConfirmDialog({ command, value });
  }, [loading, disabled, interactive]);

  const handleConfirm = useCallback(() => {
    if (confirmDialog) {
      executeCommand(confirmDialog.command, confirmDialog.value);
    }
  }, [confirmDialog, executeCommand]);

  const handleCancel = useCallback(() => {
    setConfirmDialog(null);
  }, []);

  // Get color based on control state
  const getStateColor = () => {
    switch (control.current_state?.toUpperCase()) {
      case 'ON':
      case 'RUNNING':
      case 'OPEN':
        return '#10b981'; // Green
      case 'OFF':
      case 'STOPPED':
      case 'CLOSED':
        return '#6b7280'; // Gray
      case 'FAULT':
      case 'ERROR':
        return '#ef4444'; // Red
      case 'STARTING':
      case 'STOPPING':
      case 'OPENING':
      case 'CLOSING':
        return '#f59e0b'; // Yellow
      default:
        return '#3b82f6'; // Blue
    }
  };

  // Get icon based on control type
  const getIcon = () => {
    switch (control.control_type) {
      case 'pump':
        return (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83" stroke="currentColor" strokeWidth="2" fill="none" />
          </svg>
        );
      case 'valve':
        return (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2L8 6h8l-4-4zM8 18l4 4 4-4H8zM2 8v8h4V8H2zm16 0v8h4V8h-4zM8 8v8h8V8H8z" />
          </svg>
        );
      case 'motor':
        return (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <rect x="2" y="6" width="20" height="12" rx="2" />
            <circle cx="6" cy="12" r="2" fill="rgba(0,0,0,0.3)" />
            <path d="M10 9h8v6h-8z" fill="rgba(0,0,0,0.2)" />
          </svg>
        );
      case 'heater':
        return (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2a7 7 0 0 0-7 7c0 2.38 1.19 4.47 3 5.74V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.26c1.81-1.27 3-3.36 3-5.74a7 7 0 0 0-7-7zm2 18H10v1a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1v-1z" />
          </svg>
        );
      case 'dosing':
        return (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M6 3v18h12V3H6zm10 16H8v-2h8v2zm0-4H8v-2h8v2zm0-4H8V9h8v2zm0-4H8V5h8v2z" />
          </svg>
        );
      default:
        return (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" />
          </svg>
        );
    }
  };

  const stateColor = getStateColor();
  const isOn = ['ON', 'RUNNING', 'OPEN'].includes(control.current_state?.toUpperCase() ?? '');

  // Render control based on command_type
  const renderControl = () => {
    // In view mode, show status indicator instead of controls
    if (!interactive) {
      return (
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-400">View Mode</span>
          <span className="text-xs text-gray-500 bg-gray-800 px-2 py-1 rounded">
            {control.current_value !== undefined ? `Value: ${control.current_value}` : control.current_state || 'N/A'}
          </span>
        </div>
      );
    }

    switch (control.command_type) {
      case 'on_off':
        return (
          <div className="flex gap-2">
            <button
              className={`px-3 py-1.5 rounded text-sm font-medium transition-all ${
                isOn
                  ? 'bg-green-600 text-white shadow-lg shadow-green-600/30'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
              onClick={() => handleCommand('ON')}
              disabled={loading || disabled || isOn}
            >
              ON
            </button>
            <button
              className={`px-3 py-1.5 rounded text-sm font-medium transition-all ${
                !isOn
                  ? 'bg-red-600 text-white shadow-lg shadow-red-600/30'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
              onClick={() => handleCommand('OFF')}
              disabled={loading || disabled || !isOn}
            >
              OFF
            </button>
          </div>
        );

      case 'open_close':
        return (
          <div className="flex gap-2">
            <button
              className={`px-3 py-1.5 rounded text-sm font-medium transition-all ${
                isOn
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
              onClick={() => handleCommand('OPEN')}
              disabled={loading || disabled}
            >
              OPEN
            </button>
            <button
              className={`px-3 py-1.5 rounded text-sm font-medium transition-all ${
                !isOn
                  ? 'bg-gray-600 text-white'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
              onClick={() => handleCommand('CLOSE')}
              disabled={loading || disabled}
            >
              CLOSE
            </button>
          </div>
        );

      case 'analog':
      case 'pwm':
        const min = control.range_min ?? 0;
        const max = control.range_max ?? 100;
        return (
          <div className="space-y-2 w-full">
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={min}
                max={max}
                value={sliderValue}
                onChange={(e) => setSliderValue(Number(e.target.value))}
                className="flex-1 h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                disabled={loading || disabled}
              />
              <span className="w-12 text-right font-mono text-sm">{sliderValue.toFixed(0)}</span>
            </div>
            <button
              className="w-full px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium transition-all disabled:opacity-50"
              onClick={() => handleCommand('SET', sliderValue)}
              disabled={loading || disabled}
            >
              Apply
            </button>
          </div>
        );

      case 'pulse':
        return (
          <button
            className="px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded text-sm font-medium transition-all disabled:opacity-50"
            onClick={() => handleCommand('PULSE')}
            disabled={loading || disabled}
          >
            PULSE
          </button>
        );

      default:
        return (
          <div className="text-xs text-gray-500">
            Unknown command type: {control.command_type}
          </div>
        );
    }
  };

  return (
    <>
      {/* Confirmation Modal */}
      <ConfirmationModal
        isOpen={confirmDialog !== null}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
        controlName={control.name}
        command={confirmDialog?.command || ''}
        value={confirmDialog?.value}
      />

      <div
        className="rounded-lg p-3 transition-all"
        style={{
          backgroundColor: 'rgba(15, 23, 42, 0.8)',
          border: `1px solid ${stateColor}40`,
          boxShadow: isOn ? `0 0 15px ${stateColor}20` : 'none',
        }}
      >
        {/* Header */}
        <div className="flex items-center gap-2 mb-3">
          <span style={{ color: stateColor }}>{getIcon()}</span>
          <span className="font-medium text-white flex-1 truncate" title={control.name}>
            {control.name}
          </span>
          <span
            className="text-xs px-2 py-0.5 rounded capitalize"
            style={{
              backgroundColor: `${stateColor}20`,
              color: stateColor,
            }}
          >
            {control.current_state || 'Unknown'}
          </span>
        </div>

        {/* Loading overlay */}
        {loading && (
          <div className="flex items-center justify-center py-2">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500" />
          </div>
        )}

        {/* Control */}
        {!loading && renderControl()}

        {/* Footer info */}
        <div className="mt-2 text-xs text-gray-500 flex justify-between">
          <span className="capitalize">{control.control_type}</span>
          {control.last_update && (
            <span title={new Date(control.last_update).toLocaleString()}>
              {new Date(control.last_update).toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>
    </>
  );
}
