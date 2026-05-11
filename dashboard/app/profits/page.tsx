"use client";

import { useEffect, useState } from "react";
import { api, OrderProfitDetailOut, ProfitSummaryOut, OrderStatus } from "@/lib/api";
import Skeleton from "@/components/Skeleton";

const statuses: OrderStatus[] = ["pending", "shipped", "delivered", "cancelled", "returned"];

export default function ProfitsPage() {
  const [summary, setSummary] = useState<ProfitSummaryOut | null>(null);
  const [details, setDetails] = useState<OrderProfitDetailOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [skip, setSkip] = useState(0);
  const limit = 20;
  const [statusFilter, setStatusFilter] = useState<OrderStatus | "">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useEffect(() => {
    const params: Parameters<typeof api.profit.details>[0] = { skip, limit };
    if (statusFilter) params.status = statusFilter;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;

    Promise.all([
      api.profit.summary(
        statusFilter ? { status: statusFilter, date_from: dateFrom || undefined, date_to: dateTo || undefined } : {}
      ),
      api.profit.details(params),
    ])
      .then(([s, d]) => {
        setSummary(s);
        setDetails(d);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load profit data");
      })
      .finally(() => setLoading(false));
  }, [skip, statusFilter, dateFrom, dateTo]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Profit Views</h1>
        <p className="text-neutral-600 dark:text-neutral-400 mt-1">
          Summary and per-order profit breakdowns.
        </p>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {loading && !summary ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : summary ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <SummaryCard label="Total Orders" value={String(summary.total_orders)} />
          <SummaryCard label="Total Revenue" value={summary.total_revenue} />
          <SummaryCard label="Total Profit" value={summary.total_profit ?? "—"} />
          <SummaryCard label="Avg Margin %" value={summary.average_margin_percent ? `${summary.average_margin_percent}%` : "—"} />
        </div>
      ) : null}

      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <label htmlFor="profit-status-filter" className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          Status:
        </label>
        <select
          id="profit-status-filter"
          value={statusFilter}
          onChange={(e) => {
            setLoading(true);
            setStatusFilter(e.target.value as OrderStatus | "");
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

        <label htmlFor="date-from" className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          From:
        </label>
        <input
          id="date-from"
          type="date"
          value={dateFrom}
          onChange={(e) => {
            setLoading(true);
            setDateFrom(e.target.value);
            setSkip(0);
          }}
          className="text-sm rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-neutral-400"
        />

        <label htmlFor="date-to" className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          To:
        </label>
        <input
          id="date-to"
          type="date"
          value={dateTo}
          onChange={(e) => {
            setLoading(true);
            setDateTo(e.target.value);
            setSkip(0);
          }}
          className="text-sm rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-neutral-400"
        />
      </div>

      <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-neutral-50 dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Order ID</th>
                <th className="px-4 py-3 text-left font-medium">eBay Order ID</th>
                <th className="px-4 py-3 text-left font-medium">Revenue</th>
                <th className="px-4 py-3 text-left font-medium">Shipping</th>
                <th className="px-4 py-3 text-left font-medium">eBay Fee</th>
                <th className="px-4 py-3 text-left font-medium">Purchase Cost</th>
                <th className="px-4 py-3 text-left font-medium">Profit</th>
                <th className="px-4 py-3 text-left font-medium">Margin %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-neutral-500">
                    Loading…
                  </td>
                </tr>
              ) : details.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-neutral-500">
                    No profit details found.
                  </td>
                </tr>
              ) : (
                details.map((d) => (
                  <tr key={d.order_id} className="hover:bg-neutral-50 dark:hover:bg-neutral-900/50">
                    <td className="px-4 py-3 font-mono text-xs">{d.order_id}</td>
                    <td className="px-4 py-3 font-mono text-xs">{d.ebay_order_id ?? "—"}</td>
                    <td className="px-4 py-3">{d.sale_price}</td>
                    <td className="px-4 py-3">{d.shipping_cost ?? "—"}</td>
                    <td className="px-4 py-3">{d.ebay_fee ?? "—"}</td>
                    <td className="px-4 py-3">{d.purchase_cost ?? "—"}</td>
                    <td className={`px-4 py-3 font-medium ${d.profit != null && Number(d.profit) >= 0 ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>
                      {d.profit ?? "—"}
                    </td>
                    <td className="px-4 py-3">{d.margin_percent ? `${d.margin_percent}%` : "—"}</td>
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
            disabled={details.length < limit}
            className="text-sm font-medium text-neutral-700 dark:text-neutral-300 disabled:opacity-40 hover:underline"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-5">
      <p className="text-sm text-neutral-500">{label}</p>
      <p className="text-xl font-semibold mt-1">{value}</p>
    </div>
  );
}
