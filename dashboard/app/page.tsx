"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from "recharts";
import { api, Order, ProfitSummaryOut, OrderStatus, OrderProfitDetailOut } from "@/lib/api";
import KpiCard from "@/components/KpiCard";
import Skeleton from "@/components/Skeleton";

const statusStyles: Record<OrderStatus, string> = {
  pending: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300",
  shipped: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
  delivered: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300",
  cancelled: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
  returned: "bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-300",
};

function formatCurrency(n: number) {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function last30DaysRange(): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setDate(to.getDate() - 30);
  return {
    from: from.toISOString().split("T")[0],
    to: to.toISOString().split("T")[0],
  };
}

function aggregateProfitByDate(details: OrderProfitDetailOut[]): { date: string; profit: number }[] {
  const map = new Map<string, number>();
  details.forEach((d) => {
    const profit = d.profit != null ? Number(d.profit) : 0;
    const dateKey = d.created_at ? d.created_at.slice(0, 10) : "Unknown";
    map.set(dateKey, (map.get(dateKey) ?? 0) + profit);
  });
  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, profit]) => ({ date, profit }));
}

function bucketMargins(details: OrderProfitDetailOut[]): { range: string; count: number }[] {
  const buckets = [
    { label: "< 0%", min: -Infinity, max: 0 },
    { label: "0–10%", min: 0, max: 10 },
    { label: "10–20%", min: 10, max: 20 },
    { label: "20–30%", min: 20, max: 30 },
    { label: "30%+", min: 30, max: Infinity },
  ];
  const counts = buckets.map((b) => ({ range: b.label, count: 0 }));
  details.forEach((d) => {
    const m = d.margin_percent != null ? Number(d.margin_percent) : null;
    if (m == null) return;
    const idx = buckets.findIndex((b) => m >= b.min && m < b.max);
    if (idx >= 0) counts[idx].count++;
    else counts[counts.length - 1].count++; // 30%+ catch-all
  });
  return counts;
}

