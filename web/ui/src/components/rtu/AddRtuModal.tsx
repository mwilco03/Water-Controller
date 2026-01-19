'use client';

import { useState, useCallback, useEffect, useRef } from 'react';

interface RtuFormData {
  station_name: string;
  ip_address: string;
}

interface PrefillData {
  station_name?: string;
  ip_address?: string;
  vendor_id?: string;
  device_id?: string;
}

interface FieldError {
  field: keyof RtuFormData;
  message: string;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (rtu: RtuFormData) => void;
  prefillData?: PrefillData;
}

const INITIAL_FORM_DATA: RtuFormData = {
  station_name: '',
  ip_address: '',
};

// Validation functions
function validateStationName(value: string): string | null {
  if (!value.trim()) {
    return 'Station name is required';
  }
  if (!/^[a-z][a-z0-9-]*$/.test(value)) {
    return 'Must start with letter, use lowercase letters, numbers, and hyphens only';
  }
  if (value.length < 3 || value.length > 32) {
    return 'Station name must be 3-32 characters';
  }
  return null;
}

function validateIpAddress(value: string): string | null {
  if (!value.trim()) {
    return 'IP address is required';
  }
  const ipv4Regex = /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
  if (!ipv4Regex.test(value)) {
    return 'Enter a valid IPv4 address (e.g., 192.168.1.100)';
  }
  return null;
}

