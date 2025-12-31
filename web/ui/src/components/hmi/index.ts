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

export { default as BottomNavigation } from './BottomNavigation';

export { default as LiveTimestamp } from './LiveTimestamp';

export { default as ErrorMessage, ErrorPresets } from './ErrorMessage';

export { default as ConfirmDialog } from './ConfirmDialog';

export {
  Skeleton,
  SkeletonText,
  SkeletonRTUCard,
  SkeletonAlarmItem,
  SkeletonProcessValue,
  SkeletonTableRow,
  SkeletonPage,
  SkeletonStats,
} from './Skeleton';

// New components
export { default as StatusHeader } from './StatusHeader';
export type { SystemStatus } from './StatusHeader';

export { default as ActionBar } from './ActionBar';
export type { Action, ActionGroup, ActionVariant } from './ActionBar';

export { default as ValueDisplay } from './ValueDisplay';
export type { ValueQuality, ValueTrend, ValueSize } from './ValueDisplay';

export { default as MetricCard } from './MetricCard';
export type { MetricStatus } from './MetricCard';

// Form components
export * from './forms';
