import { test, expect } from "@playwright/test";
import {
  mockProducts,
  mockSourcingResults,
  mockListings,
  mockOrders,
  mockPricingRules,
  mockProfitSummary,
  mockProfitDetails,
  mockOrderDetail,
} from "./fixtures/mocks";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function apiRoute(path: string) {
  return new RegExp(`^${API_BASE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}${path}$`);
}

async function mockApiRoutes(page: import("@playwright/test").Page) {
  await page.route(apiRoute("/api/v1/products(?:\\?.*)?"), async (route) => {
    return route.fulfill({ status: 200, body: JSON.stringify(mockProducts) });
  });

  await page.route(apiRoute("/api/v1/products/\\d+"), async (route) => {
    return route.fulfill({ status: 200, body: JSON.stringify(mockProducts[0]) });
  });

  await page.route(apiRoute("/api/v1/sourcing/search"), async (route) => {
    return route.fulfill({ status: 200, body: JSON.stringify(mockSourcingResults) });
  });

  await page.route(apiRoute("/api/v1/listings(?:\\?.*)?"), async (route) => {
    return route.fulfill({ status: 200, body: JSON.stringify(mockListings) });
  });

  await page.route(apiRoute("/api/v1/listings/\\d+/status"), async (route) => {
    const url = route.request().url();
    const id = Number(url.match(/listings\/(\d+)\/status/)?.[1]);
    const listing = mockListings.find((l) => l.id === id);
    if (listing) {
      return route.fulfill({
        status: 200,
        body: JSON.stringify({ ...listing, status: "active" }),
      });
    }
    route.continue();
  });

  await page.route(apiRoute("/api/v1/listings"), async (route) => {
    if (route.request().method() !== "POST") {
      return route.continue();
    }
    const body = await route.request().postDataJSON();
    return route.fulfill({
      status: 201,
      body: JSON.stringify({
        id: 99,
        product_id: body?.product_id ?? 1,
        title: body?.title ?? "New Listing",
        listing_price: body?.listing_price ?? "29.99",
        quantity: body?.quantity ?? 1,
        ebay_category_id: body?.ebay_category_id ?? null,
        listing_duration: body?.listing_duration ?? "GTC",
        status: "draft",
        quantity_sold: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }),
    });
  });

  await page.route(apiRoute("/api/v1/orders(?:\\?.*)?"), async (route) => {
    return route.fulfill({ status: 200, body: JSON.stringify(mockOrders) });
  });

  await page.route(apiRoute("/api/v1/orders/\\d+"), async (route) => {
    return route.fulfill({ status: 200, body: JSON.stringify(mockOrderDetail) });
  });

  await page.route(apiRoute("/api/v1/orders/\\d+/profit"), async (route) => {
    return route.fulfill({ status: 200, body: JSON.stringify(mockProfitDetails[0]) });
  });

  await page.route(apiRoute("/api/v1/orders/profit/summary(?:\\?.*)?"), async (route) => {
    return route.fulfill({ status: 200, body: JSON.stringify(mockProfitSummary) });
  });

  await page.route(apiRoute("/api/v1/orders/profit/details(?:\\?.*)?"), async (route) => {
    return route.fulfill({ status: 200, body: JSON.stringify(mockProfitDetails) });
  });

  await page.route(apiRoute("/api/v1/pricing/rules(?:\\?.*)?"), async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      return route.fulfill({ status: 200, body: JSON.stringify(mockPricingRules) });
    }
    if (method === "POST") {
      const body = await route.request().postDataJSON();
      return route.fulfill({
        status: 201,
        body: JSON.stringify({
          id: 99,
          ...body,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
    }
    route.continue();
  });

  await page.route(apiRoute("/api/v1/pricing/rules/\\d+"), async (route) => {
    const method = route.request().method();
    const url = route.request().url();
    if (method === "PATCH") {
      const id = Number(url.match(/rules\/(\d+)$/)?.[1]);
      const body = await route.request().postDataJSON();
      const rule = mockPricingRules.find((r) => r.id === id) ?? mockPricingRules[0];
      return route.fulfill({
        status: 200,
        body: JSON.stringify({ ...rule, ...body }),
      });
    }
    if (method === "DELETE") {
      return route.fulfill({ status: 204, body: "" });
    }
    route.continue();
  });

  await page.route(apiRoute("/api/v1/pricing/calculate"), async (route) => {
    return route.fulfill({
      status: 200,
      body: JSON.stringify({
        product_id: 1,
        amazon_price: "29.99",
        listing_price: "39.99",
        rule_applied: mockPricingRules[0],
      }),
    });
  });
}

test.describe("Critical Flows", () => {
  test.beforeEach(async ({ page }) => {
    await mockApiRoutes(page);
  });

  test("dashboard loads with KPIs, charts, and recent orders", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByText("Overview of your Amazon-to-eBay reselling pipeline.")).toBeVisible();

    // KPI cards
    await expect(page.getByText("Total Orders")).toBeVisible();
    await expect(page.getByText("Total Revenue")).toBeVisible();
    await expect(page.getByText("Total Profit")).toBeVisible();
    await expect(page.getByText("Avg Margin %")).toBeVisible();

    // Charts
    await expect(page.getByText("Profit Trend (Last 30 Days)")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Margin Distribution" })).toBeVisible();

    // Tables
    await expect(page.getByText("Top Orders by Margin")).toBeVisible();
    await expect(page.getByText("Recent Orders")).toBeVisible();

    // Quick links (sidebar)
    await expect(page.getByRole("link", { name: "Products", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Listings", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Orders", exact: true })).toBeVisible();
  });

  test("sidebar navigation visits all pages", async ({ page }) => {
    await page.goto("/");

    const navItems = [
      { label: "Products", path: "/products" },
      { label: "Listings", path: "/listings" },
      { label: "Orders", path: "/orders" },
      { label: "Profits", path: "/profits" },
      { label: "Pricing Rules", path: "/pricing" },
    ];

    for (const item of navItems) {
      await page.getByRole("link", { name: item.label, exact: true }).click();
      await expect(page).toHaveURL(item.path);
      await expect(page.locator("main h1")).toBeVisible();
    }
  });

  test("products page lists products and supports sourcing", async ({ page }) => {
    await page.goto("/products");

    await expect(page.getByRole("heading", { name: "Products" })).toBeVisible();
    await expect(page.getByText("B08N5WRWNW")).toBeVisible();
    await expect(page.getByText("Test Product A")).toBeVisible();
    await expect(page.getByText("Test Product B")).toBeVisible();

    // Pagination
    await expect(page.locator("button", { hasText: "Previous" })).toBeVisible();
    await expect(page.locator("button", { hasText: "Next" }).first()).toBeVisible();

    // Source products
    await page.getByRole("button", { name: "Source Products" }).click();
    await expect(page.getByText("Sourcing Results")).toBeVisible();
    await expect(page.getByText("Sourced Product 1")).toBeVisible();
    await expect(page.getByText("Sourced Product 2")).toBeVisible();
  });

  test("listings page filters and publishes a draft", async ({ page }) => {
    await page.goto("/listings");

    await expect(page.getByRole("heading", { name: "Listings" })).toBeVisible();
    await expect(page.getByText("Listing One")).toBeVisible();
    await expect(page.getByText("Listing Two")).toBeVisible();

    // Filter by status
    await page.locator("#status-filter").selectOption("draft");
    await expect(page.getByText("Listing One")).toBeVisible();

    // Publish draft
    const publishBtn = page.getByRole("button", { name: "Publish" });
    await expect(publishBtn).toBeVisible();
    await publishBtn.click();
    await expect(page.getByText("Listing One")).toBeVisible();
  });

  test("orders page filters and navigates to detail", async ({ page }) => {
    await page.goto("/orders");

    await expect(page.getByRole("heading", { name: "Orders" })).toBeVisible();
    await expect(page.getByText("12-12345-12345")).toBeVisible();
    await expect(page.getByText("12-12345-12346")).toBeVisible();

    // Filter by status
    await page.locator("#status-filter").selectOption("shipped");
    await expect(page.getByText("12-12345-12346")).toBeVisible();

    // Clear filter and click row
    await page.locator("#status-filter").selectOption("");
    await page.getByText("12-12345-12345").click();
    await expect(page).toHaveURL(/\/orders\/1$/);
    await expect(page.getByRole("heading", { name: "Order #1" })).toBeVisible();
  });

  test("pricing rules CRUD", async ({ page }) => {
    await page.goto("/pricing");

    await expect(page.getByRole("heading", { name: "Pricing Rules" })).toBeVisible();
    await expect(page.getByText("Default Markup")).toBeVisible();
    await expect(page.getByText("Percentage Rule")).toBeVisible();

    // Toggle active
    await page.getByRole("button", { name: "Yes" }).first().click();
    await expect(page.getByText("Default Markup")).toBeVisible();

    // Add rule
    await page.getByRole("button", { name: "Add Rule" }).click();
    await page.locator("#rule-name").fill("New Test Rule");
    await page.locator("#rule-value").fill("15");
    await page.locator("#rule-priority").fill("3");
    await page.getByRole("button", { name: "Create Rule" }).click();

    await expect(page.getByText("New Test Rule")).toBeVisible();

    // Edit rule
    await page.getByRole("button", { name: "Edit" }).first().click();
    await page.locator("#rule-name").fill("Updated Rule");
    await page.getByRole("button", { name: "Update Rule" }).click();
    await expect(page.getByText("Updated Rule")).toBeVisible();

    // Delete rule
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Delete" }).first().click();
    await expect(page.getByText("Default Markup")).not.toBeVisible();
  });

  test("profits page shows summary and details", async ({ page }) => {
    await page.goto("/profits");

    await expect(page.getByRole("heading", { name: "Profit Views" })).toBeVisible();
    await expect(page.getByText("Total Orders")).toBeVisible();
    await expect(page.getByText("Total Revenue")).toBeVisible();
    await expect(page.getByText("Total Profit")).toBeVisible();
    await expect(page.getByText("Avg Margin %")).toBeVisible();

    await expect(page.getByText("23.32")).toBeVisible();
  });

  test("create listing from product", async ({ page }) => {
    await page.goto("/products");
    await expect(page.getByText("Test Product A")).toBeVisible();

    await page.getByRole("link", { name: "Create Listing" }).first().click();
    await expect(page).toHaveURL(/\/listings\/new/);
    await expect(page.getByRole("heading", { name: /Create Listing/i })).toBeVisible();
  });
});
