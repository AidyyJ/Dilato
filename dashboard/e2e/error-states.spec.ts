import { test, expect } from "@playwright/test";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function apiRoute(path: string) {
  return new RegExp(`^${API_BASE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}${path}$`);
}

async function mockApiDown(page: import("@playwright/test").Page) {
  const fulfill503 = async (route: import("@playwright/test").Route) =>
    route.fulfill({ status: 503, body: "Service Unavailable" });

  await page.route(apiRoute("/api/v1/products(?:\\?.*)?"), fulfill503);
  await page.route(apiRoute("/api/v1/products/\\d+"), fulfill503);
  await page.route(apiRoute("/api/v1/sourcing/search"), fulfill503);
  await page.route(apiRoute("/api/v1/listings(?:\\?.*)?"), fulfill503);
  await page.route(apiRoute("/api/v1/listings/\\d+"), fulfill503);
  await page.route(apiRoute("/api/v1/listings/\\d+/status"), fulfill503);
  await page.route(apiRoute("/api/v1/orders(?:\\?.*)?"), fulfill503);
  await page.route(apiRoute("/api/v1/orders/\\d+"), fulfill503);
  await page.route(apiRoute("/api/v1/orders/\\d+/profit"), fulfill503);
  await page.route(apiRoute("/api/v1/orders/\\d+/purchase-link"), fulfill503);
  await page.route(apiRoute("/api/v1/orders/\\d+/mark-purchased"), fulfill503);
  await page.route(apiRoute("/api/v1/orders/\\d+/status"), fulfill503);
  await page.route(apiRoute("/api/v1/orders/\\d+/fulfillment"), fulfill503);
  await page.route(apiRoute("/api/v1/orders/profit/summary(?:\\?.*)?"), fulfill503);
  await page.route(apiRoute("/api/v1/orders/profit/details(?:\\?.*)?"), fulfill503);
  await page.route(apiRoute("/api/v1/pricing/rules(?:\\?.*)?"), fulfill503);
  await page.route(apiRoute("/api/v1/pricing/rules/\\d+"), fulfill503);
  await page.route(apiRoute("/api/v1/pricing/calculate"), fulfill503);
}

async function mockAuthFailure(page: import("@playwright/test").Page) {
  const fulfill401 = async (route: import("@playwright/test").Route) =>
    route.fulfill({ status: 401, body: "Unauthorized" });

  await page.route(apiRoute("/api/v1/products(?:\\?.*)?"), fulfill401);
  await page.route(apiRoute("/api/v1/products/\\d+"), fulfill401);
  await page.route(apiRoute("/api/v1/sourcing/search"), fulfill401);
  await page.route(apiRoute("/api/v1/listings(?:\\?.*)?"), fulfill401);
  await page.route(apiRoute("/api/v1/listings/\\d+"), fulfill401);
  await page.route(apiRoute("/api/v1/listings/\\d+/status"), fulfill401);
  await page.route(apiRoute("/api/v1/orders(?:\\?.*)?"), fulfill401);
  await page.route(apiRoute("/api/v1/orders/\\d+"), fulfill401);
  await page.route(apiRoute("/api/v1/orders/\\d+/profit"), fulfill401);
  await page.route(apiRoute("/api/v1/orders/\\d+/purchase-link"), fulfill401);
  await page.route(apiRoute("/api/v1/orders/\\d+/mark-purchased"), fulfill401);
  await page.route(apiRoute("/api/v1/orders/\\d+/status"), fulfill401);
  await page.route(apiRoute("/api/v1/orders/\\d+/fulfillment"), fulfill401);
  await page.route(apiRoute("/api/v1/orders/profit/summary(?:\\?.*)?"), fulfill401);
  await page.route(apiRoute("/api/v1/orders/profit/details(?:\\?.*)?"), fulfill401);
  await page.route(apiRoute("/api/v1/pricing/rules(?:\\?.*)?"), fulfill401);
  await page.route(apiRoute("/api/v1/pricing/rules/\\d+"), fulfill401);
  await page.route(apiRoute("/api/v1/pricing/calculate"), fulfill401);
}

