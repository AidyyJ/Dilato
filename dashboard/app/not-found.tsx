import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-[50vh] flex flex-col items-center justify-center text-center px-4">
      <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-8 max-w-md w-full">
        <h2 className="text-lg font-semibold text-neutral-800 dark:text-neutral-200">
          404 — Page Not Found
        </h2>
        <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
          The page you are looking for does not exist.
        </p>
        <div className="mt-6">
          <Link
            href="/"
            className="inline-flex items-center justify-center px-4 py-2 rounded-md bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 text-sm font-medium hover:bg-neutral-800 dark:hover:bg-neutral-200 transition-colors"
          >
            Return Home
          </Link>
        </div>
      </div>
    </div>
  );
}
