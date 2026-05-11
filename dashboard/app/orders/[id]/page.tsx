"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  api,
  Order,
  OrderProfitDetailOut,
  OrderStatus,
  FulfillmentStatus,
} from "@/lib/api";
import Skeleton from "@/components/Skeleton";

const statuses: OrderStatus[] = ["pending", "shipped", "delivered", "cancelled", "returned"];
const fulfillmentStatuses: FulfillmentStatus[] = ["not_started", "in_progress", "delivered"];

export default function OrderDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);

  const [order, setOrder] = useState<Order | null>(null);
  const [profit, setProfit] = useState<OrderProfitDetailOut | null>(null);
  const [loading, setLoading] = useState(!id || isNaN(id) ? false : true);
  const [error, setError] = useState<string | null>(!id || isNaN(id) ? "Invalid order ID" : null);

  const [purchaseUrl, setPurchaseUrl] = useState<string | null>(null);
  const [purchaseLoading, setPurchaseLoading] = useState(false);
  const [purchaseCost, setPurchaseCost] = useState("");
  const [amazonOrderId, setAmazonOrderId] = useState("");
  const [purchaseFulfillment, setPurchaseFulfillment] = useState<FulfillmentStatus>("not_started");
  const [marking, setMarking] = useState(false);

  useEffect(() => {
    if (!id || isNaN(id)) return;

    Promise.all([api.orders.get(id), api.orders.getProfit(id)])
      .then(([o, p]) => {
        setOrder(o);
        setProfit(p);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load order");
      })
      .finally(() => setLoading(false));
  }, [id]);

  async function handleGenerateLink() {
    if (!id) return;
    setPurchaseLoading(true);
    try {
      const link = await api.orders.generatePurchaseLink(id);
      setPurchaseUrl(link.purchase_url ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate link");
    } finally {
      setPurchaseLoading(false);
    }
  }

  async function handleMarkPurchased(e: React.FormEvent) {
    e.preventDefault();
    if (!id) return;
    setMarking(true);
    try {
      const updated = await api.orders.markPurchased(id, {
        purchase_cost: purchaseCost,
        amazon_order_id: amazonOrderId || undefined,
        fulfillment_status: purchaseFulfillment,
      });
      setOrder(updated);
      const p = await api.orders.getProfit(id);
      setProfit(p);
      setPurchaseCost("");
      setAmazonOrderId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to mark purchased");
    } finally {
      setMarking(false);
    }
  }

  async function handleStatusChange(status: OrderStatus) {
    if (!id) return;
    try {
      const updated = await api.orders.updateStatus(id, status);
      setOrder(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update status");
    }
  }

  async function handleFulfillmentChange(status: FulfillmentStatus) {
    if (!id) return;
    try {
      const updated = await api.orders.updateFulfillment(id, status);
      setOrder(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update fulfillment");
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-5 space-y-4">
            <Skeleton className="h-6 w-32" />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          </div>
          <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-5 space-y-4">
            <Skeleton className="h-6 w-32" />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error && !order) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold tracking-tight">Order Detail</h1>
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold tracking-tight">Order Detail</h1>
        <p className="text-neutral-500">Order not found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Order #{order.id}</h1>
          <p className="text-neutral-600 dark:text-neutral-400 mt-1">
            eBay Order: {order.ebay_order_id ?? "—"}
          </p>
        </div>
        <button
          onClick={() => router.push("/orders")}
          className="inline-flex items-center justify-center px-4 py-2 rounded-md border border-neutral-300 dark:border-neutral-700 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-900 transition-colors"
        >
          Back to Orders
        </button>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-5 space-y-4">
          <h2 className="font-semibold text-lg">Order Info</h2>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-neutral-500">Status</dt>
              <dd className="mt-1">
                <select
                  value={order.status}
                  onChange={(e) => handleStatusChange(e.target.value as OrderStatus)}
                  className="text-sm rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-2 py-1 focus:outline-none focus:ring-2 focus:ring-neutral-400"
                >
                  {statuses.map((s) => (
                    <option key={s} value={s}>
                      {s.charAt(0).toUpperCase() + s.slice(1)}
                    </option>
                  ))}
                </select>
              </dd>
            </div>
            <div>
              <dt className="text-neutral-500">Fulfillment</dt>
              <dd className="mt-1">
                <select
                  value={order.fulfillment_status ?? ""}
                  onChange={(e) =>
                    handleFulfillmentChange(e.target.value as FulfillmentStatus)
                  }
                  className="text-sm rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-2 py-1 focus:outline-none focus:ring-2 focus:ring-neutral-400"
                >
                  <option value="">—</option>
              {fulfillmentStatuses.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, " ")}
                </option>
              ))}
                </select>
              </dd>
            </div>
            <div>
              <dt className="text-neutral-500">Buyer</dt>
              <dd className="mt-1 font-medium">{order.buyer_username ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-neutral-500">Sale Price</dt>
              <dd className="mt-1 font-medium">{order.sale_price}</dd>
            </div>
            <div>
              <dt className="text-neutral-500">Quantity</dt>
              <dd className="mt-1 font-medium">{order.quantity}</dd>
            </div>
            <div>
              <dt className="text-neutral-500">Shipping Cost</dt>
              <dd className="mt-1 font-medium">{order.shipping_cost ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-neutral-500">eBay Fee</dt>
              <dd className="mt-1 font-medium">{order.ebay_fee ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-neutral-500">Tracking</dt>
              <dd className="mt-1 font-medium">
                {order.tracking_number ? `${order.tracking_number} (${order.carrier ?? "—"})` : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-neutral-500">Created</dt>
              <dd className="mt-1 font-medium">{new Date(order.created_at).toLocaleString()}</dd>
            </div>
            <div>
              <dt className="text-neutral-500">Last Webhook</dt>
              <dd className="mt-1 font-medium">
                {order.last_webhook_at ? new Date(order.last_webhook_at).toLocaleString() : "—"}
              </dd>
            </div>
          </dl>
        </div>

        <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-5 space-y-4">
          <h2 className="font-semibold text-lg">Profit Breakdown</h2>
          {profit ? (
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-neutral-500">Revenue</dt>
                <dd className="mt-1 font-medium">{profit.sale_price}</dd>
              </div>
              <div>
                <dt className="text-neutral-500">Shipping Cost</dt>
                <dd className="mt-1 font-medium">{profit.shipping_cost ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-neutral-500">eBay Fee</dt>
                <dd className="mt-1 font-medium">{profit.ebay_fee ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-neutral-500">Purchase Cost</dt>
                <dd className="mt-1 font-medium">{profit.purchase_cost ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-neutral-500">Profit</dt>
                <dd className={`mt-1 font-medium ${profit.profit != null && Number(profit.profit) >= 0 ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>
                  {profit.profit ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-neutral-500">Margin %</dt>
                <dd className="mt-1 font-medium">{profit.margin_percent ? `${profit.margin_percent}%` : "—"}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-neutral-500 text-sm">No profit data available. Mark the order as purchased to calculate profit.</p>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-5 space-y-4">
        <h2 className="font-semibold text-lg">Purchase Automation</h2>

        {order.amazon_purchase_url ? (
          <div className="text-sm space-y-2">
            <p>
              <span className="text-neutral-500">Amazon Purchase URL:</span>{" "}
              <a
                href={order.amazon_purchase_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 dark:text-blue-400 hover:underline break-all"
              >
                {order.amazon_purchase_url}
              </a>
            </p>
            {order.amazon_order_id && (
              <p>
                <span className="text-neutral-500">Amazon Order ID:</span>{" "}
                <span className="font-mono text-xs">{order.amazon_order_id}</span>
              </p>
            )}
            {order.purchased_at && (
              <p>
                <span className="text-neutral-500">Purchased At:</span>{" "}
                {new Date(order.purchased_at).toLocaleString()}
              </p>
            )}
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
            <button
              onClick={handleGenerateLink}
              disabled={purchaseLoading}
              className="inline-flex items-center justify-center px-4 py-2 rounded-md bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 text-sm font-medium hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-50 transition-colors"
            >
              {purchaseLoading ? "Generating…" : "Generate Amazon Purchase Link"}
            </button>
            {purchaseUrl && (
              <a
                href={purchaseUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-blue-600 dark:text-blue-400 hover:underline break-all"
              >
                {purchaseUrl}
              </a>
            )}
          </div>
        )}

        {!order.purchase_cost && (
          <form onSubmit={handleMarkPurchased} className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
            <div>
              <label htmlFor="purchase-cost" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                Purchase Cost
              </label>
              <input
                id="purchase-cost"
                type="number"
                step="0.01"
                min="0"
                required
                value={purchaseCost}
                onChange={(e) => setPurchaseCost(e.target.value)}
                className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
              />
            </div>
            <div>
              <label htmlFor="amazon-order-id" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                Amazon Order ID
              </label>
              <input
                id="amazon-order-id"
                type="text"
                value={amazonOrderId}
                onChange={(e) => setAmazonOrderId(e.target.value)}
                className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
              />
            </div>
            <div>
              <label htmlFor="purchase-fulfillment" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                Fulfillment Status
              </label>
              <select
                id="purchase-fulfillment"
                value={purchaseFulfillment}
                onChange={(e) => setPurchaseFulfillment(e.target.value as FulfillmentStatus)}
                className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
              >
                {fulfillmentStatuses.map((s) => (
                  <option key={s} value={s}>
                    {s.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-3 flex items-center gap-3">
              <button
                type="submit"
                disabled={marking}
                className="inline-flex items-center justify-center px-4 py-2 rounded-md bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 text-sm font-medium hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-50 transition-colors"
              >
                {marking ? "Saving…" : "Mark as Purchased"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
