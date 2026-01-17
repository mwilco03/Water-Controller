'use client';

/**
 * React Query Provider
 *
 * Provides centralized data fetching, caching, and state management using
 * TanStack React Query (formerly React Query).
 *
 * Benefits:
 * - Automatic caching and background refetching
 * - Optimistic updates
 * - Request deduplication
 * - Automatic retries with exponential backoff
 * - DevTools for debugging
 *
 * Replaces manual useState + useEffect patterns throughout the application.
 */

import { QueryClient, QueryClientProvider as TanStackQueryClientProvider } from '@tanstack/react-query';
import { ReactNode, useState } from 'react';

/**
 * Query client configuration optimized for SCADA HMI.
 *
 * Guidelines:
 * - staleTime: How long data is considered fresh (no refetch)
 * - cacheTime: How long unused data stays in cache
 * - refetchInterval: Background polling (use sparingly, prefer WebSocket)
 * - retry: Number of automatic retries on failure
 */
function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Data is considered fresh for 30 seconds
        // Prevents unnecessary refetches when switching between pages
        staleTime: 30 * 1000,

        // Keep unused data in cache for 5 minutes
        // Allows fast navigation back to previously viewed pages
        gcTime: 5 * 60 * 1000,

        // Retry failed requests 3 times with exponential backoff
        // Critical for industrial environments with occasional network issues
        retry: 3,
        retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),

        // Don't refetch on window focus (SCADA operators often have multiple windows)
        refetchOnWindowFocus: false,

        // Refetch on mount only if data is stale
        refetchOnMount: 'if-stale' as const,

        // Don't refetch on reconnect (WebSocket handles real-time updates)
        refetchOnReconnect: false,

        // Don't poll by default (WebSocket provides real-time updates)
        // Individual queries can override this for fallback polling
        refetchInterval: false,
      },
      mutations: {
        // Retry mutations (writes) only once
        // Multiple retries could cause duplicate actions (pump starts twice, etc.)
        retry: 1,
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined = undefined;

function getQueryClient() {
  if (typeof window === 'undefined') {
    // Server: always make a new query client
    return makeQueryClient();
  } else {
    // Browser: use singleton pattern to avoid creating new client on every render
    if (!browserQueryClient) browserQueryClient = makeQueryClient();
    return browserQueryClient;
  }
}

interface Props {
  children: ReactNode;
}

export function QueryClientProvider({ children }: Props) {
  // Use useState to ensure the query client is stable during the component lifecycle
  // This prevents creating new clients on re-renders
  const [queryClient] = useState(() => getQueryClient());

  return (
    <TanStackQueryClientProvider client={queryClient}>
      {children}
      {/* Uncomment to enable React Query DevTools in development */}
      {/* {process.env.NODE_ENV === 'development' && (
        <ReactQueryDevtools initialIsOpen={false} />
      )} */}
    </TanStackQueryClientProvider>
  );
}

/**
 * Hook to access the query client for manual cache operations.
 *
 * Usage:
 *   const queryClient = useQueryClient();
 *   queryClient.invalidateQueries(['rtus']); // Force refetch
 *   queryClient.setQueryData(['rtu', id], newData); // Update cache
 */
export { useQueryClient } from '@tanstack/react-query';
