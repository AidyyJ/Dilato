"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex items-center justify-center bg-white dark:bg-neutral-950 text-neutral-900 dark:text-neutral-100 px-4">
        <div className="rounded-lg border border-red-200 dark:border-red-900/30 bg-red-50 dark:bg-red-900/10 p-8 max-w-md w-full text-center">
          <h2 className="text-lg font-semibold text-red-800 dark:text-red-300">
            Application Error
          </h2>
          <p className="mt-2 text-sm text-red-700 dark:text-red-400">
            {error.message || "A critical error occurred. Please try again."}
          </p>
          {error.digest && (
            <p className="mt-1 text-xs text-red-600 dark:text-red-500 font-mono">
              Digest: {error.digest}
            </p>
          )}
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              onClick={() => unstable_retry()}
              className="inline-flex items-center justify-center px-4 py-2 rounded-md bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 text-sm font-medium hover:bg-neutral-800 dark:hover:bg-neutral-200 transition-colors"
            >
              Try again
            </button>
            <button
              onClick={() => window.location.reload()}
              className="inline-flex items-center justify-center px-4 py-2 rounded-md border border-neutral-300 dark:border-neutral-700 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-900 transition-colors"
            >
              Reload page
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
