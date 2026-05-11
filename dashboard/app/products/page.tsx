"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Product, SourcingResult } from "@/lib/api";

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [skip, setSkip] = useState(0);
  const limit = 20;
  const [sourcing, setSourcing] = useState(false);
  const [sourcingResults, setSourcingResults] = useState<SourcingResult[] | null>(null);

  useEffect(() => {
    api.products
      .list({ skip, limit })
      .then((data) => {
        setProducts(data);
        setError(null);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load products");
        setLoading(false);
      });
  }, [skip]);

  async function handleSource() {
    setSourcing(true);
    setError(null);
    try {
      const data = await api.sourcing.search({ max_results: 20 });
      setSourcingResults(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Sourcing failed");
    } finally {
      setSourcing(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Products</h1>
          <p className="text-neutral-600 dark:text-neutral-400 mt-1">
            Browse sourced Amazon products.
          </p>
        </div>
        <button
          onClick={handleSource}
          disabled={sourcing}
          className="inline-flex items-center justify-center px-4 py-2 rounded-md bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 text-sm font-medium hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-50 transition-colors"
        >
          {sourcing ? "Sourcing…" : "Source Products"}
        </button>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {sourcingResults && (
        <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Sourcing Results</h2>
            <button
              onClick={() => setSourcingResults(null)}
              className="text-sm text-neutral-600 dark:text-neutral-400 hover:underline"
            >
              Dismiss
            </button>
          </div>
          {sourcingResults.length === 0 ? (
            <p className="text-sm text-neutral-600 dark:text-neutral-400">No results found.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-neutral-500 dark:text-neutral-400 border-b border-neutral-200 dark:border-neutral-800">
                    <th className="py-2 pr-4">ASIN</th>
                    <th className="py-2 pr-4">Title</th>
                    <th className="py-2 pr-4">Price</th>
                    <th className="py-2 pr-4">Est. eBay</th>
                    <th className="py-2 pr-4">Margin</th>
                  </tr>
                </thead>
                <tbody>
                  {sourcingResults.map((r) => (
                    <tr key={r.asin} className="border-b border-neutral-100 dark:border-neutral-800">
                      <td className="py-2 pr-4 font-mono text-xs">{r.asin}</td>
                      <td className="py-2 pr-4 max-w-xs truncate">{r.title}</td>
                      <td className="py-2 pr-4">{r.amazon_price}</td>
                      <td className="py-2 pr-4">{r.estimated_ebay_price ?? "—"}</td>
                      <td className="py-2 pr-4">
                        {r.estimated_margin !== undefined ? `${(r.estimated_margin * 100).toFixed(1)}%` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-neutral-50 dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300">
              <tr>
                <th className="px-4 py-3 text-left font-medium">ASIN</th>
                <th className="px-4 py-3 text-left font-medium">Title</th>
                <th className="px-4 py-3 text-left font-medium">Price</th>
                <th className="px-4 py-3 text-left font-medium">Category</th>
                <th className="px-4 py-3 text-left font-medium">Active</th>
                <th className="px-4 py-3 text-left font-medium">Last Synced</th>
                <th className="px-4 py-3 text-left font-medium">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-neutral-500">
                    Loading…
                  </td>
                </tr>
              ) : products.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-neutral-500">
                    No products found.
                  </td>
                </tr>
              ) : (
                products.map((p) => (
                  <tr key={p.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-900/50">
                    <td className="px-4 py-3 font-mono text-xs">{p.asin}</td>
                    <td className="px-4 py-3 max-w-xs truncate">{p.title}</td>
                    <td className="px-4 py-3">{p.amazon_price ?? "—"}</td>
                    <td className="px-4 py-3">{p.category ?? "—"}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          p.is_active
                            ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
                            : "bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-300"
                        }`}
                      >
                        {p.is_active ? "Yes" : "No"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-neutral-500">
                      {p.last_synced_at ? new Date(p.last_synced_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/listings/new?productId=${p.id}`}
                        className="text-sm text-neutral-700 dark:text-neutral-300 hover:underline"
                      >
                        Create Listing
                      </Link>
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
            disabled={products.length < limit}
            className="text-sm font-medium text-neutral-700 dark:text-neutral-300 disabled:opacity-40 hover:underline"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
