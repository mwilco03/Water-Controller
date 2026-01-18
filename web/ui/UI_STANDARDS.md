# Water-Controller UI/UX Standards

## Core Principle
INFORMATION DENSITY OVER AESTHETICS. Operators need data, not decoration.

## Sizing Standards

### Buttons
| Type | Height | Use Case |
|------|--------|----------|
| Compact | 28-32px | Inline actions, table rows |
| Default | 36px | Standard actions |
| Primary CTA | 40px | One per screen region max |
| PROHIBITED | 44px+ | Never for visual size |

Touch target (tap area) may be 44px via padding/margin. Visual size stays compact.

### Icons
| Context | Size | Notes |
|---------|------|-------|
| Inline (text) | 16px | Matches text height |
| Navigation | 20-24px | Nav items, tabs |
| Empty state | 32-40px max | Indicator, not hero |
| PROHIBITED | 48px+ | Never decorative |

### Spacing
| Token | Value | Use |
|-------|-------|-----|
| xs | 4px | Tight grouping |
| sm | 8px | Related elements |
| md | 12-16px | Component padding |
| lg | 20-24px | Section separation |
| PROHIBITED | 32px+ | Never for padding |

### Empty States
- Total height: 80-120px max
- Icon: 32-40px max
- Text: 1-2 lines
- Action: Single compact button
- NO: hero illustrations, excessive margins, centered viewport layouts

## Information Hierarchy

### Above-Fold Requirements (mobile)
Must be visible without scroll:
1. Current status (connection, mode)
2. Critical counts (alarms, online RTUs)
3. Primary action

### Data Display
- Process values: prominent, monospace
- Quality indicators: subtle but visible
- Timestamps: compact, relative when recent
- Units: smaller than values

## Responsive Behavior

### Mobile (< 640px)
- Stack layouts vertically
- KEEP component sizes small
- Reduce padding (p-4 max on cards)
- No horizontal scroll

### Tablet (640-1024px)
- 2-column grids
- Same component sizes as mobile
- Moderate padding (p-4 to p-6)

### Desktop (> 1024px)
- Multi-column layouts
- Higher information density
- Standard padding

## Prohibited Patterns

| Pattern | Why |
|---------|-----|
| p-8, p-10, p-12 | Wastes space |
| h-48, h-64 on containers | Forces inflation |
| min-height on decorative elements | Prevents natural sizing |
| Centered giant icons | Empty calories |
| Full-width buttons (outside modals) | Oversized appearance |
| text-2xl+ on buttons | Unbalanced hierarchy |

## Acceptable Patterns

| Need | Solution |
|------|----------|
| Touch-friendly | 44px tap zone via padding, 36px visual |
| Empty state | Compact card, small icon, inline button |
| Modal actions | Full-width buttons OK inside constrained modal |
| Loading state | Subtle spinner, skeleton, NOT centered hero |

## Component Standards

### Cards
- Padding: p-3 to p-4
- Header: py-2 px-3, border-bottom
- Compact by default, expand with content

### Forms
- Input height: 36-40px
- Labels: above inputs, text-sm
- Buttons: right-aligned, compact

### Modals (acceptable use)
- Width: max-w-sm to max-w-md
- Padding: p-4 to p-6
- Buttons: can be full-width here
- Use for: confirmations, forms, detail views
- NOT for: empty states, status messages

## CSS Variables (globals.css)

```css
--touch-target-min: 44px;
--touch-target-comfortable: 48px;
--button-min-height: 36px;
--list-item-min-height: 48px;
--nav-item-min-height: 48px;
```

## Review Checklist

Before merge, verify on mobile viewport:
- [ ] Can see status + stats + action without scroll
- [ ] No element taller than 100px unless content requires
- [ ] Buttons visually 32-40px tall
- [ ] Icons 40px or smaller
- [ ] No padding > 24px on any element
