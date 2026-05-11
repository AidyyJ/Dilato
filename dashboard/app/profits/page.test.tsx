import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import ProfitsPage from "@/app/profits/page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    profit: {
      summary: jest.fn(),
      details: jest.fn(),
    },
  },
}));

describe("ProfitsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const summary = {
    total_orders: 10,
    total_revenue: "500.00",
    total_purchase_cost: "300.00",
    total_shipping_cost: "50.00",
    total_ebay_fees: "40.00",
    total_profit: "110.00",
    average_margin_percent: "22.00",
  };

  const details = [
    {
      order_id: 1,
      ebay_order_id: "EBAY-1",
      sale_price: "50.00",
      shipping_cost: "5.00",
      ebay_fee: "4.00",
      purchase_cost: "30.00",
      profit: "11.00",
      margin_percent: "22.00",
    },
    {
      order_id: 2,
      ebay_order_id: "EBAY-2",
      sale_price: "100.00",
      shipping_cost: "10.00",
      ebay_fee: "8.00",
      purchase_cost: "60.00",
      profit: "22.00",
      margin_percent: "22.00",
    },
  ];

  it("shows loading state initially", () => {
    (api.profit.summary as jest.Mock).mockReturnValue(new Promise(() => {}));
    (api.profit.details as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<ProfitsPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders summary cards and details table", async () => {
    (api.profit.summary as jest.Mock).mockResolvedValue(summary);
    (api.profit.details as jest.Mock).mockResolvedValue(details);

    render(<ProfitsPage />);

    await waitFor(() => {
      expect(screen.getByText("Total Orders")).toBeInTheDocument();
    });

    expect(screen.getByText("500.00")).toBeInTheDocument();
    expect(screen.getByText("110.00")).toBeInTheDocument();
    expect(screen.getAllByText("22.00%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("EBAY-1")).toBeInTheDocument();
    expect(screen.getByText("EBAY-2")).toBeInTheDocument();
  });

  it("shows empty state when no details", async () => {
    (api.profit.summary as jest.Mock).mockResolvedValue({
      total_orders: 0,
      total_revenue: "0.00",
      total_profit: null,
      average_margin_percent: null,
    });
    (api.profit.details as jest.Mock).mockResolvedValue([]);

    render(<ProfitsPage />);

    await waitFor(() => {
      expect(screen.getByText("No profit details found.")).toBeInTheDocument();
    });
  });

  it("shows error on fetch failure", async () => {
    (api.profit.summary as jest.Mock).mockRejectedValue(new Error("Network error"));
    (api.profit.details as jest.Mock).mockRejectedValue(new Error("Network error"));

    render(<ProfitsPage />);

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  it("filters by status", async () => {
    (api.profit.summary as jest.Mock).mockResolvedValue(summary);
    (api.profit.details as jest.Mock).mockResolvedValue([]);

    render(<ProfitsPage />);

    await waitFor(() => {
      expect(screen.getByText("No profit details found.")).toBeInTheDocument();
    });

    const select = screen.getByLabelText("Status:");
    fireEvent.change(select, { target: { value: "shipped" } });

    await waitFor(() => {
      expect(api.profit.details).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "shipped" })
      );
    });
  });
});
