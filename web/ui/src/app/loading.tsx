/**
 * Global Loading State
 * Displays a skeleton loader while routes are loading.
 *
 * ISA-101 Compliance:
 * - Gray/neutral colors (loading is not an error state)
 * - Clear visual indication that data is loading
 * - Maintains layout structure during load
 */

export default function Loading() {
  return (
    <div className="min-h-screen bg-hmi-bg p-6 animate-pulse">
      {/* Header Skeleton */}
      <div className="max-w-[1800px] mx-auto">
        {/* Page Title */}
        <div className="flex items-center justify-between mb-6">
          <div className="h-8 w-48 bg-hmi-border rounded-lg" />
          <div className="h-10 w-32 bg-hmi-border rounded-lg" />
        </div>

        {/* Stats Cards Skeleton */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-hmi-panel rounded-lg border border-hmi-border p-4">
              <div className="h-4 w-20 bg-hmi-border rounded mb-2" />
              <div className="h-8 w-16 bg-hmi-border rounded" />
            </div>
          ))}
        </div>

        {/* Main Content Skeleton */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Large Panel */}
          <div className="lg:col-span-2 bg-hmi-panel rounded-lg border border-hmi-border p-6">
            <div className="h-6 w-32 bg-hmi-border rounded mb-4" />
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="flex items-center gap-4">
                  <div className="h-10 w-10 bg-hmi-border rounded-full" />
                  <div className="flex-1">
                    <div className="h-4 w-full bg-hmi-border rounded mb-2" />
                    <div className="h-3 w-2/3 bg-hmi-border rounded" />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Side Panel */}
          <div className="bg-hmi-panel rounded-lg border border-hmi-border p-6">
            <div className="h-6 w-24 bg-hmi-border rounded mb-4" />
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="p-3 bg-hmi-bg-alt rounded-lg">
                  <div className="h-4 w-full bg-hmi-border rounded mb-2" />
                  <div className="h-3 w-1/2 bg-hmi-border rounded" />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Loading Indicator */}
        <div className="fixed bottom-4 right-4 bg-hmi-panel rounded-lg shadow-lg border border-hmi-border px-4 py-3 flex items-center gap-3">
          <div className="w-5 h-5 border-2 border-alarm-blue border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-hmi-text-secondary">Loading...</span>
        </div>
      </div>
    </div>
  );
}
