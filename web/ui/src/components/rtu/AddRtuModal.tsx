'use client';

import { useState, useCallback, useEffect } from 'react';

interface RtuFormData {
  station_name: string;
  ip_address: string;
  vendor_id: string;
  device_id: string;
  slot_count: number;
}

interface FieldError {
  field: keyof RtuFormData;
  message: string;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (rtu: RtuFormData) => void;
  prefillData?: Partial<RtuFormData>;
}

const INITIAL_FORM_DATA: RtuFormData = {
  station_name: '',
  ip_address: '',
  vendor_id: '0x0000',
  device_id: '0x0000',
  slot_count: 8,
};

// Validation functions
function validateStationName(value: string): string | null {
  if (!value.trim()) {
    return 'Station name is required';
  }
  if (!/^[a-zA-Z0-9_-]+$/.test(value)) {
    return 'Only alphanumeric characters, hyphens, and underscores allowed';
  }
  if (value.length > 64) {
    return 'Station name must be 64 characters or less';
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

function validateHexId(value: string, fieldName: string): string | null {
  if (!value.trim()) {
    return `${fieldName} is required`;
  }
  const hexRegex = /^0x[0-9a-fA-F]{4}$/;
  if (!hexRegex.test(value)) {
    return 'Enter a valid hex value (e.g., 0x0493)';
  }
  return null;
}

function validateSlotCount(value: number): string | null {
  if (value < 1 || value > 64) {
    return 'Slot count must be between 1 and 64';
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

  // Reset form when modal opens/closes or prefill data changes
  useEffect(() => {
    if (isOpen) {
      setFormData({
        ...INITIAL_FORM_DATA,
        ...prefillData,
        vendor_id: prefillData?.vendor_id || INITIAL_FORM_DATA.vendor_id,
        device_id: prefillData?.device_id || INITIAL_FORM_DATA.device_id,
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

  const validateField = useCallback((field: keyof RtuFormData, value: string | number): string | null => {
    switch (field) {
      case 'station_name':
        return validateStationName(value as string);
      case 'ip_address':
        return validateIpAddress(value as string);
      case 'vendor_id':
        return validateHexId(value as string, 'Vendor ID');
      case 'device_id':
        return validateHexId(value as string, 'Device ID');
      case 'slot_count':
        return validateSlotCount(value as number);
      default:
        return null;
    }
  }, []);

  const handleChange = useCallback((field: keyof RtuFormData, value: string | number) => {
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

    (Object.keys(formData) as Array<keyof RtuFormData>).forEach(field => {
      const error = validateField(field, formData[field]);
      if (error) {
        errors.push({ field, message: error });
      }
    });

    setFieldErrors(errors);
    setTouched(new Set(Object.keys(formData) as Array<keyof RtuFormData>));
    return errors.length === 0;
  }, [formData, validateField]);

  const handleSubmit = async () => {
    if (!validateAllFields()) {
      return;
    }

    setLoading(true);
    setServerError(null);

    try {
      const res = await fetch('/api/v1/rtus', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          station_name: formData.station_name,
          ip_address: formData.ip_address,
          vendor_id: parseInt(formData.vendor_id, 16),
          device_id: parseInt(formData.device_id, 16),
          slot_count: formData.slot_count,
        }),
      });

      if (res.status === 201 || res.ok) {
        onSuccess(formData);
        return;
      }

      // Handle Pydantic validation errors (422) and general bad requests (400)
      if (res.status === 400 || res.status === 422) {
        const data = await res.json();
        if (data.detail) {
          // Pydantic returns detail as array of validation errors
          if (Array.isArray(data.detail)) {
            const errors: FieldError[] = [];
            for (const err of data.detail) {
              const fieldName = err.loc?.[err.loc.length - 1];
              const message = err.msg || 'Invalid value';
              if (fieldName && fieldName in INITIAL_FORM_DATA) {
                errors.push({ field: fieldName as keyof RtuFormData, message });
              } else {
                // If we can't map to a specific field, show as server error
                setServerError(message);
              }
            }
            if (errors.length > 0) {
              setFieldErrors(errors);
            }
          } else if (typeof data.detail === 'string') {
            // Check for field-specific errors from server
            if (data.detail.includes('name') || data.detail.includes('station')) {
              setFieldErrors([{ field: 'station_name', message: data.detail }]);
            } else if (data.detail.includes('IP') || data.detail.includes('address')) {
              setFieldErrors([{ field: 'ip_address', message: data.detail }]);
            } else {
              setServerError(data.detail);
            }
          } else {
            // Unknown detail format - stringify it safely
            setServerError('Validation error. Please check your input.');
          }
        } else {
          setServerError('Invalid request. Please check your input.');
        }
        return;
      }

      if (res.status === 409) {
        const data = await res.json();
        const detail = data.detail || 'An RTU with this name or IP already exists';
        if (detail.includes('IP')) {
          setFieldErrors([{ field: 'ip_address', message: 'An RTU with this IP address already exists' }]);
        } else if (detail.includes('name')) {
          setFieldErrors([{ field: 'station_name', message: 'An RTU with this name already exists' }]);
        } else {
          setServerError(detail);
        }
        return;
      }

      setServerError('Failed to add RTU. Please try again.');
    } catch (err) {
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

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div
        className="bg-gray-900 rounded-lg w-full max-w-md border border-gray-700 shadow-xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-blue-600/20 flex items-center justify-center">
              <span className="text-blue-400 text-xl font-bold">+</span>
            </div>
            <h2 className="text-lg font-semibold text-white">Add New RTU</h2>
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
              onChange={e => handleChange('station_name', e.target.value)}
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
            <p className="text-gray-500 text-xs mt-1">Unique alphanumeric identifier</p>
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

          {/* Vendor ID & Device ID */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Vendor ID <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={formData.vendor_id}
                onChange={e => handleChange('vendor_id', e.target.value)}
                onBlur={() => handleBlur('vendor_id')}
                placeholder="0x0493"
                disabled={loading}
                className={`w-full px-3 py-2 bg-gray-800 border rounded text-white font-mono placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 ${
                  getFieldError('vendor_id') ? 'border-red-500' : 'border-gray-700'
                }`}
              />
              {getFieldError('vendor_id') && (
                <p className="text-red-400 text-xs mt-1">{getFieldError('vendor_id')}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Device ID <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={formData.device_id}
                onChange={e => handleChange('device_id', e.target.value)}
                onBlur={() => handleBlur('device_id')}
                placeholder="0x0001"
                disabled={loading}
                className={`w-full px-3 py-2 bg-gray-800 border rounded text-white font-mono placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 ${
                  getFieldError('device_id') ? 'border-red-500' : 'border-gray-700'
                }`}
              />
              {getFieldError('device_id') && (
                <p className="text-red-400 text-xs mt-1">{getFieldError('device_id')}</p>
              )}
            </div>
          </div>

          {/* Slot Count */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Slot Count <span className="text-red-400">*</span>
            </label>
            <select
              value={formData.slot_count}
              onChange={e => handleChange('slot_count', parseInt(e.target.value))}
              onBlur={() => handleBlur('slot_count')}
              disabled={loading}
              className={`w-full px-3 py-2 bg-gray-800 border rounded text-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 ${
                getFieldError('slot_count') ? 'border-red-500' : 'border-gray-700'
              }`}
            >
              {[1, 2, 4, 8, 16, 32, 64].map(count => (
                <option key={count} value={count}>
                  {count} {count === 1 ? 'slot' : 'slots'}
                </option>
              ))}
            </select>
            {getFieldError('slot_count') && (
              <p className="text-red-400 text-xs mt-1">{getFieldError('slot_count')}</p>
            )}
            <p className="text-gray-500 text-xs mt-1">Number of I/O slots (default: 8)</p>
          </div>
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