export default function AddRtuModal({
  isOpen,
  onClose,
  onSuccess,
  prefillData,
}: Props) {
  const [formData, setFormData] = useState<RtuFormData>(INITIAL_FORM_DATA);
  const [fieldErrors, setFieldErrors] = useState<FieldError[]>([]);
  const [serverError, setServerError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [touched, setTouched] = useState<Set<keyof RtuFormData>>(new Set());
  const modalRef = useRef<HTMLDivElement>(null);

  // Handle escape key to close modal
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !loading) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.body.style.overflow = 'hidden';
    modalRef.current?.focus();

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, loading, onClose]);

  // Reset form when modal opens/closes or prefill data changes
  useEffect(() => {
    if (isOpen) {
      setFormData({
        station_name: prefillData?.station_name || '',
        ip_address: prefillData?.ip_address || '',
      });
      setFieldErrors([]);
      setServerError(null);
      setTouched(new Set());
    }
  }, [isOpen, prefillData]);

  const getFieldError = (field: keyof RtuFormData): string | null => {
    const error = fieldErrors.find(e => e.field === field);
    return error?.message || null;
  };

  const validateField = useCallback((field: keyof RtuFormData, value: string): string | null => {
    switch (field) {
      case 'station_name':
        return validateStationName(value);
      case 'ip_address':
        return validateIpAddress(value);
      default:
        return null;
    }
  }, []);

  const handleChange = useCallback((field: keyof RtuFormData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setServerError(null);

    // Validate on change if field was already touched
    if (touched.has(field)) {
      const error = validateField(field, value);
      setFieldErrors(prev => {
        const filtered = prev.filter(e => e.field !== field);
        if (error) {
          return [...filtered, { field, message: error }];
        }
        return filtered;
      });
    }
  }, [touched, validateField]);

  const handleBlur = useCallback((field: keyof RtuFormData) => {
    setTouched(prev => new Set(prev).add(field));

    const value = formData[field];
    const error = validateField(field, value);
    setFieldErrors(prev => {
      const filtered = prev.filter(e => e.field !== field);
      if (error) {
        return [...filtered, { field, message: error }];
      }
      return filtered;
    });
  }, [formData, validateField]);

  const validateAllFields = useCallback((): boolean => {
    const errors: FieldError[] = [];

    const stationError = validateStationName(formData.station_name);
    if (stationError) errors.push({ field: 'station_name', message: stationError });

    const ipError = validateIpAddress(formData.ip_address);
    if (ipError) errors.push({ field: 'ip_address', message: ipError });

    setFieldErrors(errors);
    setTouched(new Set(['station_name', 'ip_address']));
    return errors.length === 0;
  }, [formData]);

  const handleSubmit = async () => {
    if (!validateAllFields()) {
      return;
    }

    setLoading(true);
    setServerError(null);

    try {
      // Build request - only station_name and ip_address are required
      // vendor_id and device_id use prefill (from discovery) or backend defaults
      const requestBody: Record<string, string> = {
        station_name: formData.station_name,
        ip_address: formData.ip_address,
      };

      // Include vendor/device IDs if provided by discovery prefill
      if (prefillData?.vendor_id) {
        requestBody.vendor_id = prefillData.vendor_id;
      }
      if (prefillData?.device_id) {
        requestBody.device_id = prefillData.device_id;
      }

      const res = await fetch('/api/v1/rtus', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (res.status === 201 || res.ok) {
        onSuccess(formData);
        return;
      }

      // Handle Pydantic validation errors (422) and general bad requests (400)
      if (res.status === 400 || res.status === 422) {
        const data = await res.json();
        if (data.detail) {
          if (Array.isArray(data.detail)) {
            const messages = data.detail
              .map((err: { msg?: string }) => err.msg || 'Invalid value')
              .join('; ');
            setServerError(messages || 'Validation failed');
          } else if (typeof data.detail === 'string') {
            if (data.detail.includes('name') || data.detail.includes('station')) {
              setFieldErrors([{ field: 'station_name', message: data.detail }]);
            } else if (data.detail.includes('IP') || data.detail.includes('address')) {
              setFieldErrors([{ field: 'ip_address', message: data.detail }]);
            } else {
              setServerError(data.detail);
            }
          } else if (typeof data.detail === 'object' && data.detail.msg) {
            setServerError(data.detail.msg);
          } else {
            setServerError('Validation error. Please check your input.');
          }
        } else {
          setServerError('Invalid request. Please check your input.');
        }
        return;
      }

      if (res.status === 409) {
        const data = await res.json();
        let detailMessage = 'An RTU with this name or IP already exists';
        if (typeof data.detail === 'string') {
          detailMessage = data.detail;
        } else if (Array.isArray(data.detail) && data.detail.length > 0) {
          detailMessage = data.detail[0]?.msg || detailMessage;
        } else if (data.detail && typeof data.detail === 'object' && data.detail.msg) {
          detailMessage = data.detail.msg;
        }

        if (detailMessage.includes('IP')) {
          setFieldErrors([{ field: 'ip_address', message: 'An RTU with this IP address already exists' }]);
        } else if (detailMessage.includes('name')) {
          setFieldErrors([{ field: 'station_name', message: 'An RTU with this name already exists' }]);
        } else {
          setServerError(detailMessage);
        }
        return;
      }

      setServerError('Failed to add RTU. Please try again.');
    } catch {
      setServerError('Unable to reach server. Check connection and try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    if (!loading) {
      onClose();
    }
  };

  if (!isOpen) return null;

  const hasErrors = fieldErrors.length > 0 || serverError !== null;
  const isFromDiscovery = !!(prefillData?.vendor_id || prefillData?.device_id);

  // Handle backdrop click
  const handleBackdropClick = (event: React.MouseEvent) => {
    if (event.target === event.currentTarget && !loading) {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-modal p-4"
      onClick={handleBackdropClick}
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-rtu-modal-title"
        tabIndex={-1}
        className="bg-gray-900 rounded-lg w-full max-w-md border border-gray-700 shadow-xl outline-none"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-blue-600/20 flex items-center justify-center">
              <span className="text-blue-400 text-xl font-bold">+</span>
            </div>
            <div>
              <h2 id="add-rtu-modal-title" className="text-lg font-semibold text-white">Add New RTU</h2>
              {isFromDiscovery && (
                <p className="text-xs text-green-400">From network discovery</p>
              )}
            </div>
          </div>
          <button
            onClick={handleClose}
            disabled={loading}
            className="text-gray-400 hover:text-white transition-colors disabled:opacity-50 w-6 h-6 flex items-center justify-center text-lg font-bold"
          >
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 space-y-4">
          {/* Server Error Banner */}
          {serverError && (
            <div className="flex items-start gap-3 p-3 bg-red-900/30 border border-red-800 rounded-lg">
              <span className="w-5 h-5 flex-shrink-0 mt-0.5 flex items-center justify-center bg-red-600 text-white text-xs font-bold rounded">!</span>
              <div>
                <p className="text-red-300 text-sm">{serverError}</p>
                <button
                  onClick={() => setServerError(null)}
                  className="text-red-400 text-xs hover:text-red-300 mt-1"
                >
                  Dismiss
                </button>
              </div>
            </div>
          )}

          {/* Station Name */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Station Name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={formData.station_name}
              onChange={e => handleChange('station_name', e.target.value.toLowerCase())}
              onBlur={() => handleBlur('station_name')}
              placeholder="e.g., water-treat-rtu-1"
              disabled={loading}
              className={`w-full px-3 py-2 bg-gray-800 border rounded text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 ${
                getFieldError('station_name') ? 'border-red-500' : 'border-gray-700'
              }`}
            />
            {getFieldError('station_name') && (
              <p className="text-red-400 text-xs mt-1">{getFieldError('station_name')}</p>
            )}
            <p className="text-gray-500 text-xs mt-1">Lowercase letters, numbers, hyphens (3-32 chars)</p>
          </div>

          {/* IP Address */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              IP Address <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={formData.ip_address}
              onChange={e => handleChange('ip_address', e.target.value)}
              onBlur={() => handleBlur('ip_address')}
              placeholder="e.g., 192.168.1.100"
              disabled={loading}
              className={`w-full px-3 py-2 bg-gray-800 border rounded text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 ${
                getFieldError('ip_address') ? 'border-red-500' : 'border-gray-700'
              }`}
            />
            {getFieldError('ip_address') && (
              <p className="text-red-400 text-xs mt-1">{getFieldError('ip_address')}</p>
            )}
          </div>

          {/* Discovery info (read-only, shown only if from discovery) */}
          {isFromDiscovery && (
            <div className="p-3 bg-gray-800/50 border border-gray-700 rounded-lg">
              <p className="text-xs text-gray-400 mb-2">Discovered device info:</p>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-gray-500">Vendor ID:</span>
                  <span className="text-gray-300 font-mono ml-1">{prefillData?.vendor_id || '0x0000'}</span>
                </div>
                <div>
                  <span className="text-gray-500">Device ID:</span>
                  <span className="text-gray-300 font-mono ml-1">{prefillData?.device_id || '0x0000'}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-700">
          <button
            onClick={handleClose}
            disabled={loading}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading || hasErrors}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-white font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {loading && (
              <span className="inline-block animate-pulse">...</span>
            )}
            {loading ? 'Adding...' : 'Add RTU'}
          </button>
        </div>
      </div>
    </div>
  );
}
