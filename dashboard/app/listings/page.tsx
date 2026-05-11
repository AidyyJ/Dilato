"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Listing, ListingStatus } from "@/lib/api";

const statuses: ListingStatus[] = ["draft", "active", "ended", "sold"];

export default function ListingsPage() {
  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [skip, setSkip] = useState(0);
  const limit = 20;
  const [statusFilter, setStatusFilter] = useState<ListingStatus | "">("");

  useEffect(() => {
    api.listings
      .list({ skip, limit, status: statusFilter || undefined })
      .then((data) => {
        setListings(data);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load listings");
        setLoading(false);
      });
  }, [skip, statusFilter]);

  async function publish(listingId: number) {
    try {
      await api.listings.updateStatus(listingId, "active");
      setListings((prev) =>
        prev.map((l) => (l.id === listingId ? { ...l, status: "active" as ListingStatus } : l))
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Publish failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Listings</h1>
          <p className="text-neutral-600 dark:text-neutral-400 mt-1">
            Manage eBay listings and drafts.
          </p>
        </div>
        <Link
          href="/listings/new"
          className="inline-flex items-center justify-center px-4 py-2 rounded-md bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 text-sm font-medium hover:bg-neutral-800 dark:hover:bg-neutral-200 transition-colors"
        >
          Create Listing
        </Link>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <div className="flex items-center gap-2">
        <label htmlFor="status-filter" className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          Filter by status:
        </label>
        <select
          id="status-filter"
          value={statusFilter}
          onChange={(e) => {
            setLoading(true);
            setStatusFilter(e.target.value as ListingStatus | "");
            setSkip(0);
          }}
          className="text-sm rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-neutral-400"
        >
          <option value="">All</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </option>
          ))}
        </select>
      </div>

      <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-neutral-50 dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Title</th>
                <th className="px-4 py-3 text-left font-medium">Product ID</th>
                <th className="px-4 py-3 text-left font-medium">Price</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">eBay Item ID</th>
                <th className="px-4 py-3 text-left font-medium">Created</th>
                <th className="px-4 py-3 text-left font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-neutral-500">
                    Loading…
                  </td>
                </tr>
              ) : listings.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-neutral-500">
                    No listings found.
                  </td>
                </tr>
              ) : (
                listings.map((l) => (
                  <tr key={l.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-900/50">
                    <td className="px-4 py-3 max-w-xs truncate">{l.title}</td>
                    <td className="px-4 py-3">{l.product_id}</td>
                    <td className="px-4 py-3">{l.listing_price}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={l.status} />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{l.ebay_item_id ?? "—"}</td>
                    <td className="px-4 py-3 text-neutral-500">
                      {new Date(l.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3">
                      {l.status === "draft" && (
                        <button
                          onClick={() => publish(l.id)}
                          className="text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:underline"
                        >
                          Publish
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between px-4 py-3 border-t border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900">
          <button
            onClick={() => {
              setLoading(true);
              setSkip((s) => Math.max(0, s - limit));
            }}
            disabled={skip === 0}
            className="text-sm font-medium text-neutral-700 dark:text-neutral-300 disabled:opacity-40 hover:underline"
          >
            Previous
          </button>
          <span className="text-sm text-neutral-600 dark:text-neutral-400">
            Page {Math.floor(skip / limit) + 1}
          </span>
          <button
            onClick={() => {
              setLoading(true);
              setSkip((s) => s + limit);
            }}
            disabled={listings.length < limit}
            className="text-sm font-medium text-neutral-700 dark:text-neutral-300 disabled:opacity-40 hover:underline"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: ListingStatus }) {
  const styles: Record<ListingStatus, string> = {
    draft: "bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-300",
    active: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300",
    ended: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
    sold: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${styles[status]}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}
