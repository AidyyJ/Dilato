import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import NewListingForm from "@/app/listings/new/NewListingForm";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    products: {
      list: jest.fn(),
    },
    listings: {
      create: jest.fn(),
    },
    pricing: {
      calculate: jest.fn(),
    },
  },
}));

const mockPush = jest.fn();
let mockSearchParams: URLSearchParams;

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    refresh: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    prefetch: jest.fn(),
  }),
  useSearchParams: () => mockSearchParams,
  usePathname: jest.fn(),
}));

const productsFixture = [
  {
    id: 1,
    asin: "B0TEST1",
    title: "Test Product One",
    brand: "TestBrand",
    category: "Electronics",
    image_url: null,
    detail_page_url: null,
    amazon_price: "49.99",
    current_price: "49.99",
    source: "amazon" as const,
    is_active: true,
    last_synced_at: null,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  },
  {
    id: 2,
    asin: "B0TEST2",
    title: "Test Product Two",
    brand: undefined,
    category: undefined,
    image_url: null,
    detail_page_url: null,
    amazon_price: "29.99",
    current_price: "29.99",
    source: "amazon" as const,
    is_active: true,
    last_synced_at: null,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  },
];

const previewFixture = {
  product_id: 1,
  amazon_price: "49.99",
  listing_price: "59.99",
  rule_applied: { id: 1, name: "Default Markup", rule_type: "percentage" as const, value: "20", min_price: undefined, max_price: undefined, min_margin_percent: undefined, priority: 1, is_active: true, created_at: "", updated_at: "" },
};

