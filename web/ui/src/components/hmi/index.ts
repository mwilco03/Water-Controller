/**
 * HMI Components Index
 * ISA-101 compliant SCADA HMI components
 */

export { default as DataQualityIndicator, qualityFromCode, isStale } from './DataQualityIndicator';
export type { DataQuality } from './DataQualityIndicator';

export { default as ConnectionStatusIndicator, connectionStateFromRtuState } from './ConnectionStatusIndicator';
export type { ConnectionState } from './ConnectionStatusIndicator';

export { default as AlarmBanner } from './AlarmBanner';
export type { AlarmData } from './AlarmBanner';

export { default as SystemStatusBar } from './SystemStatusBar';

export { default as RTUStatusCard } from './RTUStatusCard';
export type { RTUStatusData } from './RTUStatusCard';

export { default as SessionIndicator } from './SessionIndicator';

export { default as AuthenticationModal } from './AuthenticationModal';

export { default as ControlGuard } from './ControlGuard';

export { default as DegradedModeBanner, useDegradedMode } from './DegradedModeBanner';
export type { DegradedReason } from './DegradedModeBanner';

export { default as SystemStatusIndicator, DataFreshnessIndicator } from './SystemStatusIndicator';
export type { SystemState } from './SystemStatusIndicator';