test.describe("Error States", () => {
  test.describe("API down / server errors", () => {
    test.beforeEach(async ({ page }) => {
      await mockApiDown(page);
    });

    test("dashboard shows error when APIs are down", async ({ page }) => {
      await page.goto("/");
      await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 15000 });
      await expect(errorBanner).toContainText(/API 503|Failed to load dashboard/);
    });

    test("products page shows error when API is down", async ({ page }) => {
      await page.goto("/products");
      await expect(page.getByRole("heading", { name: "Products" })).toBeVisible();
      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 15000 });
      await expect(errorBanner).toContainText(/API 503|Failed to load products/);
    });

    test("listings page shows error when API is down", async ({ page }) => {
      await page.goto("/listings");
      await expect(page.getByRole("heading", { name: "Listings" })).toBeVisible();
      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 15000 });
      await expect(errorBanner).toContainText(/API 503|Failed to load listings/);
    });

    test("orders page shows error when API is down", async ({ page }) => {
      await page.goto("/orders");
      await expect(page.getByRole("heading", { name: "Orders" })).toBeVisible();
      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 15000 });
      await expect(errorBanner).toContainText(/API 503|Failed to load orders/);
    });

    test("pricing rules page shows error when API is down", async ({ page }) => {
      await page.goto("/pricing");
      await expect(page.getByRole("heading", { name: "Pricing Rules" })).toBeVisible();
      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 15000 });
      await expect(errorBanner).toContainText(/API 503|Failed to load rules/);
    });

    test("profits page shows error when API is down", async ({ page }) => {
      await page.goto("/profits");
      await expect(page.getByRole("heading", { name: "Profit Views" })).toBeVisible();
      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 15000 });
      await expect(errorBanner).toContainText(/API 503|Failed to load profit data/);
    });

    test("order detail shows error when API is down", async ({ page }) => {
      await page.goto("/orders/1");
      await expect(page.getByRole("heading", { name: "Order Detail" })).toBeVisible();
      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 15000 });
      await expect(errorBanner).toContainText(/API 503|Failed to load order/);
    });

    test("sourcing fails gracefully when API is down", async ({ page }) => {
      await page.goto("/products");
      await expect(page.getByRole("button", { name: "Source Products" })).toBeVisible();
      await page.getByRole("button", { name: "Source Products" }).click();
      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 15000 });
      await expect(errorBanner).toContainText(/API 503|Sourcing failed/);
    });
  });

  test.describe("Auth failures", () => {
    test.beforeEach(async ({ page }) => {
      await mockAuthFailure(page);
    });

    test("dashboard shows auth error", async ({ page }) => {
      await page.goto("/");
      await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 15000 });
      await expect(errorBanner).toContainText(/API 401|Unauthorized/);
    });

    test("products page shows auth error", async ({ page }) => {
      await page.goto("/products");
      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 15000 });
      await expect(errorBanner).toContainText(/API 401|Unauthorized/);
    });

    test("order detail shows auth error", async ({ page }) => {
      await page.goto("/orders/1");
      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 15000 });
      await expect(errorBanner).toContainText(/API 401|Unauthorized/);
    });
  });

  test.describe("Invalid inputs", () => {
    test("order detail with invalid ID shows error", async ({ page }) => {
      await page.goto("/orders/invalid-id");
      await expect(page.getByRole("heading", { name: "Order Detail" })).toBeVisible();
      await expect(page.getByText("Invalid order ID")).toBeVisible();
    });

    test("pricing rule form blocks empty required fields", async ({ page }) => {
      await page.goto("/pricing");
      await expect(page.getByRole("heading", { name: "Pricing Rules" })).toBeVisible();
      await page.getByRole("button", { name: "Add Rule" }).click();

      const nameInput = page.locator("#rule-name");
      const valueInput = page.locator("#rule-value");
      const priorityInput = page.locator("#rule-priority");

      // HTML5 required validation should prevent submission
      await expect(nameInput).toHaveAttribute("required", "");
      await expect(valueInput).toHaveAttribute("required", "");
      await expect(priorityInput).toHaveAttribute("required", "");

      // Clear fields and attempt submit
      await nameInput.fill("");
      await valueInput.fill("");
      await priorityInput.fill("");

      await page.getByRole("button", { name: "Create Rule" }).click();

      // Form should not submit because of HTML5 validation; still on pricing page with form visible
      await expect(page).toHaveURL("/pricing");
      await expect(page.locator("#rule-name")).toBeVisible();
    });

    test("create listing form blocks missing product selection", async ({ page }) => {
      // Mock products list so the form renders with an empty select
      await page.route(apiRoute("/api/v1/products(?:\\?.*)?"), async (route) => {
        return route.fulfill({ status: 200, body: JSON.stringify([]) });
      });

      await page.goto("/listings/new");
      await expect(page.getByRole("heading", { name: /Create Listing/i })).toBeVisible();

      const productSelect = page.locator("#product");
      await expect(productSelect).toHaveAttribute("required", "");

      // Title and price are also required
      await expect(page.locator("#title")).toHaveAttribute("required", "");
      await expect(page.locator("#price")).toHaveAttribute("required", "");
      await expect(page.locator("#quantity")).toHaveAttribute("required", "");

      // Submit button is disabled when no product is selected
      const submitBtn = page.getByRole("button", { name: "Create Draft Listing" });
      await expect(submitBtn).toBeDisabled();

      // Should still be on the create listing page
      await expect(page).toHaveURL(/\/listings\/new/);
      await expect(page.locator("#product")).toBeVisible();
    });

    test("pricing calculate returns error for invalid product", async ({ page }) => {
      await page.route(apiRoute("/api/v1/products(?:\\?.*)?"), async (route) => {
        return route.fulfill({ status: 200, body: JSON.stringify([]) });
      });

      await page.route(apiRoute("/api/v1/pricing/calculate"), async (route) => {
        return route.fulfill({
          status: 422,
          body: JSON.stringify({ detail: "Invalid product_id" }),
        });
      });

      await page.goto("/listings/new?productId=99999");
      await expect(page.getByRole("heading", { name: /Create Listing/i })).toBeVisible();

      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 15000 });
      await expect(errorBanner).toContainText(/API 422|Invalid product_id|Pricing preview failed/);
    });

    test("mark purchased shows error on server validation failure", async ({ page }) => {
      await page.route(apiRoute("/api/v1/orders/1"), async (route) => {
        return route.fulfill({
          status: 200,
          body: JSON.stringify({
            id: 1,
            listing_id: 2,
            ebay_order_id: "12-12345-12345",
            buyer_username: "buyer1",
            sale_price: "59.99",
            quantity: 1,
            shipping_cost: "5.00",
            ebay_fee: "6.00",
            status: "pending",
            shipped_at: null,
            delivered_at: null,
            shipping_address: "123 Main St",
            payment_status: "paid",
            tracking_number: null,
            carrier: null,
            last_webhook_at: null,
            amazon_purchase_url: null,
            purchase_cost: null,
            profit: null,
            margin_percent: null,
            amazon_order_id: null,
            purchased_at: null,
            fulfillment_status: "not_started",
            created_at: "2024-01-12T00:00:00Z",
            updated_at: "2024-01-12T00:00:00Z",
          }),
        });
      });

      await page.route(apiRoute("/api/v1/orders/1/profit"), async (route) => {
        return route.fulfill({ status: 200, body: "null" });
      });

      await page.route(apiRoute("/api/v1/orders/1/mark-purchased"), async (route) => {
        return route.fulfill({
          status: 400,
          body: JSON.stringify({ detail: "purchase_cost must be a positive number" }),
        });
      });

      await page.goto("/orders/1");
      await expect(page.getByRole("heading", { name: "Order #1" })).toBeVisible();

      // Use 0 as purchase cost (passes HTML5 min="0", fails server-side)
      await page.locator("#purchase-cost").fill("0");
      await page.getByRole("button", { name: "Mark as Purchased" }).click();

      const errorBanner = page.locator("div.bg-red-50, div.dark\\:bg-red-900\\/20").first();
      await expect(errorBanner).toBeVisible({ timeout: 10000 });
      await expect(errorBanner).toContainText(/API 400|purchase_cost|Failed to mark purchased/);
    });
  });
});