export default function HomePage() {
  const [summary, setSummary] = useState<ProfitSummaryOut | null>(null);
  const [recentOrders, setRecentOrders] = useState<Order[]>([]);
  const [profitDetails, setProfitDetails] = useState<OrderProfitDetailOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const { from, to } = last30DaysRange();
    Promise.all([
      api.profit.summary(),
      api.orders.list({ limit: 5 }),
      api.profit.details({ limit: 100, date_from: from, date_to: to }),
    ])
      .then(([s, orders, details]) => {
        setSummary(s);
        setRecentOrders(orders);
        setProfitDetails(details);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load dashboard data");
      })
      .finally(() => setLoading(false));
  }, []);

  const profitTrendData = useMemo(() => {
    return aggregateProfitByDate(profitDetails);
  }, [profitDetails]);

  const marginDistribution = useMemo(() => {
    return bucketMargins(profitDetails);
  }, [profitDetails]);

  const topByMargin = useMemo(() => {
    return [...profitDetails]
      .filter((d) => d.margin_percent != null)
      .sort((a, b) => Number(b.margin_percent) - Number(a.margin_percent))
      .slice(0, 5);
  }, [profitDetails]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-neutral-600 dark:text-neutral-400 mt-1">
          Overview of your Amazon-to-eBay reselling pipeline.
        </p>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* KPI Section */}
      <section aria-label="Analytics">
        <h2 className="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-3">
          Key Metrics
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {loading ? (
            <>
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </>
          ) : summary ? (
            <>
              <KpiCard
                label="Total Orders"
                value={String(summary.total_orders)}
                href="/orders"
              />
              <KpiCard
                label="Total Revenue"
                value={summary.total_revenue}
                href="/profits"
              />
              <KpiCard
                label="Total Profit"
                value={summary.total_profit ?? "—"}
                subtext={summary.average_margin_percent ? `Avg margin ${summary.average_margin_percent}%` : undefined}
                href="/profits"
              />
              <KpiCard
                label="Avg Margin %"
                value={summary.average_margin_percent ? `${summary.average_margin_percent}%` : "—"}
                href="/profits"
              />
            </>
          ) : (
            <>
              <KpiCard label="Total Orders" value="—" />
              <KpiCard label="Total Revenue" value="—" />
              <KpiCard label="Total Profit" value="—" />
              <KpiCard label="Avg Margin %" value="—" />
            </>
          )}
        </div>
      </section>

      {/* Charts Row */}
      <section aria-label="Charts">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Profit Over Time */}
          <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5">
            <h2 className="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-4">
              Profit Trend (Last 30 Days)
            </h2>
            {loading ? (
              <Skeleton className="h-64 w-full" />
            ) : profitTrendData.length === 0 ? (
              <p className="text-sm text-neutral-500 h-64 flex items-center justify-center">
                No profit trend data available.
              </p>
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={profitTrendData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <defs>
                      <linearGradient id="profitGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#059669" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#059669" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                    <XAxis dataKey="date" tick={{ fill: "#737373", fontSize: 12 }} axisLine={{ stroke: "#d4d4d4" }} />
                    <YAxis tick={{ fill: "#737373", fontSize: 12 }} axisLine={{ stroke: "#d4d4d4" }} />
                    <Tooltip
                      formatter={(value) => [`$${formatCurrency(Number(value))}`, "Profit"]}
                      contentStyle={{
                        borderRadius: "0.5rem",
                        border: "1px solid #e5e5e5",
                        fontSize: "0.875rem",
                      }}
                    />
                    <Area type="monotone" dataKey="profit" stroke="#059669" fill="url(#profitGradient)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Margin Distribution */}
          <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5">
            <h2 className="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-4">
              Margin Distribution
            </h2>
            {loading ? (
              <Skeleton className="h-64 w-full" />
            ) : marginDistribution.length === 0 || marginDistribution.every((d) => d.count === 0) ? (
              <p className="text-sm text-neutral-500 h-64 flex items-center justify-center">
                No margin distribution data available.
              </p>
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={marginDistribution} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                    <XAxis dataKey="range" tick={{ fill: "#737373", fontSize: 12 }} axisLine={{ stroke: "#d4d4d4" }} />
                    <YAxis tick={{ fill: "#737373", fontSize: 12 }} axisLine={{ stroke: "#d4d4d4" }} allowDecimals={false} />
                    <Tooltip
                      formatter={(value) => [String(value), "Orders"]}
                      contentStyle={{
                        borderRadius: "0.5rem",
                        border: "1px solid #e5e5e5",
                        fontSize: "0.875rem",
                      }}
                    />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {marginDistribution.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={["#ef4444", "#f59e0b", "#3b82f6", "#10b981", "#059669"][index % 5]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Top by Margin + Recent Orders */}
      <section aria-label="Top Orders by Margin">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
            Top Orders by Margin
          </h2>
          <Link
            href="/profits"
            className="text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:underline"
          >
            View all
          </Link>
        </div>
        <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-neutral-50 dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Order ID</th>
                  <th className="px-4 py-3 text-left font-medium">eBay Order ID</th>
                  <th className="px-4 py-3 text-left font-medium">Revenue</th>
                  <th className="px-4 py-3 text-left font-medium">Profit</th>
                  <th className="px-4 py-3 text-left font-medium">Margin %</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                {loading ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8">
                      <div className="space-y-2">
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-3/4" />
                      </div>
                    </td>
                  </tr>
                ) : topByMargin.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-neutral-500">
                      No margin data available.
                    </td>
                  </tr>
                ) : (
                  topByMargin.map((d) => (
                    <tr key={d.order_id} className="hover:bg-neutral-50 dark:hover:bg-neutral-900/50">
                      <td className="px-4 py-3 font-mono text-xs">
                        <Link href={`/orders/${d.order_id}`} className="hover:underline">
                          {d.order_id}
                        </Link>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">{d.ebay_order_id ?? "—"}</td>
                      <td className="px-4 py-3">{d.sale_price}</td>
                      <td className={`px-4 py-3 font-medium ${d.profit != null && Number(d.profit) >= 0 ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>
                        {d.profit ?? "—"}
                      </td>
                      <td className="px-4 py-3 font-semibold">{d.margin_percent ? `${d.margin_percent}%` : "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Recent Orders Section */}
      <section aria-label="Recent Orders">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
            Recent Orders
          </h2>
          <Link
            href="/orders"
            className="text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:underline"
          >
            View all
          </Link>
        </div>
        <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-neutral-50 dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Order ID</th>
                  <th className="px-4 py-3 text-left font-medium">eBay Order ID</th>
                  <th className="px-4 py-3 text-left font-medium">Sale Price</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3 text-left font-medium">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                {loading ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8">
                      <div className="space-y-2">
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-3/4" />
                      </div>
                    </td>
                  </tr>
                ) : recentOrders.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-neutral-500">
                      No recent orders.
                    </td>
                  </tr>
                ) : (
                  recentOrders.map((o) => (
                    <tr key={o.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-900/50">
                      <td className="px-4 py-3 font-mono text-xs">
                        <Link href={`/orders/${o.id}`} className="hover:underline">
                          {o.id}
                        </Link>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">{o.ebay_order_id ?? "—"}</td>
                      <td className="px-4 py-3">{o.sale_price}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusStyles[o.status]}`}>
                          {o.status.charAt(0).toUpperCase() + o.status.slice(1)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-neutral-500">
                        {new Date(o.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Quick Links Section */}
      <section aria-label="Quick Links">
        <h2 className="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-3">
          Quick Links
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <QuickCard href="/products" title="Products" description="Browse and source Amazon products." />
          <QuickCard href="/listings" title="Listings" description="Manage eBay listings and drafts." />
          <QuickCard href="/orders" title="Orders" description="Track eBay orders and fulfillment." />
          <QuickCard href="/profits" title="Profits" description="Review profit summaries and per-order breakdowns." />
          <QuickCard href="/pricing" title="Pricing Rules" description="Configure margin and markup rules." />
          <QuickCard href="/listings/new" title="Create Listing" description="Create a new eBay listing from a product." />
        </div>
      </section>
    </div>
  );
}

function QuickCard({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="block rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-5 hover:border-neutral-300 dark:hover:border-neutral-700 transition-colors"
    >
      <h3 className="font-semibold text-neutral-900 dark:text-neutral-100">{title}</h3>
      <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-2">{description}</p>
    </Link>
  );
}
