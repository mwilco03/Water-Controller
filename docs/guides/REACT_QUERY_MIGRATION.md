# React Query Migration Guide

**Date:** 2026-01-17
**Status:** In Progress
**Impact:** Eliminates prop drilling, improves caching, standardizes state management

---

## Summary

This guide shows how to migrate from manual `useState` + `useEffect` data fetching to **React Query** (TanStack Query), the industry-standard data fetching library for React.

### Benefits

✅ **Automatic Caching** - Fetched data is cached and shared across components
✅ **Background Refetching** - Stale data is automatically refreshed
✅ **Optimistic Updates** - UI updates immediately, rollback on error
✅ **Request Deduplication** - Multiple components can request same data without multiple fetches
✅ **Automatic Retries** - Failed requests retry with exponential backoff
✅ **DevTools** - Visualize queries and cache in browser
✅ **TypeScript Support** - Full type safety for queries and mutations

### Performance Impact

- **Eliminated prop drilling:** Components fetch their own data instead of receiving it through 3-4 levels of props
- **Reduced re-renders:** Only components using the data re-render when it changes
- **Smart refetching:** Data is only refetched when stale, not on every mount
- **Request deduplication:** 10 components requesting same data = 1 network request

---

## Installation

### 1. Add Dependency

Already added to `package.json`:

```json
{
  "dependencies": {
    "@tanstack/react-query": "^5.56.2"
  }
}
```

Install:

```bash
cd web/ui
npm install
```

### 2. Add Query Client Provider

Update `/web/ui/src/app/layout.tsx` to wrap the app with `QueryClientProvider`:

```tsx
// web/ui/src/app/layout.tsx
import { QueryClientProvider } from '@/contexts/QueryClientProvider';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <QueryClientProvider>
          <CommandModeProvider>
            <HMIToastProvider>
              {children}
            </HMIToastProvider>
          </CommandModeProvider>
        </QueryClientProvider>
      </body>
    </html>
  );
}
```

**Order matters:** `QueryClientProvider` should wrap other providers that might use queries.

---

## Migration Patterns

### Pattern 1: Simple Data Fetch

**Before (useState + useEffect):**

```tsx
function RTUList() {
  const [rtus, setRTUs] = useState<RTU[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchRTUs = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/v1/rtus');
        if (!response.ok) throw new Error('Failed to fetch RTUs');
        const data = await response.json();
        setRTUs(data.data || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchRTUs();

    // Poll every 10 seconds
    const interval = setInterval(fetchRTUs, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <Spinner />;
  if (error) return <Error message={error} />;

  return (
    <div>
      {rtus.map(rtu => <RTUCard key={rtu.id} rtu={rtu} />)}
    </div>
  );
}
```

**After (React Query):**

```tsx
import { useRTUs } from '@/hooks/useRTUs';

function RTUList() {
  const { data: rtus = [], isLoading, error } = useRTUs();

  if (isLoading) return <Spinner />;
  if (error) return <Error message={error.message} />;

  return (
    <div>
      {rtus.map(rtu => <RTUCard key={rtu.id} rtu={rtu} />)}
    </div>
  );
}
```

**Lines of code:** 35 → 12 (66% reduction)

**Benefits:**
- Automatic polling (configured in hook)
- Automatic caching (other components get cached data)
- Automatic error retry
- No manual cleanup needed

---

### Pattern 2: Prop Drilling Elimination

**Before (Props passed through multiple levels):**

```tsx
// Page level
function DashboardPage() {
  const [rtus, setRTUs] = useState<RTU[]>([]);

  useEffect(() => {
    // fetch RTUs...
  }, []);

  return <RTUDashboard rtus={rtus} />;
}

// Component level 1
function RTUDashboard({ rtus }: { rtus: RTU[] }) {
  return <RTUGrid rtus={rtus} />;
}

// Component level 2
function RTUGrid({ rtus }: { rtus: RTU[] }) {
  return (
    <div className="grid">
      {rtus.map(rtu => <RTUCard key={rtu.id} rtu={rtu} />)}
    </div>
  );
}

// Component level 3
function RTUCard({ rtu }: { rtu: RTU }) {
  return <div>{rtu.station_name}</div>;
}
```

**After (Each component fetches its own data):**

```tsx
// Page level - no props!
function DashboardPage() {
  return <RTUDashboard />;
}

// Component level 1 - no props!
function RTUDashboard() {
  return <RTUGrid />;
}

// Component level 2 - fetches data here
function RTUGrid() {
  const { data: rtus = [] } = useRTUs();

  return (
    <div className="grid">
      {rtus.map(rtu => <RTUCard key={rtu.id} rtuId={rtu.id} />)}
    </div>
  );
}

// Component level 3 - fetches its own detail if needed
function RTUCard({ rtuId }: { rtuId: number }) {
  const { data: rtu } = useRTU(rtuId);
  if (!rtu) return null;

  return <div>{rtu.station_name}</div>;
}
```

