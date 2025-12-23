# Alarm Audio Notifications - Q4 2026 Roadmap

**Target Release:** Q4 2026
**Priority:** Medium
**Category:** Operator Experience Enhancement

## Overview

Implement audible alarm notifications to ensure operators are alerted to critical alarms even when not actively viewing the HMI screen. This is a SCADA best practice requirement for safety-critical systems.

## Requirements

### Audio Alert Types

| Alarm Severity | Sound Pattern | Volume | Repeat |
|----------------|---------------|--------|--------|
| CRITICAL/EMERGENCY | Continuous siren | High | Until acknowledged |
| WARNING | Double beep | Medium | Every 30 seconds |
| INFO | Single chime | Low | Once |

### Features to Implement

1. **Browser Audio API Integration**
   - Use Web Audio API for reliable cross-browser support
   - Support for MP3/WAV alarm sound files
   - Volume control per severity level

2. **Audio Settings (User Preferences)**
   - Enable/disable audio alerts per user
   - Volume slider (0-100%)
   - Per-severity enable/disable
   - Quiet hours configuration (optional)
   - Test sound button

3. **Audio Control Panel (Header)**
   - Mute/unmute toggle button (visible in header)
   - Visual indicator when muted
   - Click to silence current alarm sound

4. **Accessibility Considerations**
   - Audio should complement, not replace, visual indicators
   - Volume should respect system volume settings
   - Provide visual confirmation when audio plays

## Technical Implementation

### Frontend Changes

**New Files:**
- `hooks/useAlarmAudio.ts` - Audio management hook
- `components/AudioControls.tsx` - Mute/volume controls
- `public/sounds/alarm-critical.mp3`
- `public/sounds/alarm-warning.mp3`
- `public/sounds/alarm-info.mp3`

**Modified Files:**
- `app/layout.tsx` - Add AudioControls to header
- `app/settings/page.tsx` - Add audio settings section
- `hooks/useWebSocket.ts` - Trigger audio on alarm_raised event

### Backend Changes

**Database:**
- Add `audio_enabled`, `audio_volume`, `audio_muted` columns to users table

**API:**
- `GET /api/v1/users/{id}/audio-settings`
- `PUT /api/v1/users/{id}/audio-settings`

### Example Hook Implementation

```typescript
// hooks/useAlarmAudio.ts
import { useEffect, useRef, useCallback } from 'react';

export function useAlarmAudio() {
  const audioContext = useRef<AudioContext | null>(null);

  const playAlarm = useCallback((severity: string) => {
    if (!audioContext.current) {
      audioContext.current = new AudioContext();
    }

    const soundFile = {
      'CRITICAL': '/sounds/alarm-critical.mp3',
      'EMERGENCY': '/sounds/alarm-critical.mp3',
      'WARNING': '/sounds/alarm-warning.mp3',
      'INFO': '/sounds/alarm-info.mp3',
    }[severity] || '/sounds/alarm-info.mp3';

    // Play the sound...
  }, []);

  return { playAlarm };
}
```

## Testing Requirements

1. Verify audio plays on new alarms in all major browsers (Chrome, Firefox, Edge, Safari)
2. Verify mute button silences all audio
3. Verify settings persist across sessions
4. Verify quiet hours functionality
5. Verify audio stops on alarm acknowledgment
6. Test with screen reader software

## Resources Required

- Sound designer for alarm audio files (or use royalty-free sounds)
- Browser compatibility testing
- Accessibility review

## Dependencies

- None (can be implemented independently)

## Estimated Effort

- Development: 2-3 sprints
- Testing: 1 sprint
- Documentation: 0.5 sprint

## Notes

- Consider adding haptic feedback for mobile devices
- Browser may require user interaction before audio can play (autoplay policy)
- Store user audio preferences in localStorage as fallback

---

*Created: 2025-12-23*
*Last Updated: 2025-12-23*
