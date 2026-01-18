'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { RtuStateBadge } from '@/components/rtu';
import { useHMIToast } from '@/components/hmi';

interface DiscoveredSensor {
  bus_type: string;
  address: string | null;
  device_type: string;
  name: string;
  suggested_slot: number | null;
  suggested_measurement_type: string | null;
}

interface TestResult {
  test: string;
  status: 'pass' | 'fail' | 'warn';
  detail: string;
}

interface RTUTestResult {
  station_name: string;
  success: boolean;
  tests_passed: number;
  tests_failed: number;
  results: TestResult[];
  duration_ms: number;
}

type WizardStep = 'welcome' | 'add-rtu' | 'connect' | 'discover' | 'configure' | 'test' | 'complete';

const WIZARD_STORAGE_KEY = 'water-controller-wizard-state';

interface WizardState {
  currentStep: WizardStep;
  rtuConfig: {
    station_name: string;
    ip_address: string;
    vendor_id: number;
    device_id: number;
    slot_count: number;
  };
  completedSteps: WizardStep[];
  skippedSteps: WizardStep[];
  connectionState: string;
}

function loadWizardState(): WizardState | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = localStorage.getItem(WIZARD_STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch {
    // Invalid stored state
  }
  return null;
}

function saveWizardState(state: WizardState): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(WIZARD_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Storage full or unavailable
  }
}

function clearWizardState(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(WIZARD_STORAGE_KEY);
}

