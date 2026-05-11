import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import ProductsPage from "@/app/products/page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    products: {
      list: jest.fn(),
    },
    sourcing: {
      search: jest.fn(),
    },
  },
}));

describe("ProductsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("shows loading state initially", () => {
    (api.products.list as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<ProductsPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders products after loading", async () => {
    (api.products.list as jest.Mock).mockResolvedValue([
      {
        id: 1,
        asin: "B000TEST01",
        title: "Test Product",
        amazon_price: "29.99",
        category: "Electronics",
        source: "amazon",
        is_active: true,
        last_synced_at: "2024-01-01T00:00:00Z",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      },
    ]);

    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Product")).toBeInTheDocument();
    });

    expect(screen.getByText("B000TEST01")).toBeInTheDocument();
    expect(screen.getByText("29.99")).toBeInTheDocument();
    expect(screen.getByText("Electronics")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
  });

  it("shows empty state when no products", async () => {
    (api.products.list as jest.Mock).mockResolvedValue([]);
    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("No products found.")).toBeInTheDocument();
    });
  });

  it("shows error message on fetch failure", async () => {
    (api.products.list as jest.Mock).mockRejectedValue(new Error("Network error"));
    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  it("shows fallback error message on non-Error throw", async () => {
    (api.products.list as jest.Mock).mockRejectedValue("Network error");
    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load products")).toBeInTheDocument();
    });
  });

  it("renders inactive product badge", async () => {
    (api.products.list as jest.Mock).mockResolvedValue([
      {
        id: 1,
        asin: "B000TEST01",
        title: "Inactive Product",
        source: "amazon",
        is_active: false,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      },
    ]);

    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("Inactive Product")).toBeInTheDocument();
    });

    const badge = screen.getByText("No");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("bg-neutral-100");
    expect(badge).toHaveClass("text-neutral-800");
  });

  it("has pagination controls", async () => {
    (api.products.list as jest.Mock).mockResolvedValue([]);
    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("No products found.")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeInTheDocument();
    expect(screen.getByText("Page 1")).toBeInTheDocument();
  });

  it("navigates to next page", async () => {
    (api.products.list as jest.Mock).mockResolvedValue(
      Array.from({ length: 20 }, (_, i) => ({
        id: i + 1,
        asin: `B000TEST${String(i + 1).padStart(2, "0")}`,
        title: `Product ${i + 1}`,
        source: "amazon",
        is_active: true,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      }))
    );

    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("Product 1")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(api.products.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip: 20, limit: 20 })
      );
    });

    expect(screen.getByText("Page 2")).toBeInTheDocument();
  });

  it("navigates to previous page", async () => {
    (api.products.list as jest.Mock).mockResolvedValue(
      Array.from({ length: 20 }, (_, i) => ({
        id: i + 1,
        asin: `B000TEST${String(i + 1).padStart(2, "0")}`,
        title: `Product ${i + 1}`,
        source: "amazon",
        is_active: true,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      }))
    );

    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("Product 1")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(screen.getByText("Page 2")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));

    await waitFor(() => {
      expect(api.products.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip: 0, limit: 20 })
      );
    });

    expect(screen.getByText("Page 1")).toBeInTheDocument();
  });

  it("calls source and shows results", async () => {
    (api.products.list as jest.Mock).mockResolvedValue([]);
    (api.sourcing.search as jest.Mock).mockResolvedValue([
      {
        asin: "B000SRC01",
        title: "Sourced Product",
        amazon_price: "15.99",
        estimated_ebay_price: "24.99",
        estimated_margin: 0.35,
        category: "Home",
      },
    ]);

    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("No products found.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Source Products" }));

    await waitFor(() => {
      expect(api.sourcing.search).toHaveBeenCalledWith({ max_results: 20 });
    });

    await waitFor(() => {
      expect(screen.getByText("Sourcing Results")).toBeInTheDocument();
    });

    expect(screen.getByText("B000SRC01")).toBeInTheDocument();
    expect(screen.getByText("Sourced Product")).toBeInTheDocument();
    expect(screen.getByText("15.99")).toBeInTheDocument();
    expect(screen.getByText("24.99")).toBeInTheDocument();
    expect(screen.getByText("35.0%")).toBeInTheDocument();
  });

  it("shows sourcing empty state", async () => {
    (api.products.list as jest.Mock).mockResolvedValue([]);
    (api.sourcing.search as jest.Mock).mockResolvedValue([]);

    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("No products found.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Source Products" }));

    await waitFor(() => {
      expect(screen.getByText("Sourcing Results")).toBeInTheDocument();
    });

    expect(screen.getByText("No results found.")).toBeInTheDocument();
  });

  it("shows error on sourcing failure", async () => {
    (api.products.list as jest.Mock).mockResolvedValue([]);
    (api.sourcing.search as jest.Mock).mockRejectedValue(new Error("Sourcing API error"));

    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("No products found.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Source Products" }));

    await waitFor(() => {
      expect(screen.getByText("Sourcing API error")).toBeInTheDocument();
    });
  });

  it("shows fallback sourcing error message on non-Error throw", async () => {
    (api.products.list as jest.Mock).mockResolvedValue([]);
    (api.sourcing.search as jest.Mock).mockRejectedValue("Sourcing API error");

    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("No products found.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Source Products" }));

    await waitFor(() => {
      expect(screen.getByText("Sourcing failed")).toBeInTheDocument();
    });
  });

  it("dismisses sourcing results", async () => {
    (api.products.list as jest.Mock).mockResolvedValue([]);
    (api.sourcing.search as jest.Mock).mockResolvedValue([
      {
        asin: "B000SRC01",
        title: "Sourced Product",
        amazon_price: "15.99",
        source: "amazon",
      },
    ]);

    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("No products found.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Source Products" }));

    await waitFor(() => {
      expect(screen.getByText("Sourcing Results")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() => {
      expect(screen.queryByText("Sourcing Results")).not.toBeInTheDocument();
    });
  });

  it("has Create Listing links for each product", async () => {
    (api.products.list as jest.Mock).mockResolvedValue([
      {
        id: 1,
        asin: "B000TEST01",
        title: "Test Product",
        source: "amazon",
        is_active: true,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      },
    ]);

    render(<ProductsPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Product")).toBeInTheDocument();
    });

    const link = screen.getByRole("link", { name: "Create Listing" });
    expect(link).toHaveAttribute("href", "/listings/new?productId=1");
  });
});