**Benefits:**
- No props needed (eliminated 3 levels of prop drilling)
- Each component is self-contained
- Data is cached - `useRTUs()` in multiple components = single network request
- Components can be moved anywhere without breaking

---

### Pattern 3: WebSocket Integration

**Before (Manual state updates from WebSocket):**

```tsx
function RTUDashboard() {
  const [rtus, setRTUs] = useState<RTU[]>([]);

  useWebSocket((message) => {
    if (message.type === 'rtu_updated') {
      setRTUs(prev => prev.map(rtu =>
        rtu.id === message.rtu_id
          ? { ...rtu, connection_state: message.state }
          : rtu
      ));
    }
  });

  return <div>{/* ... */}</div>;
}
```

**After (React Query cache update):**

```tsx
import { useRTUWebSocketSync } from '@/hooks/useRTUs';

function RootLayout({ children }: { children: React.ReactNode }) {
  const message = useWebSocket();

  // Sync WebSocket messages with React Query cache
  useRTUWebSocketSync(message);

  return <div>{children}</div>;
}

// Child components automatically receive updated data
function RTUDashboard() {
  const { data: rtus = [] } = useRTUs();
  // rtus is automatically updated when WebSocket message arrives!

  return <div>{/* ... */}</div>;
}
```

**Benefits:**
- WebSocket updates handled in one place (layout)
- All components using `useRTUs()` automatically receive updates
- No manual state synchronization needed
- Cache is source of truth

---

### Pattern 4: Mutations with Optimistic Updates

**Before (Manual optimistic update):**

```tsx
function ActuatorControl({ rtuId, actuatorId }: Props) {
  const [state, setState] = useState(false);
  const [pending, setPending] = useState(false);

  const handleToggle = async () => {
    const previousState = state;
    setState(!state); // Optimistic update
    setPending(true);

    try {
      await fetch(`/api/v1/rtus/${rtuId}/actuators/${actuatorId}`, {
        method: 'POST',
        body: JSON.stringify({ state: !state }),
      });
    } catch (err) {
      setState(previousState); // Rollback on error
      alert('Failed to control actuator');
    } finally {
      setPending(false);
    }
  };

  return (
    <button onClick={handleToggle} disabled={pending}>
      {state ? 'ON' : 'OFF'}
    </button>
  );
}
```

**After (React Query mutation):**

```tsx
import { useRTU, useControlActuator } from '@/hooks/useRTUs';

function ActuatorControl({ rtuId, actuatorId }: Props) {
  const { data: rtu } = useRTU(rtuId);
  const controlActuator = useControlActuator();

  const actuator = rtu?.actuators.find(a => a.id === actuatorId);
  if (!actuator) return null;

  const handleToggle = () => {
    controlActuator.mutate({
      rtuId,
      actuatorId,
      state: !actuator.state,
    });
  };

  return (
    <button
      onClick={handleToggle}
      disabled={controlActuator.isPending}
    >
      {actuator.state ? 'ON' : 'OFF'}
    </button>
  );
}
```

**Benefits:**
- Automatic optimistic update (instant UI feedback)
- Automatic rollback on error
- Automatic cache invalidation on success
- Loading state built-in
- No manual state management

---

## Advanced Patterns

### Dependent Queries

Fetch data that depends on other data:

```tsx
function RTUSensorDetails({ rtuId }: { rtuId: number }) {
  // First, fetch the RTU
  const { data: rtu } = useRTU(rtuId);

  // Then, fetch sensor details (only if RTU is loaded)
  const { data: sensorDetails } = useQuery({
    queryKey: ['sensor-details', rtuId],
    queryFn: () => fetch(`/api/v1/rtus/${rtuId}/sensors/details`).then(r => r.json()),
    // Only fetch if we have the RTU loaded
    enabled: !!rtu,
  });

  return <div>{/* ... */}</div>;
}
```

### Infinite Queries (Pagination)

Load more data as user scrolls:

```tsx
function AlarmHistory() {
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['alarms', 'infinite'],
    queryFn: ({ pageParam = 0 }) =>
      fetch(`/api/v1/alarms?offset=${pageParam}&limit=50`).then(r => r.json()),
    getNextPageParam: (lastPage, pages) =>
      lastPage.hasMore ? pages.length * 50 : undefined,
  });

  return (
    <div>
      {data?.pages.map(page =>
        page.alarms.map(alarm => <AlarmRow key={alarm.id} alarm={alarm} />)
      )}
      {hasNextPage && (
        <button onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
          Load More
        </button>
      )}
    </div>
  );
}
```