export default function WizardPage() {
  const router = useRouter();
  const toast = useHMIToast();
  const [currentStep, setCurrentStep] = useState<WizardStep>('welcome');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [completedSteps, setCompletedSteps] = useState<WizardStep[]>([]);
  const [skippedSteps, setSkippedSteps] = useState<WizardStep[]>([]);
  const [connectionState, setConnectionState] = useState<string>('OFFLINE');
  const [initialized, setInitialized] = useState(false);

  // RTU configuration
  const [rtuConfig, setRtuConfig] = useState({
    station_name: '',
    ip_address: '',
    vendor_id: 0x0493,
    device_id: 0x0001,
    slot_count: 16,
  });

  // Discovered sensors
  const [discoveredSensors, setDiscoveredSensors] = useState<DiscoveredSensor[]>([]);
  const [selectedSensors, setSelectedSensors] = useState<Set<number>>(new Set());

  // Test results
  const [testResults, setTestResults] = useState<RTUTestResult | null>(null);

  // Configuration options
  const [configOptions, setConfigOptions] = useState({
    createHistorianTags: true,
    createAlarmRules: false,
    enableModbus: false,
  });

  // Load saved state on mount
  useEffect(() => {
    const saved = loadWizardState();
    if (saved) {
      setCurrentStep(saved.currentStep);
      setRtuConfig(saved.rtuConfig);
      setCompletedSteps(saved.completedSteps);
      setSkippedSteps(saved.skippedSteps);
      setConnectionState(saved.connectionState || 'OFFLINE');
    }
    setInitialized(true);
  }, []);

  // Save state on changes
  useEffect(() => {
    if (!initialized) return;
    saveWizardState({
      currentStep,
      rtuConfig,
      completedSteps,
      skippedSteps,
      connectionState,
    });
  }, [initialized, currentStep, rtuConfig, completedSteps, skippedSteps, connectionState]);

  const steps = useMemo<{ id: WizardStep; label: string }[]>(() => [
    { id: 'welcome', label: 'Welcome' },
    { id: 'add-rtu', label: 'Add RTU' },
    { id: 'connect', label: 'Connect' },
    { id: 'discover', label: 'Discover' },
    { id: 'configure', label: 'Configure' },
    { id: 'test', label: 'Test' },
    { id: 'complete', label: 'Complete' },
  ], []);

  const currentStepIndex = steps.findIndex(s => s.id === currentStep);

  const goToStep = useCallback((step: WizardStep) => {
    setError(null);
    setCurrentStep(step);
  }, []);

  const markStepCompleted = useCallback((step: WizardStep) => {
    setCompletedSteps(prev => prev.includes(step) ? prev : [...prev, step]);
  }, []);

  const markStepSkipped = useCallback((step: WizardStep) => {
    setSkippedSteps(prev => prev.includes(step) ? prev : [...prev, step]);
  }, []);

  const nextStep = useCallback(() => {
    markStepCompleted(currentStep);
    const nextIndex = currentStepIndex + 1;
    if (nextIndex < steps.length) {
      goToStep(steps[nextIndex].id);
    }
  }, [currentStep, currentStepIndex, steps, goToStep, markStepCompleted]);

  const skipStep = useCallback(() => {
    markStepSkipped(currentStep);
    const nextIndex = currentStepIndex + 1;
    if (nextIndex < steps.length) {
      goToStep(steps[nextIndex].id);
    }
  }, [currentStep, currentStepIndex, steps, goToStep, markStepSkipped]);

  const prevStep = useCallback(() => {
    const prevIndex = currentStepIndex - 1;
    if (prevIndex >= 0) {
      goToStep(steps[prevIndex].id);
    }
  }, [currentStepIndex, steps, goToStep]);

  const cancelWizard = useCallback(() => {
    clearWizardState();
    router.push('/rtus');
  }, [router]);

  const addRtu = async () => {
    if (!rtuConfig.station_name || !rtuConfig.ip_address) {
      setError('Station name and IP address are required');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch('/api/v1/rtus', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rtuConfig),
      });

      if (res.ok) {
        nextStep();
      } else {
        const data = await res.json();
        setError(data.detail || 'Failed to add RTU');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setLoading(false);
    }
  };

  const connectRtu = async () => {
    setLoading(true);
    setError(null);
    setConnectionState('CONNECTING');

    try {
      const res = await fetch(`/api/v1/rtus/${rtuConfig.station_name}/connect`, {
        method: 'POST',
      });

      if (res.ok) {
        // Poll for connection state
        let attempts = 0;
        const maxAttempts = 10;
        while (attempts < maxAttempts) {
          await new Promise(resolve => setTimeout(resolve, 1000));
          attempts++;

          try {
            const statusRes = await fetch(`/api/v1/rtus/${rtuConfig.station_name}`);
            if (statusRes.ok) {
              const data = await statusRes.json();
              setConnectionState(data.state || data.connection_state || 'UNKNOWN');
              if (data.state === 'RUNNING' || data.connection_state === 'RUNNING') {
                toast.success('Connected', `Successfully connected to ${rtuConfig.station_name}`);
                nextStep();
                return;
              }
              if (data.state === 'ERROR' || data.connection_state === 'ERROR') {
                setError('Connection failed. Check RTU status and network connectivity.');
                setConnectionState('ERROR');
                return;
              }
            }
          } catch {
            // Continue polling
          }
        }
        // Timeout - proceed anyway
        toast.warning('Connection timeout', 'Connection is still in progress. You may continue.');
        nextStep();
      } else {
        setError('Failed to connect to RTU');
        setConnectionState('OFFLINE');
      }
    } catch (err) {
      setError('Connection failed. Check network connectivity.');
      setConnectionState('OFFLINE');
    } finally {
      setLoading(false);
    }
  };

  const discoverSensors = async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`/api/v1/rtus/${rtuConfig.station_name}/discover?scan_i2c=true&scan_onewire=true`, {
        method: 'POST',
      });

      if (res.ok) {
        const data = await res.json();
        setDiscoveredSensors(data.sensors);
        // Select all by default
        setSelectedSensors(new Set(data.sensors.map((_: DiscoveredSensor, i: number) => i)));
        nextStep();
      } else {
        setError('Discovery failed');
      }
    } catch (err) {
      setError('Discovery request failed');
    } finally {
      setLoading(false);
    }
  };

  const provisionSensors = async () => {
    setLoading(true);
    setError(null);

    const sensorsToProvision = discoveredSensors.filter((_, i) => selectedSensors.has(i));

    try {
      const res = await fetch(`/api/v1/rtus/${rtuConfig.station_name}/provision?create_historian_tags=${configOptions.createHistorianTags}&create_alarm_rules=${configOptions.createAlarmRules}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sensorsToProvision),
      });

      if (res.ok) {
        nextStep();
      } else {
        setError('Failed to provision sensors');
      }
    } catch (err) {
      setError('Provisioning failed');
    } finally {
      setLoading(false);
    }
  };

  const runTest = async () => {
    setLoading(true);
    setError(null);
    setTestResults(null);

    try {
      const res = await fetch(`/api/v1/rtus/${rtuConfig.station_name}/test?test_actuators=true&blink_duration_ms=500`, {
        method: 'POST',
      });

      if (res.ok) {
        const data = await res.json();
        setTestResults(data);
      } else {
        setError('Test failed to run');
      }
    } catch (err) {
      setError('Test request failed');
    } finally {
      setLoading(false);
    }
  };

  const toggleSensor = (index: number) => {
    const newSelected = new Set(selectedSensors);
    if (newSelected.has(index)) {
      newSelected.delete(index);
    } else {
      newSelected.add(index);
    }
    setSelectedSensors(newSelected);
  };

  const getStepStatusClass = (stepId: WizardStep) => {
    if (completedSteps.includes(stepId)) return 'bg-status-ok text-white';
    if (skippedSteps.includes(stepId)) return 'bg-amber-600 text-white';
    if (stepId === currentStep) return 'bg-status-info text-white';
    return 'bg-hmi-panel text-hmi-muted';
  };

  const getStepIcon = (stepId: WizardStep, index: number) => {
    if (completedSteps.includes(stepId)) {
      return (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      );
    }
    if (skippedSteps.includes(stepId)) {
      return (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
        </svg>
      );
    }
    return index + 1;
  };

  return (
    <div className="min-h-screen bg-hmi-bg text-hmi-text p-4">
      <div className="max-w-4xl mx-auto">
        {/* Progress Bar */}
        <div className="mb-4">
          <div className="flex items-center justify-between">
            <button
              onClick={cancelWizard}
              className="text-hmi-muted hover:text-hmi-text text-sm flex items-center gap-1"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              Cancel
            </button>
            <span className="text-sm text-hmi-muted">Step {currentStepIndex + 1} of {steps.length}</span>
          </div>
          <div className="flex items-center justify-between mt-4">
            {steps.map((step, index) => (
              <div key={step.id} className="flex items-center">
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold ${getStepStatusClass(step.id)}`}
                >
                  {getStepIcon(step.id, index)}
                </div>
                {index < steps.length - 1 && (
                  <div className={`h-1 w-16 mx-2 ${
                    completedSteps.includes(step.id) || skippedSteps.includes(step.id)
                      ? completedSteps.includes(step.id) ? 'bg-status-ok' : 'bg-amber-600'
                      : 'bg-hmi-panel'
                  }`} />
                )}
              </div>
            ))}
          </div>
          <div className="flex justify-between mt-2">
            {steps.map((step) => (
              <span key={step.id} className="text-xs text-hmi-muted w-20 text-center">
                {step.label}
              </span>
            ))}
          </div>
        </div>

        {/* Error Banner */}
        {error && (
          <div className="mb-6 p-4 bg-red-900 text-red-200 rounded-lg">
            {error}
          </div>
        )}

        {/* Step Content */}
        <div className="bg-hmi-panel rounded-lg p-4">
          {/* Welcome Step */}
          {currentStep === 'welcome' && (
            <div className="text-center">
              <h1 className="text-xl font-bold mb-2">Configuration Wizard</h1>
              <p className="text-hmi-muted mb-4 text-sm">
                This wizard will help you set up your Water Treatment Controller by guiding you through:
              </p>
              <div className="grid grid-cols-2 gap-3 max-w-md mx-auto text-left mb-4 text-sm">
                <div className="flex items-center space-x-2">
                  <span className="text-green-400">1.</span>
                  <span>Adding an RTU device</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-green-400">2.</span>
                  <span>Establishing connection</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-green-400">3.</span>
                  <span>Discovering sensors</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-green-400">4.</span>
                  <span>Configuring slots</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-green-400">5.</span>
                  <span>Testing communication</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-green-400">6.</span>
                  <span>Completing setup</span>
                </div>
              </div>
              <button
                onClick={nextStep}
                className="px-6 py-2.5 bg-status-info hover:bg-status-info/90 rounded-lg font-semibold"
              >
                Get Started
              </button>
            </div>
          )}

          {/* Add RTU Step */}
          {currentStep === 'add-rtu' && (
            <div>
              <h2 className="text-lg font-bold mb-3">Add RTU Device</h2>
              <p className="text-hmi-muted text-sm mb-3">
                Enter the details of your Remote Terminal Unit (RTU). The RTU should be powered on and connected to the network.
              </p>

              <div className="space-y-4 max-w-md">
                <div>
                  <label className="block text-sm text-hmi-muted mb-1">Station Name *</label>
                  <input
                    type="text"
                    value={rtuConfig.station_name}
                    onChange={(e) => setRtuConfig({ ...rtuConfig, station_name: e.target.value })}
                    placeholder="e.g., water-treat-rtu-1"
                    className="w-full px-4 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                  />
                  <p className="text-xs text-gray-500 mt-1">Unique identifier for this RTU</p>
                </div>

                <div>
                  <label className="block text-sm text-hmi-muted mb-1">IP Address *</label>
                  <input
                    type="text"
                    value={rtuConfig.ip_address}
                    onChange={(e) => setRtuConfig({ ...rtuConfig, ip_address: e.target.value })}
                    placeholder="e.g., 192.168.1.100"
                    className="w-full px-4 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-hmi-muted mb-1">Vendor ID</label>
                    <input
                      type="text"
                      value={`0x${rtuConfig.vendor_id.toString(16).padStart(4, '0')}`}
                      onChange={(e) => setRtuConfig({ ...rtuConfig, vendor_id: parseInt(e.target.value, 16) || 0 })}
                      className="w-full px-4 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-hmi-muted mb-1">Device ID</label>
                    <input
                      type="text"
                      value={`0x${rtuConfig.device_id.toString(16).padStart(4, '0')}`}
                      onChange={(e) => setRtuConfig({ ...rtuConfig, device_id: parseInt(e.target.value, 16) || 0 })}
                      className="w-full px-4 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text font-mono"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm text-hmi-muted mb-1">Initial Slot Count</label>
                  <select
                    value={rtuConfig.slot_count}
                    onChange={(e) => setRtuConfig({ ...rtuConfig, slot_count: parseInt(e.target.value) })}
                    className="w-full px-4 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                  >
                    <option value={8}>8 slots</option>
                    <option value={16}>16 slots</option>
                    <option value={32}>32 slots</option>
                    <option value={64}>64 slots</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">Will be updated automatically from RTU configuration</p>
                </div>
              </div>

              <div className="flex justify-between mt-4">
                <button
                  onClick={prevStep}
                  className="px-6 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded border border-hmi-border"
                >
                  Back
                </button>
                <button
                  onClick={addRtu}
                  disabled={loading}
                  className="px-6 py-2 bg-status-info hover:bg-status-info/90 rounded disabled:opacity-50"
                >
                  {loading ? 'Adding...' : 'Add RTU'}
                </button>
              </div>
            </div>
          )}

          {/* Connect Step */}
          {currentStep === 'connect' && (
            <div>
              <h2 className="text-lg font-bold mb-3">Connect to RTU</h2>
              <p className="text-hmi-muted text-sm mb-3">
                Establish a PROFINET connection to <strong>{rtuConfig.station_name}</strong> at {rtuConfig.ip_address}.
              </p>

              {/* Connection Status */}
              <div className="bg-hmi-panel border border-hmi-border p-4 rounded-lg mb-3">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold">Connection Status</h3>
                  <RtuStateBadge state={connectionState} size="md" />
                </div>
                {loading && (
                  <div className="flex items-center gap-3 text-blue-400">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <span>Establishing connection...</span>
                  </div>
                )}
              </div>

              <div className="bg-hmi-panel border border-hmi-border p-4 rounded-lg mb-3">
                <h3 className="font-semibold mb-4">Pre-flight Checklist</h3>
                <ul className="space-y-2 text-hmi-muted">
                  <li className="flex items-center space-x-2">
                    <span className="text-green-400">&#10003;</span>
                    <span>RTU is powered on</span>
                  </li>
                  <li className="flex items-center space-x-2">
                    <span className="text-green-400">&#10003;</span>
                    <span>RTU is connected to network</span>
                  </li>
                  <li className="flex items-center space-x-2">
                    <span className="text-green-400">&#10003;</span>
                    <span>Controller and RTU are on the same network segment</span>
                  </li>
                  <li className="flex items-center space-x-2">
                    <span className="text-green-400">&#10003;</span>
                    <span>No firewall blocking PROFINET ports (34962-34964)</span>
                  </li>
                </ul>
              </div>

              <div className="flex justify-between">
                <button
                  onClick={prevStep}
                  className="px-6 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded border border-hmi-border"
                >
                  Back
                </button>
                <div className="space-x-4">
                  <button
                    onClick={skipStep}
                    className="px-6 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded border border-hmi-border"
                  >
                    Connect Later
                  </button>
                  <button
                    onClick={connectRtu}
                    disabled={loading}
                    className="px-6 py-2 bg-status-info hover:bg-status-info/90 rounded disabled:opacity-50 flex items-center gap-2 inline-flex"
                  >
                    {loading && (
                      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                    )}
                    {loading ? 'Connecting...' : 'Connect'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Discover Step */}
          {currentStep === 'discover' && (
            <div>
              <h2 className="text-lg font-bold mb-3">Discover Sensors</h2>
              <p className="text-hmi-muted text-sm mb-3">
                Scan the RTU&apos;s I2C buses and 1-Wire interfaces to discover connected sensors.
              </p>

              <div className="bg-hmi-panel border border-hmi-border p-4 rounded-lg mb-3">
                <h3 className="font-semibold mb-4">Supported Sensors</h3>
                <div className="grid grid-cols-2 gap-4 text-sm text-hmi-muted">
                  <div>
                    <h4 className="text-blue-400 mb-2">I2C Devices</h4>
                    <ul className="space-y-1">
                      <li>ADS1115 - 16-bit ADC</li>
                      <li>BME280 - Temp/Pressure/Humidity</li>
                      <li>TCS34725 - Color Sensor</li>
                      <li>SHT31 - Temp/Humidity</li>
                      <li>INA219 - Current Sensor</li>
                    </ul>
                  </div>
                  <div>
                    <h4 className="text-blue-400 mb-2">1-Wire Devices</h4>
                    <ul className="space-y-1">
                      <li>DS18B20 - Temperature</li>
                    </ul>
                  </div>
                </div>
              </div>

              <div className="flex justify-between">
                <button
                  onClick={prevStep}
                  className="px-6 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded border border-hmi-border"
                >
                  Back
                </button>
                <div className="space-x-4">
                  <button
                    onClick={skipStep}
                    className="px-6 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded border border-hmi-border"
                  >
                    Configure Manually Later
                  </button>
                  <button
                    onClick={discoverSensors}
                    disabled={loading}
                    className="px-6 py-2 bg-status-info hover:bg-status-info/90 rounded disabled:opacity-50 inline-flex items-center gap-2"
                  >
                    {loading && (
                      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                    )}
                    {loading ? 'Scanning...' : 'Scan for Sensors'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Configure Step */}
          {currentStep === 'configure' && (
            <div>
              <h2 className="text-lg font-bold mb-3">Configure Sensors</h2>

              {discoveredSensors.length > 0 ? (
                <>
                  <p className="text-hmi-muted text-sm mb-3">
                    Found {discoveredSensors.length} sensor(s). Select which ones to configure:
                  </p>

                  <div className="space-y-3 mb-6">
                    {discoveredSensors.map((sensor, index) => (
                      <div
                        key={index}
                        className={`p-4 rounded-lg border cursor-pointer transition-colors ${
                          selectedSensors.has(index)
                            ? 'bg-blue-900 border-blue-500'
                            : 'bg-hmi-panel border-hmi-border hover:border-gray-500'
                        }`}
                        onClick={() => toggleSensor(index)}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-4">
                            <input
                              type="checkbox"
                              checked={selectedSensors.has(index)}
                              onChange={() => toggleSensor(index)}
                              className="w-5 h-5"
                            />
                            <div>
                              <div className="font-semibold">{sensor.name}</div>
                              <div className="text-sm text-hmi-muted">
                                {sensor.bus_type.toUpperCase()} @ {sensor.address} | Type: {sensor.device_type}
                              </div>
                            </div>
                          </div>
                          <div className="text-right text-sm">
                            <div className="text-hmi-muted">Suggested Slot</div>
                            <div className="font-mono">{sensor.suggested_slot}</div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="bg-hmi-panel border border-hmi-border p-4 rounded-lg mb-6">
                    <h3 className="font-semibold mb-3">Additional Options</h3>
                    <div className="space-y-3">
                      <label className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          checked={configOptions.createHistorianTags}
                          onChange={(e) => setConfigOptions({ ...configOptions, createHistorianTags: e.target.checked })}
                          className="w-4 h-4"
                        />
                        <span>Create historian tags for data logging</span>
                      </label>
                      <label className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          checked={configOptions.createAlarmRules}
                          onChange={(e) => setConfigOptions({ ...configOptions, createAlarmRules: e.target.checked })}
                          className="w-4 h-4"
                        />
                        <span>Create default alarm rules (disabled by default)</span>
                      </label>
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-center py-3">
                  <p className="text-hmi-muted text-sm">No sensors discovered. You can configure sensors manually later.</p>
                </div>
              )}

              <div className="flex justify-between">
                <button
                  onClick={prevStep}
                  className="px-6 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded border border-hmi-border"
                >
                  Back
                </button>
                <button
                  onClick={discoveredSensors.length > 0 && selectedSensors.size > 0 ? provisionSensors : nextStep}
                  disabled={loading}
                  className="px-6 py-2 bg-status-info hover:bg-status-info/90 rounded disabled:opacity-50"
                >
                  {loading ? 'Configuring...' : selectedSensors.size > 0 ? 'Configure Selected' : 'Continue'}
                </button>
              </div>
            </div>
          )}

          {/* Test Step */}
          {currentStep === 'test' && (
            <div>
              <h2 className="text-lg font-bold mb-3">Test RTU</h2>
              <p className="text-hmi-muted text-sm mb-3">
                Run a functionality test to verify communication and actuator operation.
                This will briefly blink all actuator outputs for visual verification.
              </p>

              {!testResults ? (
                <div className="text-center py-4">
                  <button
                    onClick={runTest}
                    disabled={loading}
                    className="px-4 py-2 bg-status-ok hover:bg-status-ok/90 rounded font-medium disabled:opacity-50"
                  >
                    {loading ? 'Running Test...' : 'Run Test'}
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className={`p-4 rounded-lg ${testResults.success ? 'bg-green-900' : 'bg-red-900'}`}>
                    <div className="font-semibold text-lg">
                      {testResults.success ? 'All Tests Passed!' : 'Some Tests Failed'}
                    </div>
                    <div className="text-sm">
                      {testResults.tests_passed} passed, {testResults.tests_failed} failed
                      ({testResults.duration_ms}ms)
                    </div>
                  </div>

                  <div className="space-y-2">
                    {testResults.results.map((result, index) => (
                      <div
                        key={index}
                        className={`p-3 rounded flex items-center justify-between ${
                          result.status === 'pass' ? 'bg-green-900/50' :
                          result.status === 'warn' ? 'bg-yellow-900/50' : 'bg-red-900/50'
                        }`}
                      >
                        <div>
                          <span className="font-medium capitalize">{result.test}</span>
                          <span className="text-hmi-muted ml-2">- {result.detail}</span>
                        </div>
                        <span className={`font-semibold ${
                          result.status === 'pass' ? 'text-green-400' :
                          result.status === 'warn' ? 'text-yellow-400' : 'text-red-400'
                        }`}>
                          {result.status.toUpperCase()}
                        </span>
                      </div>
                    ))}
                  </div>

                  <button
                    onClick={runTest}
                    disabled={loading}
                    className="mt-4 px-6 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded border border-hmi-border"
                  >
                    Run Again
                  </button>
                </div>
              )}

              <div className="flex justify-between mt-4">
                <button
                  onClick={prevStep}
                  className="px-6 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded border border-hmi-border"
                >
                  Back
                </button>
                <div className="space-x-4">
                  {!testResults && (
                    <button
                      onClick={skipStep}
                      className="px-6 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded border border-hmi-border"
                    >
                      Skip Test
                    </button>
                  )}
                  <button
                    onClick={nextStep}
                    className="px-6 py-2 bg-status-info hover:bg-status-info/90 rounded"
                  >
                    {testResults ? 'Continue' : 'Finish Setup'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Complete Step */}
          {currentStep === 'complete' && (
            <div className="text-center">
              <div className="w-10 h-10 mx-auto mb-3 rounded-full bg-status-ok flex items-center justify-center">
                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 className="text-lg font-bold mb-2">Setup Complete!</h2>
              <p className="text-hmi-muted text-sm mb-4">
                Your RTU <strong>{rtuConfig.station_name}</strong> has been configured successfully.
              </p>

              <div className="bg-hmi-panel border border-hmi-border p-4 rounded-lg mb-4 text-left max-w-md mx-auto">
                <h3 className="font-semibold mb-2 text-sm">Summary</h3>
                <div className="space-y-2 text-hmi-muted">
                  <div className="flex justify-between">
                    <span>Station Name:</span>
                    <span className="font-mono">{rtuConfig.station_name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>IP Address:</span>
                    <span className="font-mono">{rtuConfig.ip_address}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Connection:</span>
                    <RtuStateBadge state={connectionState} size="sm" />
                  </div>
                  <div className="flex justify-between">
                    <span>Sensors Configured:</span>
                    <span>{selectedSensors.size}</span>
                  </div>
                  {skippedSteps.length > 0 && (
                    <div className="flex justify-between text-amber-400">
                      <span>Skipped Steps:</span>
                      <span>{skippedSteps.length}</span>
                    </div>
                  )}
                </div>
              </div>

              <div className="space-x-4">
                <button
                  onClick={() => {
                    clearWizardState();
                    router.push('/rtus');
                  }}
                  className="px-6 py-2 bg-status-info hover:bg-status-info/90 rounded"
                >
                  Go to Dashboard
                </button>
                <button
                  onClick={() => {
                    clearWizardState();
                    setCurrentStep('welcome');
                    setCompletedSteps([]);
                    setSkippedSteps([]);
                    setConnectionState('OFFLINE');
                    setRtuConfig({
                      station_name: '',
                      ip_address: '',
                      vendor_id: 0x0493,
                      device_id: 0x0001,
                      slot_count: 16,
                    });
                    setDiscoveredSensors([]);
                    setSelectedSensors(new Set());
                    setTestResults(null);
                    setError(null);
                  }}
                  className="px-6 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded border border-hmi-border"
                >
                  Add Another RTU
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