describe("NewListingForm", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSearchParams = new URLSearchParams();
    (api.products.list as jest.Mock).mockReturnValue(new Promise(() => {}));
  });

  it("renders the form with heading", () => {
    render(<NewListingForm />);
    expect(screen.getByText("Create Listing")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Draft Listing" })).toBeInTheDocument();
  });

  it("fetches products on mount", async () => {
    (api.products.list as jest.Mock).mockResolvedValue(productsFixture);
    render(<NewListingForm />);

    await waitFor(() => {
      expect(api.products.list).toHaveBeenCalledWith({ limit: 500 });
    });

    await waitFor(() => {
      expect(screen.getByText("B0TEST1 — Test Product One")).toBeInTheDocument();
    });
  });

  it("submit button is disabled when no product selected", async () => {
    (api.products.list as jest.Mock).mockResolvedValue(productsFixture);
    render(<NewListingForm />);

    await waitFor(() => {
      expect(screen.getByText("B0TEST1 — Test Product One")).toBeInTheDocument();
    });

    const btn = screen.getByRole("button", { name: "Create Draft Listing" });
    expect(btn).toBeDisabled();
  });

  it("auto-selects product and fetches preview when productId is in search params", async () => {
    mockSearchParams = new URLSearchParams({ productId: "1" });
    (api.products.list as jest.Mock).mockResolvedValue(productsFixture);
    (api.pricing.calculate as jest.Mock).mockResolvedValue(previewFixture);

    render(<NewListingForm />);

    await waitFor(() => {
      expect(api.pricing.calculate).toHaveBeenCalledWith({ product_id: 1 });
    });

    await waitFor(() => {
      expect(screen.getByText("59.99")).toBeInTheDocument();
      expect(screen.getByText("Default Markup")).toBeInTheDocument();
    });

    // Title should be auto-filled
    const titleInput = screen.getByLabelText("Listing Title") as HTMLInputElement;
    expect(titleInput.value).toBe("Test Product One");
  });

  it("still calls pricing preview when preselected product not in local list", async () => {
    mockSearchParams = new URLSearchParams({ productId: "999" });
    (api.products.list as jest.Mock).mockResolvedValue(productsFixture);
    (api.pricing.calculate as jest.Mock).mockResolvedValue(previewFixture);

    render(<NewListingForm />);

    await waitFor(() => {
      expect(api.products.list).toHaveBeenCalled();
    });

    // Preview is called regardless — backend may still have the product
    await waitFor(() => {
      expect(api.pricing.calculate).toHaveBeenCalledWith({ product_id: 999 });
    });
  });

  it("fetches preview when user selects a product", async () => {
    (api.products.list as jest.Mock).mockResolvedValue(productsFixture);
    (api.pricing.calculate as jest.Mock).mockResolvedValue(previewFixture);

    render(<NewListingForm />);

    await waitFor(() => {
      expect(screen.getByText("B0TEST1 — Test Product One")).toBeInTheDocument();
    });

    const select = screen.getByLabelText("Product");
    fireEvent.change(select, { target: { value: "1" } });

    await waitFor(() => {
      expect(api.pricing.calculate).toHaveBeenCalledWith({ product_id: 1 });
    });

    await waitFor(() => {
      expect(screen.getByText("59.99")).toBeInTheDocument();
    });
  });

  it("shows error when preview fetch fails", async () => {
    (api.products.list as jest.Mock).mockResolvedValue(productsFixture);
    (api.pricing.calculate as jest.Mock).mockRejectedValue(new Error("Pricing API down"));

    render(<NewListingForm />);

    await waitFor(() => {
      expect(screen.getByText("B0TEST1 — Test Product One")).toBeInTheDocument();
    });

    const select = screen.getByLabelText("Product");
    fireEvent.change(select, { target: { value: "1" } });

    await waitFor(() => {
      expect(screen.getByText("Pricing API down")).toBeInTheDocument();
    });
  });

  it("submits listing and navigates on success", async () => {
    (api.products.list as jest.Mock).mockResolvedValue(productsFixture);
    (api.listings.create as jest.Mock).mockResolvedValue({});

    render(<NewListingForm />);

    await waitFor(() => {
      expect(screen.getByText("B0TEST1 — Test Product One")).toBeInTheDocument();
    });

    // Select product
    fireEvent.change(screen.getByLabelText("Product"), { target: { value: "1" } });

    // Fill required fields
    fireEvent.change(screen.getByLabelText("Listing Title"), { target: { value: "My Listing" } });
    fireEvent.change(screen.getByLabelText("Listing Price"), { target: { value: "59.99" } });

    fireEvent.click(screen.getByRole("button", { name: "Create Draft Listing" }));

    await waitFor(() => {
      expect(api.listings.create).toHaveBeenCalledWith({
        product_id: 1,
        title: "My Listing",
        listing_price: "59.99",
        quantity: 1,
        ebay_category_id: undefined,
        listing_duration: "GTC",
      });
    });

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/listings");
    });
  });

  it("shows error when submit fails", async () => {
    (api.products.list as jest.Mock).mockResolvedValue(productsFixture);
    (api.listings.create as jest.Mock).mockRejectedValue(new Error("Creation failed"));

    render(<NewListingForm />);

    await waitFor(() => {
      expect(screen.getByText("B0TEST1 — Test Product One")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Product"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Listing Title"), { target: { value: "My Listing" } });
    fireEvent.change(screen.getByLabelText("Listing Price"), { target: { value: "59.99" } });

    fireEvent.click(screen.getByRole("button", { name: "Create Draft Listing" }));

    await waitFor(() => {
      expect(screen.getByText("Creation failed")).toBeInTheDocument();
    });

    // Should not navigate on error
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("shows Amazon price and category for selected product", async () => {
    (api.products.list as jest.Mock).mockResolvedValue(productsFixture);

    render(<NewListingForm />);

    await waitFor(() => {
      expect(screen.getByText("B0TEST1 — Test Product One")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Product"), { target: { value: "1" } });

    await waitFor(() => {
      expect(screen.getByText("49.99")).toBeInTheDocument();
      expect(screen.getByText("Electronics")).toBeInTheDocument();
    });
  });

  it("Cancel button navigates to /listings", () => {
    render(<NewListingForm />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(mockPush).toHaveBeenCalledWith("/listings");
  });

  it("shows 'Calculating price…' while preview is loading", async () => {
    (api.products.list as jest.Mock).mockResolvedValue(productsFixture);
    // Never resolves so loading state persists
    (api.pricing.calculate as jest.Mock).mockReturnValue(new Promise(() => {}));

    render(<NewListingForm />);

    await waitFor(() => {
      expect(screen.getByText("B0TEST1 — Test Product One")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Product"), { target: { value: "1" } });

    await waitFor(() => {
      expect(screen.getByText("Calculating price…")).toBeInTheDocument();
    });
  });

  it("clears error when product changes", async () => {
    (api.products.list as jest.Mock).mockResolvedValue(productsFixture);
    (api.pricing.calculate as jest.Mock)
      .mockRejectedValueOnce(new Error("Pricing API down"))
      .mockResolvedValueOnce(previewFixture);

    render(<NewListingForm />);

    await waitFor(() => {
      expect(screen.getByText("B0TEST1 — Test Product One")).toBeInTheDocument();
    });

    // Select product 1 — fails
    fireEvent.change(screen.getByLabelText("Product"), { target: { value: "1" } });
    await waitFor(() => {
      expect(screen.getByText("Pricing API down")).toBeInTheDocument();
    });

    // Select product 2 — succeeds, error should clear
    fireEvent.change(screen.getByLabelText("Product"), { target: { value: "2" } });
    await waitFor(() => {
      expect(screen.getByText("59.99")).toBeInTheDocument();
    });

    expect(screen.queryByText("Pricing API down")).not.toBeInTheDocument();
  });
});
