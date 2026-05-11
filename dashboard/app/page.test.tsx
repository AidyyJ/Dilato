import { render, screen, waitFor } from "@testing-library/react";
import HomePage from "@/app/page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    profit: {
      summary: jest.fn(),
      details: jest.fn(),
    },
    orders: {
      list: jest.fn(),
    },
  },
}));

describe("HomePage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const summary = {
    total_orders: 42,
    total_revenue: "2500.00",
    total_profit: "850.00",
    average_margin_percent: "34.00",
  };

  const orders = [
    {
      id: 1,
      ebay_order_id: "EBAY-1",
      sale_price: "100.00",
      status: "pending",
      created_at: "2024-01-15T10:00:00Z",
    },
    {
      id: 2,
      ebay_order_id: "EBAY-2",
      sale_price: "200.00",
      status: "shipped",
      created_at: "2024-01-14T10:00:00Z",
    },
  ];

  const profitDetails = [
    {
      order_id: 1,
      ebay_order_id: "EBAY-1",
      sale_price: "100.00",
      shipping_cost: "5.00",
      ebay_fee: "4.00",
      purchase_cost: "60.00",
      profit: "31.00",
      margin_percent: "31.00",
    },
    {
      order_id: 2,
      ebay_order_id: "EBAY-2",
      sale_price: "200.00",
      shipping_cost: "10.00",
      ebay_fee: "8.00",
      purchase_cost: "120.00",
      profit: "62.00",
      margin_percent: "31.00",
    },
    {
      order_id: 3,
      ebay_order_id: "EBAY-3",
      sale_price: "50.00",
      shipping_cost: "5.00",
      ebay_fee: "2.00",
      purchase_cost: "40.00",
      profit: "3.00",
      margin_percent: "6.00",
    },
  ];

  it("renders the dashboard heading", () => {
    (api.profit.summary as jest.Mock).mockReturnValue(new Promise(() => {}));
    (api.orders.list as jest.Mock).mockReturnValue(new Promise(() => {}));
    (api.profit.details as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<HomePage />);
    expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("renders the description text", () => {
    (api.profit.summary as jest.Mock).mockReturnValue(new Promise(() => {}));
    (api.orders.list as jest.Mock).mockReturnValue(new Promise(() => {}));
    (api.profit.details as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<HomePage />);
    expect(screen.getByText(/Overview of your Amazon-to-eBay reselling pipeline./)).toBeInTheDocument();
  });

  it("shows skeleton loaders while loading", () => {
    (api.profit.summary as jest.Mock).mockReturnValue(new Promise(() => {}));
    (api.orders.list as jest.Mock).mockReturnValue(new Promise(() => {}));
    (api.profit.details as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<HomePage />);
    expect(screen.getByLabelText("Analytics")).toBeInTheDocument();
    expect(screen.getByLabelText("Recent Orders")).toBeInTheDocument();
    expect(screen.getByLabelText("Charts")).toBeInTheDocument();
  });

  it("renders KPI cards and recent orders after loading", async () => {
    (api.profit.summary as jest.Mock).mockResolvedValue(summary);
    (api.orders.list as jest.Mock).mockResolvedValue(orders);
    (api.profit.details as jest.Mock).mockResolvedValue(profitDetails);

    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText("42")).toBeInTheDocument();
    });

    expect(screen.getByText("Total Orders")).toBeInTheDocument();
    expect(screen.getByText("2500.00")).toBeInTheDocument();
    expect(screen.getByText("850.00")).toBeInTheDocument();
    expect(screen.getByText("34.00%")).toBeInTheDocument();
    expect(screen.getAllByText("EBAY-1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("EBAY-2").length).toBeGreaterThanOrEqual(1);
  });

  it("renders chart sections after loading", async () => {
    (api.profit.summary as jest.Mock).mockResolvedValue(summary);
    (api.orders.list as jest.Mock).mockResolvedValue(orders);
    (api.profit.details as jest.Mock).mockResolvedValue(profitDetails);

    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText("Profit Trend (Last 30 Days)")).toBeInTheDocument();
    });

    expect(screen.getByText("Margin Distribution")).toBeInTheDocument();
    expect(screen.getByText("Top Orders by Margin")).toBeInTheDocument();
  });

  it("renders top orders by margin table", async () => {
    (api.profit.summary as jest.Mock).mockResolvedValue(summary);
    (api.orders.list as jest.Mock).mockResolvedValue(orders);
    (api.profit.details as jest.Mock).mockResolvedValue(profitDetails);

    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText("Top Orders by Margin")).toBeInTheDocument();
    });

    expect(screen.getAllByText("31.00%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("6.00%")).toBeInTheDocument();
  });

  it("renders quick link cards", async () => {
    (api.profit.summary as jest.Mock).mockResolvedValue(summary);
    (api.orders.list as jest.Mock).mockResolvedValue(orders);
    (api.profit.details as jest.Mock).mockResolvedValue(profitDetails);

    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText("Products")).toBeInTheDocument();
    });

    // Quick Links section uses h3 titles inside link cards
    const quickLinks = screen.getByLabelText("Quick Links");
    expect(quickLinks).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Products/i })).toHaveAttribute("href", "/products");
    expect(screen.getByRole("link", { name: /Listings/i })).toHaveAttribute("href", "/listings");
    expect(screen.getByRole("link", { name: /Pricing Rules/i })).toHaveAttribute("href", "/pricing");
    expect(screen.getByRole("link", { name: /Create Listing/i })).toHaveAttribute("href", "/listings/new");
  });

  it("shows empty state when no recent orders", async () => {
    (api.profit.summary as jest.Mock).mockResolvedValue(summary);
    (api.orders.list as jest.Mock).mockResolvedValue([]);
    (api.profit.details as jest.Mock).mockResolvedValue([]);

    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText("No recent orders.")).toBeInTheDocument();
    });
  });

  it("shows empty state for charts when no profit data", async () => {
    (api.profit.summary as jest.Mock).mockResolvedValue({
      total_orders: 0,
      total_revenue: "0.00",
      total_profit: null,
      average_margin_percent: null,
    });
    (api.orders.list as jest.Mock).mockResolvedValue([]);
    (api.profit.details as jest.Mock).mockResolvedValue([]);

    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText("No profit trend data available.")).toBeInTheDocument();
    });
    expect(screen.getByText("No margin distribution data available.")).toBeInTheDocument();
  });

  it("shows error on fetch failure", async () => {
    (api.profit.summary as jest.Mock).mockRejectedValue(new Error("Network error"));
    (api.orders.list as jest.Mock).mockRejectedValue(new Error("Network error"));
    (api.profit.details as jest.Mock).mockRejectedValue(new Error("Network error"));

    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  it("links KPI cards to correct routes", async () => {
    (api.profit.summary as jest.Mock).mockResolvedValue(summary);
    (api.orders.list as jest.Mock).mockResolvedValue(orders);
    (api.profit.details as jest.Mock).mockResolvedValue(profitDetails);

    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText("42")).toBeInTheDocument();
    });

    expect(screen.getByText("Total Orders").closest("a")).toHaveAttribute("href", "/orders");
    expect(screen.getByText("Total Revenue").closest("a")).toHaveAttribute("href", "/profits");
  });
});
