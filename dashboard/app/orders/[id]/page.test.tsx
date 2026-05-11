import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import OrderDetailPage from "@/app/orders/[id]/page";
import { api } from "@/lib/api";

const mockPush = jest.fn();

jest.mock("next/navigation", () => ({
  useParams: () => ({ id: "42" }),
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/lib/api", () => ({
  api: {
    orders: {
      get: jest.fn(),
      getProfit: jest.fn(),
      generatePurchaseLink: jest.fn(),
      markPurchased: jest.fn(),
      updateStatus: jest.fn(),
      updateFulfillment: jest.fn(),
    },
  },
}));

describe("OrderDetailPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const order = {
    id: 42,
    ebay_order_id: "EBAY-456",
    buyer_username: "buyer1",
    sale_price: "49.99",
    quantity: 2,
    shipping_cost: "5.00",
    ebay_fee: "4.00",
    status: "pending",
    fulfillment_status: "not_started",
    tracking_number: null,
    carrier: null,
    created_at: "2024-02-01T00:00:00Z",
    last_webhook_at: null,
    amazon_purchase_url: null,
    purchase_cost: null,
    profit: null,
    margin_percent: null,
    amazon_order_id: null,
    purchased_at: null,
  };

  const profit = {
    order_id: 42,
    ebay_order_id: "EBAY-456",
    sale_price: "49.99",
    shipping_cost: "5.00",
    ebay_fee: "4.00",
    purchase_cost: "30.00",
    profit: "10.99",
    margin_percent: "21.98",
  };

  it("shows loading state initially", () => {
    (api.orders.get as jest.Mock).mockReturnValue(new Promise(() => {}));
    (api.orders.getProfit as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<OrderDetailPage />);
    expect(document.querySelectorAll("[aria-hidden='true']").length).toBeGreaterThan(0);
  });

  it("renders order details and profit", async () => {
    (api.orders.get as jest.Mock).mockResolvedValue(order);
    (api.orders.getProfit as jest.Mock).mockResolvedValue(profit);

    render(<OrderDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Order #42")).toBeInTheDocument();
    });

    expect(screen.getByText(/EBAY-456/)).toBeInTheDocument();
    expect(screen.getByText("buyer1")).toBeInTheDocument();
    expect(screen.getAllByText("49.99").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("10.99")).toBeInTheDocument();
  });

  it("shows error when order not found", async () => {
    (api.orders.get as jest.Mock).mockRejectedValue(new Error("Not found"));
    (api.orders.getProfit as jest.Mock).mockRejectedValue(new Error("Not found"));

    render(<OrderDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Not found")).toBeInTheDocument();
    });
  });

  it("generates purchase link", async () => {
    (api.orders.get as jest.Mock).mockResolvedValue(order);
    (api.orders.getProfit as jest.Mock).mockResolvedValue(profit);
    (api.orders.generatePurchaseLink as jest.Mock).mockResolvedValue({
      order_id: 42,
      purchase_url: "https://amazon.com/add-to-cart",
    });

    render(<OrderDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Order #42")).toBeInTheDocument();
    });

    const btn = screen.getByRole("button", { name: /Generate Amazon Purchase Link/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByText("https://amazon.com/add-to-cart")).toBeInTheDocument();
    });
  });

  it("marks order as purchased", async () => {
    (api.orders.get as jest.Mock).mockResolvedValue(order);
    (api.orders.getProfit as jest.Mock)
      .mockResolvedValueOnce(profit)
      .mockResolvedValueOnce({
        ...profit,
        purchase_cost: "30.00",
        profit: "10.99",
      });
    (api.orders.markPurchased as jest.Mock).mockResolvedValue({
      ...order,
      purchase_cost: "30.00",
      amazon_order_id: "AMZ-123",
      fulfillment_status: "in_progress",
    });

    render(<OrderDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Order #42")).toBeInTheDocument();
    });

    const costInput = screen.getByLabelText(/Purchase Cost/i);
    const amazonIdInput = screen.getByLabelText(/Amazon Order ID/i);
    const submit = screen.getByRole("button", { name: /Mark as Purchased/i });

    fireEvent.change(costInput, { target: { value: "30.00" } });
    fireEvent.change(amazonIdInput, { target: { value: "AMZ-123" } });
    fireEvent.click(submit);

    await waitFor(() => {
      expect(api.orders.markPurchased).toHaveBeenCalledWith(42, expect.objectContaining({
        purchase_cost: "30.00",
        amazon_order_id: "AMZ-123",
      }));
    });
  });

  it("updates order status", async () => {
    (api.orders.get as jest.Mock).mockResolvedValue(order);
    (api.orders.getProfit as jest.Mock).mockResolvedValue(profit);
    (api.orders.updateStatus as jest.Mock).mockResolvedValue({ ...order, status: "shipped" });

    render(<OrderDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Order #42")).toBeInTheDocument();
    });

    const statusSelect = screen.getByDisplayValue("Pending");
    fireEvent.change(statusSelect, { target: { value: "shipped" } });

    await waitFor(() => {
      expect(api.orders.updateStatus).toHaveBeenCalledWith(42, "shipped");
    });
  });

  it("navigates back to orders list", async () => {
    (api.orders.get as jest.Mock).mockResolvedValue(order);
    (api.orders.getProfit as jest.Mock).mockResolvedValue(profit);

    render(<OrderDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Order #42")).toBeInTheDocument();
    });

    const backBtn = screen.getByRole("button", { name: /Back to Orders/i });
    fireEvent.click(backBtn);

    expect(mockPush).toHaveBeenCalledWith("/orders");
  });
});