### Suspense Mode

Use React Suspense for cleaner loading states:

```tsx
function RTUListSuspense() {
  const { data: rtus } = useSuspenseQuery({
    queryKey: ['rtus'],
    queryFn: () => fetch('/api/v1/rtus').then(r => r.json()),
  });

  // No loading state needed - Suspense handles it
  return (
    <div>
      {rtus.map(rtu => <RTUCard key={rtu.id} rtu={rtu} />)}
    </div>
  );
}

// Wrap in Suspense boundary
function Page() {
  return (
    <Suspense fallback={<Spinner />}>
      <RTUListSuspense />
    </Suspense>
  );
}
```

---

## Migration Checklist

### Components to Migrate (Priority Order)

1. **RTU List** (`/web/ui/src/app/rtus/page.tsx`)
   - [x] Create `useRTUs()` hook
   - [ ] Replace useState with useQuery
   - [ ] Add WebSocket sync

2. **RTU Detail** (`/web/ui/src/app/rtus/[id]/page.tsx`)
   - [x] Create `useRTU(id)` hook
   - [ ] Replace useState with useQuery
   - [ ] Migrate sensors/actuators to use cache

3. **Alarm List** (`/web/ui/src/app/alarms/page.tsx`)
   - [ ] Create `useAlarms()` hook
   - [ ] Replace useState with useQuery
   - [ ] Add pagination with useInfiniteQuery

4. **Trend Chart** (`/web/ui/src/components/TrendChart.tsx`)
   - [ ] Create `useTrendData()` hook
   - [ ] Use optimized trends API endpoint
   - [ ] Add time range selection

5. **System Status** (`/web/ui/src/app/page.tsx`)
   - [ ] Reuse existing hooks (useRTUs, useAlarms)
   - [ ] Remove prop passing
   - [ ] Add auto-refresh

### Layout Updates

- [x] Add QueryClientProvider to root layout
- [ ] Add WebSocket sync in root layout
- [ ] Remove manual data fetching from layout
- [ ] Remove prop passing through layout

### DevTools (Optional)

Add React Query DevTools for development:

```bash
npm install @tanstack/react-query-devtools
```

```tsx
// web/ui/src/contexts/QueryClientProvider.tsx
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';

export function QueryClientProvider({ children }: Props) {
  return (
    <TanStackQueryClientProvider client={queryClient}>
      {children}
      {process.env.NODE_ENV === 'development' && (
        <ReactQueryDevtools initialIsOpen={false} />
      )}
    </TanStackQueryClientProvider>
  );
}
```

---

## Testing

### Query Mocking

Mock queries in tests:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

test('RTU list renders', async () => {
  const queryClient = createTestQueryClient();

  // Set mock data in cache
  queryClient.setQueryData(['rtus', 'list'], [
    { id: 1, station_name: 'rtu-1', connection_state: 'ONLINE' },
  ]);

  render(
    <QueryClientProvider client={queryClient}>
      <RTUList />
    </QueryClientProvider>
  );

  expect(screen.getByText('rtu-1')).toBeInTheDocument();
});
```

---

## Performance Monitoring

### Cache Size

Monitor cache size to prevent memory leaks:

```tsx
import { useQueryClient } from '@tanstack/react-query';

function DebugPanel() {
  const queryClient = useQueryClient();
  const cache = queryClient.getQueryCache();

  return (
    <div>
      <p>Queries in cache: {cache.getAll().length}</p>
      <button onClick={() => queryClient.clear()}>Clear Cache</button>
    </div>
  );
}
```

### Request Logging

Log all requests for debugging:

```tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      onSuccess: (data, query) => {
        console.log(`Query ${query.queryKey} succeeded:`, data);
      },
      onError: (error, query) => {
        console.error(`Query ${query.queryKey} failed:`, error);
      },
    },
  },
});
```

---

## References

- [TanStack Query Docs](https://tanstack.com/query/latest/docs/framework/react/overview)
- [React Query DevTools](https://tanstack.com/query/latest/docs/framework/react/devtools)
- [Query Key Factory Pattern](https://tkdodo.eu/blog/effective-react-query-keys)
- [Optimistic Updates Guide](https://tanstack.com/query/latest/docs/framework/react/guides/optimistic-updates)

---

## Conclusion

React Query provides:

✅ **66% less code** for data fetching
✅ **Eliminates prop drilling** (3-4 level deep props removed)
✅ **Automatic caching** and background refetching
✅ **Optimistic updates** for instant UI feedback
✅ **WebSocket integration** with cache invalidation
✅ **Type safety** with full TypeScript support

**Next Steps:**
1. Finish migrating high-traffic components (RTU list, alarms)
2. Add DevTools for development
3. Add unit tests for custom hooks
4. Monitor cache size in production
