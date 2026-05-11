import { api, fetchApi } from "@/lib/api";

describe("lib/api", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockReset();
  });

  describe("api.products", () => {
    it("calls list endpoint with query params", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [{ id: 1, asin: "B123", title: "Test" }],
      });

      await api.products.list({ skip: 0, limit: 10, category: "Electronics" });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/products?skip=0&limit=10&category=Electronics"),
        expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) })
      );
    });

    it("calls get endpoint", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 1, asin: "B123" }),
      });

      await api.products.get(1);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/products/1"),
        expect.any(Object)
      );
    });

    it("calls create endpoint with POST", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 2, asin: "B456" }),
      });

      await api.products.create({ asin: "B456", title: "New Product" });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/products"),
        expect.objectContaining({ method: "POST", body: JSON.stringify({ asin: "B456", title: "New Product" }) })
      );
    });
  });

  describe("api.listings", () => {
    it("calls list endpoint with status filter", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

      await api.listings.list({ status: "draft" });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/listings?status=draft"),
        expect.any(Object)
      );
    });

    it("calls updateStatus with PATCH", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 1, status: "active" }),
      });

      await api.listings.updateStatus(1, "active", "ebay-123");

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/listings/1/status"),
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ status: "active", ebay_item_id: "ebay-123" }),
        })
      );
    });
  });

  describe("api.pricing", () => {
    it("calls listRules endpoint", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

      await api.pricing.listRules();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/pricing/rules"),
        expect.any(Object)
      );
    });

    it("calls calculate endpoint with POST", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ product_id: 1, listing_price: "12.99" }),
      });

      await api.pricing.calculate({ product_id: 1 });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/pricing/calculate"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ product_id: 1 }),
        })
      );
    });
  });

  describe("api.sourcing", () => {
    it("calls search endpoint with POST", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [{ asin: "B123", title: "Test" }],
      });

      await api.sourcing.search({ keywords: ["test"], max_results: 10 });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/sourcing/search"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ keywords: ["test"], max_results: 10 }),
        })
      );
    });
  });

  describe("error handling", () => {
    it("throws on non-ok response", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        text: async () => "Not found",
      });

      await expect(api.products.get(999)).rejects.toThrow("API 404: Not found");
    });

    it("throws with unknown error when text fails", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        text: async () => { throw new Error("fail"); },
      });

      await expect(api.products.get(1)).rejects.toThrow("API 500: Unknown error");
    });
  });

  describe("retry logic", () => {
    it("retries on 500 errors up to 3 times then throws", async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: false, status: 500, text: async () => "Server Error" })
        .mockResolvedValueOnce({ ok: false, status: 500, text: async () => "Server Error" })
        .mockResolvedValueOnce({ ok: false, status: 500, text: async () => "Server Error" })
        .mockResolvedValueOnce({ ok: false, status: 500, text: async () => "Server Error" });

      await expect(fetchApi("/test", {}, 0)).rejects.toThrow("API 500: Server Error");
      expect(global.fetch).toHaveBeenCalledTimes(4);
    });

    it("retries on network errors up to 3 times then throws", async () => {
      (global.fetch as jest.Mock)
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockRejectedValueOnce(new TypeError("Failed to fetch"));

      await expect(fetchApi("/test", {}, 0)).rejects.toThrow("Failed to fetch");
      expect(global.fetch).toHaveBeenCalledTimes(4);
    });

    it("recovers after a single 500 and returns data", async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: false, status: 503, text: async () => "Unavailable" })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 1, asin: "B123" }) });

      const result = await fetchApi("/test", {}, 0);
      expect(result).toEqual({ id: 1, asin: "B123" });
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });

    it("does not retry on 4xx errors", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        text: async () => "Bad Request",
      });

      await expect(fetchApi("/test", {}, 0)).rejects.toThrow("API 400: Bad Request");
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    it("retries on 429 then recovers", async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: false, status: 429, text: async () => "Too Many Requests" })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 1 }) });

      const result = await fetchApi("/test", {}, 0);
      expect(result).toEqual({ id: 1 });
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });
  });

  describe("AbortController support", () => {
    it("passes signal to fetch", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [{ id: 1 }],
      });

      const controller = new AbortController();
      await api.products.list(undefined, { signal: controller.signal });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ signal: controller.signal })
      );
    });

    it("aborts retry delay when signal is aborted", async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: false, status: 503, text: async () => "Unavailable" });

      const controller = new AbortController();
      const promise = fetchApi("/test", { signal: controller.signal }, 10);
      controller.abort();

      await expect(promise).rejects.toThrow("Aborted");
    });
  });
});
