const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const DEFAULT_RETRIES = 3;
export const DEFAULT_RETRY_DELAY_MS = 300;

function isRetryableError(error: unknown): boolean {
  return (
    error instanceof TypeError ||
    (error instanceof Error && error.message.includes("fetch"))
  );
}

function isRetryableStatus(status: number): boolean {
  return status >= 500 || status === 429;
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(resolve, ms);
    if (signal) {
      const onAbort = () => {
        clearTimeout(timeout);
        reject(new DOMException("Aborted", "AbortError"));
      };
      if (signal.aborted) {
        onAbort();
        return;
      }
      signal.addEventListener("abort", onAbort, { once: true });
    }
  });
}

export async function fetchApi<T>(
  path: string,
  options?: RequestInit,
  __retryDelayMs?: number
): Promise<T> {
  const retryDelayMs = __retryDelayMs ?? DEFAULT_RETRY_DELAY_MS;
  const signal = options?.signal ?? undefined;
  let lastError: unknown;

  // Attach auth token from localStorage
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  const authHeaders: Record<string, string> = {};
  if (token) {
    authHeaders['Authorization'] = `Bearer ${token}`;
  }

  for (let attempt = 0; attempt <= DEFAULT_RETRIES; attempt++) {
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
          ...options?.headers,
        },
        ...options,
        signal,
      });

      if (!res.ok) {
        // Handle 401 - clear token and redirect
        if (res.status === 401) {
          if (typeof window !== 'undefined') {
            localStorage.removeItem('auth_token');
            window.location.href = '/login';
          }
          throw new Error('Not authenticated');
        }

        let text: string;
        try {
          text = await res.text();
        } catch {
          throw new Error(`API ${res.status}: Unknown error`);
        }
        if (isRetryableStatus(res.status) && attempt < DEFAULT_RETRIES) {
          lastError = new Error(`API ${res.status}: ${text}`);
          const delay = retryDelayMs * Math.pow(2, attempt);
          await sleep(delay, signal);
          continue;
        }
        throw new Error(`API ${res.status}: ${text}`);
      }

      return res.json() as Promise<T>;
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        throw err;
      }

      if (err instanceof Error && err.message.startsWith("API ")) {
        throw err;
      }

      if (isRetryableError(err) && attempt < DEFAULT_RETRIES) {
        lastError = err;
        const delay = retryDelayMs * Math.pow(2, attempt);
        await sleep(delay, signal);
        continue;
      }

      throw err;
    }
  }

  throw lastError ?? new Error("Request failed after retries");
}

export interface ApiOptions {
  signal?: AbortSignal;
}

export type ProductSource = "amazon";

