"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, Product, PricingCalculateResponse } from "@/lib/api";

export default function NewListingForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselectedProductId = searchParams.get("productId");

  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string>(preselectedProductId ?? "");
  const [title, setTitle] = useState("");
  const [listingPrice, setListingPrice] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [ebayCategoryId, setEbayCategoryId] = useState("");
  const [listingDuration, setListingDuration] = useState("GTC");
  const [preview, setPreview] = useState<PricingCalculateResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPreviewForProduct = useCallback(async (productId: string) => {
    if (!productId) return;
    setError(null);
    setPreviewLoading(true);
    try {
      const data = await api.pricing.calculate({ product_id: Number(productId) });
      setPreview(data);
      if (data.listing_price) {
        setListingPrice(String(data.listing_price));
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Pricing preview failed");
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  useEffect(() => {
    api.products.list({ limit: 500 }).then((data) => {
      setProducts(data);
      if (preselectedProductId) {
        const p = data.find((x) => String(x.id) === preselectedProductId);
        if (p) setTitle(p.title);
        fetchPreviewForProduct(preselectedProductId);
      }
    });
  }, [preselectedProductId, fetchPreviewForProduct]);

  const selectedProduct = products.find((p) => String(p.id) === selectedProductId);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.listings.create({
        product_id: Number(selectedProductId),
        title,
        listing_price: listingPrice,
        quantity: Number(quantity) || 1,
        ebay_category_id: ebayCategoryId || undefined,
        listing_duration: listingDuration || undefined,
      });
      router.push("/listings");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create listing");
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Create Listing</h1>
        <p className="text-neutral-600 dark:text-neutral-400 mt-1">
          Create a new eBay listing from an existing product.
        </p>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        <div>
          <label htmlFor="product" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            Product
          </label>
          <select
            id="product"
            value={selectedProductId}
            onChange={(e) => {
              const val = e.target.value;
              setSelectedProductId(val);
              if (val) {
                const p = products.find((x) => String(x.id) === val);
                if (p) setTitle(p.title);
                fetchPreviewForProduct(val);
              }
            }}
            required
            className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
          >
            <option value="">Select a product…</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.asin} — {p.title}
              </option>
            ))}
          </select>
        </div>

        {selectedProduct && (
          <div className="rounded-md border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-4 text-sm space-y-1">
            <p>
              <span className="font-medium">Amazon Price:</span> {selectedProduct.amazon_price ?? "—"}
            </p>
            <p>
              <span className="font-medium">Category:</span> {selectedProduct.category ?? "—"}
            </p>
            {previewLoading ? (
              <p className="text-neutral-500">Calculating price…</p>
            ) : preview ? (
              <>
                <p>
                  <span className="font-medium">Suggested Price:</span>{" "}
                  {preview.listing_price ?? "—"}
                </p>
                <p>
                  <span className="font-medium">Rule Applied:</span>{" "}
                  {preview.rule_applied?.name ?? "None"}
                </p>
              </>
            ) : null}
          </div>
        )}

        <div>
          <label htmlFor="title" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            Listing Title
          </label>
          <input
            id="title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            maxLength={500}
            className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="price" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
              Listing Price
            </label>
            <input
              id="price"
              type="number"
              step="0.01"
              min="0"
              value={listingPrice}
              onChange={(e) => setListingPrice(e.target.value)}
              required
              className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
            />
          </div>
          <div>
            <label htmlFor="quantity" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
              Quantity
            </label>
            <input
              id="quantity"
              type="number"
              min="1"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
              className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="category" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
              eBay Category ID
            </label>
            <input
              id="category"
              type="text"
              value={ebayCategoryId}
              onChange={(e) => setEbayCategoryId(e.target.value)}
              className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
            />
          </div>
          <div>
            <label htmlFor="duration" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
              Duration
            </label>
            <select
              id="duration"
              value={listingDuration}
              onChange={(e) => setListingDuration(e.target.value)}
              className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
            >
              <option value="GTC">GTC</option>
              <option value="Days_1">1 Day</option>
              <option value="Days_3">3 Days</option>
              <option value="Days_5">5 Days</option>
              <option value="Days_7">7 Days</option>
              <option value="Days_10">10 Days</option>
              <option value="Days_30">30 Days</option>
            </select>
          </div>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <button
            type="submit"
            disabled={submitting || !selectedProductId}
            className="inline-flex items-center justify-center px-4 py-2 rounded-md bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 text-sm font-medium hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-50 transition-colors"
          >
            {submitting ? "Creating…" : "Create Draft Listing"}
          </button>
          <button
            type="button"
            onClick={() => router.push("/listings")}
            className="inline-flex items-center justify-center px-4 py-2 rounded-md border border-neutral-300 dark:border-neutral-700 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-900 transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
