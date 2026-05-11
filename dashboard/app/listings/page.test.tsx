import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import ListingsPage from "@/app/listings/page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    listings: {
      list: jest.fn(),
      updateStatus: jest.fn(),
    },
  },
}));

describe("ListingsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("shows loading state initially", () => {
    (api.listings.list as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<ListingsPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders listings after loading", async () => {
    (api.listings.list as jest.Mock).mockResolvedValue([
      {
        id: 1,
        product_id: 10,
        title: "Test Listing",
        listing_price: "19.99",
        quantity: 5,
        listing_duration: "GTC",
        quantity_sold: 0,
        status: "draft",
        created_at: "2024-01-01T00:00:00Z",
      },
    ]);

    render(<ListingsPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Listing")).toBeInTheDocument();
    });

    expect(screen.getByText("19.99")).toBeInTheDocument();
    expect(screen.getAllByText("Draft").length).toBeGreaterThanOrEqual(1);
  });

  it("shows empty state when no listings", async () => {
    (api.listings.list as jest.Mock).mockResolvedValue([]);
    render(<ListingsPage />);

    await waitFor(() => {
      expect(screen.getByText("No listings found.")).toBeInTheDocument();
    });
  });

  it("shows error message on fetch failure", async () => {
    (api.listings.list as jest.Mock).mockRejectedValue(new Error("Network error"));
    render(<ListingsPage />);

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  it("has a Create Listing link", () => {
    (api.listings.list as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<ListingsPage />);
    expect(screen.getByRole("link", { name: "Create Listing" })).toHaveAttribute("href", "/listings/new");
  });

  it("filters by status", async () => {
    (api.listings.list as jest.Mock).mockResolvedValue([]);
    render(<ListingsPage />);

    await waitFor(() => {
      expect(screen.getByText("No listings found.")).toBeInTheDocument();
    });

    const select = screen.getByLabelText("Filter by status:");
    fireEvent.change(select, { target: { value: "active" } });

    await waitFor(() => {
      expect(api.listings.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "active" })
      );
    });
  });

  it("calls publish and updates status", async () => {
    (api.listings.list as jest.Mock).mockResolvedValue([
      {
        id: 1,
        product_id: 10,
        title: "Draft Listing",
        listing_price: "9.99",
        quantity: 1,
        listing_duration: "GTC",
        quantity_sold: 0,
        status: "draft",
        created_at: "2024-01-01T00:00:00Z",
      },
    ]);
    (api.listings.updateStatus as jest.Mock).mockResolvedValue({ id: 1, status: "active" });

    render(<ListingsPage />);

    await waitFor(() => {
      expect(screen.getByText("Draft Listing")).toBeInTheDocument();
    });

    const publishBtn = screen.getByRole("button", { name: "Publish" });
    fireEvent.click(publishBtn);

    await waitFor(() => {
      expect(api.listings.updateStatus).toHaveBeenCalledWith(1, "active");
    });
  });
});