export interface Product {
  id: number;
  asin: string;
  title: string;
  brand?: string;
  category?: string;
  image_url?: string;
  detail_page_url?: string;
  amazon_price?: string;
  current_price?: string;
  source: ProductSource;
  is_active: boolean;
  last_synced_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ProductCreate {
  asin: string;
  title: string;
  brand?: string;
  category?: string;
  image_url?: string;
  detail_page_url?: string;
  amazon_price?: string;
  current_price?: string;
}

export type ListingStatus = "draft" | "active" | "ended" | "sold";

export interface Listing {
  id: number;
  product_id: number;
  title: string;
  listing_price: string;
  quantity: number;
  ebay_category_id?: string;
  listing_duration: string;
  ebay_item_id?: string;
  ebay_sku?: string;
  quantity_sold: number;
  status: ListingStatus;
  ebay_fee_estimate?: string;
  started_at?: string;
  ended_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ListingCreate {
  product_id: number;
  title: string;
  listing_price: string;
  quantity?: number;
  ebay_category_id?: string;
  listing_duration?: string;
}

export type RuleType = "fixed_markup" | "percentage" | "fixed_price";

export interface PricingRule {
  id: number;
  name: string;
  rule_type: RuleType;
  value: string;
  min_price?: string;
  max_price?: string;
  min_margin_percent?: string;
  priority: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PricingRuleCreate {
  name: string;
  rule_type: RuleType;
  value: string;
  min_price?: string;
  max_price?: string;
  min_margin_percent?: string;
  priority?: number;
  is_active?: boolean;
}

export interface PricingRuleUpdate {
  name?: string;
  rule_type?: RuleType;
  value?: string;
  min_price?: string;
  max_price?: string;
  min_margin_percent?: string;
  priority?: number;
  is_active?: boolean;
}

export interface PricingCalculateRequest {
  product_id: number;
}

export interface PricingCalculateResponse {
  product_id: number;
  amazon_price?: string;
  listing_price?: string;
  rule_applied?: PricingRule;
}

export interface SourcingRequest {
  keywords?: string[];
  category?: string;
  min_price?: string;
  max_price?: string;
  min_margin?: number;
  max_results?: number;
}

export interface SourcingResult {
  asin: string;
  title: string;
  amazon_price: string;
  estimated_ebay_price?: string;
  estimated_margin?: number;
  category?: string;
  image_url?: string;
}

export type OrderStatus = "pending" | "shipped" | "delivered" | "cancelled" | "returned";

export type FulfillmentStatus = "not_started" | "in_progress" | "delivered";

export interface Order {
  id: number;
  listing_id?: number;
  ebay_order_id?: string;
  buyer_username?: string;
  sale_price: string;
  quantity: number;
  shipping_cost?: string;
  ebay_fee?: string;
  status: OrderStatus;
  shipped_at?: string;
  delivered_at?: string;
  shipping_address?: string;
  payment_status?: string;
  tracking_number?: string;
  carrier?: string;
  last_webhook_at?: string;
  amazon_purchase_url?: string;
  purchase_cost?: string;
  profit?: string;
  margin_percent?: string;
  amazon_order_id?: string;
  purchased_at?: string;
  fulfillment_status?: FulfillmentStatus;
  created_at: string;
  updated_at: string;
}

export interface OrderProfitDetailOut {
  order_id: number;
  ebay_order_id?: string;
  sale_price: string;
  shipping_cost?: string;
  ebay_fee?: string;
  purchase_cost?: string;
  profit?: string;
  margin_percent?: string;
  created_at?: string;
}

export interface ProfitSummaryOut {
  total_orders: number;
  total_revenue: string;
  total_purchase_cost?: string;
  total_shipping_cost?: string;
  total_ebay_fees?: string;
  total_profit?: string;
  average_margin_percent?: string;
}

export interface PurchaseLinkOut {
  order_id: number;
  purchase_url?: string;
}

export interface MarkPurchasedRequest {
  purchase_cost: string;
  amazon_order_id?: string;
  amazon_purchase_url?: string;
  fulfillment_status?: FulfillmentStatus;
}

export interface PaginatedParams {
  skip?: number;
  limit?: number;
}

export const api = {
  products: {
    list: (params?: PaginatedParams & { category?: string; is_active?: boolean }, options?: ApiOptions) =>
      fetchApi<Product[]>(`/api/v1/products?${toQuery(params)}`, { signal: options?.signal }),
    get: (id: number, options?: ApiOptions) => fetchApi<Product>(`/api/v1/products/${id}`, { signal: options?.signal }),
    getByAsin: (asin: string, options?: ApiOptions) => fetchApi<Product>(`/api/v1/products/asin/${asin}`, { signal: options?.signal }),
    create: (data: ProductCreate, options?: ApiOptions) =>
      fetchApi<Product>("/api/v1/products", { method: "POST", body: JSON.stringify(data), signal: options?.signal }),
  },
  listings: {
    list: (params?: PaginatedParams & { status?: ListingStatus }, options?: ApiOptions) =>
      fetchApi<Listing[]>(`/api/v1/listings?${toQuery(params)}`, { signal: options?.signal }),
    get: (id: number, options?: ApiOptions) => fetchApi<Listing>(`/api/v1/listings/${id}`, { signal: options?.signal }),
    create: (data: ListingCreate, options?: ApiOptions) =>
      fetchApi<Listing>("/api/v1/listings", { method: "POST", body: JSON.stringify(data), signal: options?.signal }),
    updateStatus: (id: number, status: ListingStatus, ebay_item_id?: string, options?: ApiOptions) =>
      fetchApi<Listing>(`/api/v1/listings/${id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status, ebay_item_id }),
        signal: options?.signal,
      }),
  },
  pricing: {
    listRules: (options?: ApiOptions) => fetchApi<PricingRule[]>("/api/v1/pricing/rules", { signal: options?.signal }),
    createRule: (data: PricingRuleCreate, options?: ApiOptions) =>
      fetchApi<PricingRule>("/api/v1/pricing/rules", { method: "POST", body: JSON.stringify(data), signal: options?.signal }),
    updateRule: (id: number, data: PricingRuleUpdate, options?: ApiOptions) =>
      fetchApi<PricingRule>(`/api/v1/pricing/rules/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
        signal: options?.signal,
      }),
    deleteRule: (id: number, options?: ApiOptions) =>
      fetchApi<PricingRule>(`/api/v1/pricing/rules/${id}`, { method: "DELETE", signal: options?.signal }),
    calculate: (data: PricingCalculateRequest, options?: ApiOptions) =>
      fetchApi<PricingCalculateResponse>("/api/v1/pricing/calculate", {
        method: "POST",
        body: JSON.stringify(data),
        signal: options?.signal,
      }),
  },
  sourcing: {
    search: (data: SourcingRequest, options?: ApiOptions) =>
      fetchApi<SourcingResult[]>("/api/v1/sourcing/search", {
        method: "POST",
        body: JSON.stringify(data),
        signal: options?.signal,
      }),
  },
  orders: {
    list: (params?: PaginatedParams & { status?: OrderStatus }, options?: ApiOptions) =>
      fetchApi<Order[]>(`/api/v1/orders?${toQuery(params)}`, { signal: options?.signal }),
    get: (id: number, options?: ApiOptions) => fetchApi<Order>(`/api/v1/orders/${id}`, { signal: options?.signal }),
    updateStatus: (id: number, status: OrderStatus, options?: ApiOptions) =>
      fetchApi<Order>(`/api/v1/orders/${id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
        signal: options?.signal,
      }),
    updateFulfillment: (id: number, status: FulfillmentStatus, options?: ApiOptions) =>
      fetchApi<Order>(`/api/v1/orders/${id}/fulfillment`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
        signal: options?.signal,
      }),
    getProfit: (id: number, options?: ApiOptions) =>
      fetchApi<OrderProfitDetailOut>(`/api/v1/orders/${id}/profit`, { signal: options?.signal }),
    generatePurchaseLink: (id: number, options?: ApiOptions) =>
      fetchApi<PurchaseLinkOut>(`/api/v1/orders/${id}/purchase-link`, { method: "POST", signal: options?.signal }),
    markPurchased: (id: number, data: MarkPurchasedRequest, options?: ApiOptions) =>
      fetchApi<Order>(`/api/v1/orders/${id}/mark-purchased`, {
        method: "POST",
        body: JSON.stringify(data),
        signal: options?.signal,
      }),
  },
  profit: {
    summary: (params?: { status?: OrderStatus; date_from?: string; date_to?: string }, options?: ApiOptions) =>
      fetchApi<ProfitSummaryOut>(`/api/v1/orders/profit/summary?${toQuery(params)}`, { signal: options?.signal }),
    details: (params?: PaginatedParams & { status?: OrderStatus; date_from?: string; date_to?: string }, options?: ApiOptions) =>
      fetchApi<OrderProfitDetailOut[]>(`/api/v1/orders/profit/details?${toQuery(params)}`, { signal: options?.signal }),
  },
};

function toQuery(params?: Record<string, unknown> | object): string {
  if (!params) return "";
  const q = new URLSearchParams();
  Object.entries(params as Record<string, unknown>).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      q.set(key, String(value));
    }
  });
  return q.toString();
}
