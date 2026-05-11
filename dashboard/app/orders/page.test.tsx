import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import OrdersPage from "@/app/orders/page";
import { api } from "@/lib/api";
import * as navigation from "next/navigation";

const mockPush = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

jest.mock("@/lib/api", () => ({
  api: {
    orders: {
      list: jest.fn(),
    },
  },
}));

describe("OrdersPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("shows loading state initially", () => {
    (api.orders.list as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<OrdersPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders orders after loading", async () => {
    (api.orders.list as jest.Mock).mockResolvedValue([
      {
        id: 1,
        ebay_order_id: "EBAY-123",
        listing_id: 10,
        sale_price: "29.99",
        quantity: 1,
        status: "pending",
        fulfillment_status: "not_started",
        created_at: "2024-01-15T00:00:00Z",
      },
    ]);

    render(<OrdersPage />);

    await waitFor(() => {
      expect(screen.getByText("EBAY-123")).toBeInTheDocument();
    });

    expect(screen.getByText("29.99")).toBeInTheDocument();
    expect(screen.getAllByText("Pending").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("not started")).toBeInTheDocument();
  });

  it("shows empty state when no orders", async () => {
    (api.orders.list as jest.Mock).mockResolvedValue([]);
    render(<OrdersPage />);

    await waitFor(() => {
      expect(screen.getByText("No orders found.")).toBeInTheDocument();
    });
  });

  it("shows error message on fetch failure", async () => {
    (api.orders.list as jest.Mock).mockRejectedValue(new Error("Network error"));
    render(<OrdersPage />);

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  it("filters by status", async () => {
    (api.orders.list as jest.Mock).mockResolvedValue([]);
    render(<OrdersPage />);

    await waitFor(() => {
      expect(screen.getByText("No orders found.")).toBeInTheDocument();
    });

    const select = screen.getByLabelText("Filter by status:");
    fireEvent.change(select, { target: { value: "shipped" } });

    await waitFor(() => {
      expect(api.orders.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "shipped" })
      );
    });
  });

  it("navigates to order detail on row click", async () => {
    (api.orders.list as jest.Mock).mockResolvedValue([
      {
        id: 42,
        ebay_order_id: "EBAY-456",
        listing_id: 20,
        sale_price: "49.99",
        quantity: 2,
        status: "shipped",
        fulfillment_status: "in_progress",
        created_at: "2024-02-01T00:00:00Z",
      },
    ]);

    render(<OrdersPage />);

    await waitFor(() => {
      expect(screen.getByText("EBAY-456")).toBeInTheDocument();
    });

    const row = screen.getByText("EBAY-456").closest("tr");
    fireEvent.click(row!);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/orders/42");
    });
  });
});
