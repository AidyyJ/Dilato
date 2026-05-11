import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import PricingPage from "@/app/pricing/page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    pricing: {
      listRules: jest.fn(),
      createRule: jest.fn(),
      updateRule: jest.fn(),
      deleteRule: jest.fn(),
    },
  },
}));

const mockRule = {
  id: 1,
  name: "Test Rule",
  rule_type: "fixed_markup" as const,
  value: "10.00",
  min_price: "5.00",
  max_price: "100.00",
  min_margin_percent: "0.20",
  priority: 1,
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

const mockRuleInactive = {
  id: 2,
  name: "Inactive Rule",
  rule_type: "percentage" as const,
  value: "15.00",
  priority: 2,
  is_active: false,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

describe("PricingPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.confirm = jest.fn(() => true);
  });

  it("shows loading state initially", () => {
    (api.pricing.listRules as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<PricingPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders pricing rules after loading", async () => {
    (api.pricing.listRules as jest.Mock).mockResolvedValue([mockRule, mockRuleInactive]);
    render(<PricingPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Rule")).toBeInTheDocument();
    });

    expect(screen.getByText("fixed_markup")).toBeInTheDocument();
    expect(screen.getByText("10.00")).toBeInTheDocument();
    expect(screen.getByText("5.00")).toBeInTheDocument();
    expect(screen.getByText("100.00")).toBeInTheDocument();
    expect(screen.getByText("0.20")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("Inactive Rule")).toBeInTheDocument();
    expect(screen.getByText("percentage")).toBeInTheDocument();
  });

  it("shows empty state when no rules", async () => {
    (api.pricing.listRules as jest.Mock).mockResolvedValue([]);
    render(<PricingPage />);

    await waitFor(() => {
      expect(screen.getByText("No pricing rules found.")).toBeInTheDocument();
    });
  });

  it("shows error message on fetch failure", async () => {
    (api.pricing.listRules as jest.Mock).mockRejectedValue(new Error("Network error"));
    render(<PricingPage />);

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  it("opens the form when Add Rule is clicked", async () => {
    (api.pricing.listRules as jest.Mock).mockResolvedValue([]);
    render(<PricingPage />);

    await waitFor(() => {
      expect(screen.getByText("No pricing rules found.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Add Rule" }));
    expect(screen.getByText("New Rule")).toBeInTheDocument();
  });

  it("closes the form when Cancel is clicked", async () => {
    (api.pricing.listRules as jest.Mock).mockResolvedValue([]);
    render(<PricingPage />);

    await waitFor(() => {
      expect(screen.getByText("No pricing rules found.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Add Rule" }));
    expect(screen.getByText("New Rule")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(screen.queryByText("New Rule")).not.toBeInTheDocument();
    });
  });

  it("creates a new rule via the form", async () => {
    (api.pricing.listRules as jest.Mock).mockResolvedValue([]);
    const createdRule = {
      id: 3,
      name: "New Rule",
      rule_type: "fixed_price" as const,
      value: "25.00",
      priority: 5,
      is_active: true,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    };
    (api.pricing.createRule as jest.Mock).mockResolvedValue(createdRule);

    render(<PricingPage />);

    await waitFor(() => {
      expect(screen.getByText("No pricing rules found.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Add Rule" }));

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "New Rule" },
    });
    fireEvent.change(screen.getByLabelText("Type"), {
      target: { value: "fixed_price" },
    });
    fireEvent.change(screen.getByLabelText("Value"), {
      target: { value: "25.00" },
    });
    fireEvent.change(screen.getByLabelText("Priority"), {
      target: { value: "5" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Create Rule" }));

    await waitFor(() => {
      expect(api.pricing.createRule).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "New Rule",
          rule_type: "fixed_price",
          value: "25.00",
          priority: 5,
          is_active: true,
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText("New Rule")).toBeInTheDocument();
    });
  });

  it("edits an existing rule via the form", async () => {
    (api.pricing.listRules as jest.Mock).mockResolvedValue([mockRule]);
    const updatedRule = { ...mockRule, name: "Updated Rule", value: "20.00" };
    (api.pricing.updateRule as jest.Mock).mockResolvedValue(updatedRule);

    render(<PricingPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Rule")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    await waitFor(() => {
      expect(screen.getByText("Edit Rule")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Updated Rule" },
    });
    fireEvent.change(screen.getByLabelText("Value"), {
      target: { value: "20.00" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Update Rule" }));

    await waitFor(() => {
      expect(api.pricing.updateRule).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          name: "Updated Rule",
          value: "20.00",
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText("Updated Rule")).toBeInTheDocument();
    });
  });

  it("deletes a rule after confirmation", async () => {
    (api.pricing.listRules as jest.Mock).mockResolvedValue([mockRule]);
    (api.pricing.deleteRule as jest.Mock).mockResolvedValue({});

    render(<PricingPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Rule")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(window.confirm).toHaveBeenCalledWith(
        "Are you sure you want to delete this pricing rule?"
      );
    });

    await waitFor(() => {
      expect(api.pricing.deleteRule).toHaveBeenCalledWith(1);
    });

    await waitFor(() => {
      expect(screen.queryByText("Test Rule")).not.toBeInTheDocument();
    });
  });

  it("does not delete a rule if confirmation is cancelled", async () => {
    window.confirm = jest.fn(() => false);
    (api.pricing.listRules as jest.Mock).mockResolvedValue([mockRule]);

    render(<PricingPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Rule")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(window.confirm).toHaveBeenCalled();
    });

    expect(api.pricing.deleteRule).not.toHaveBeenCalled();
    expect(screen.getByText("Test Rule")).toBeInTheDocument();
  });

  it("toggles active status", async () => {
    const updatedRule = { ...mockRule, is_active: false };
    (api.pricing.listRules as jest.Mock).mockResolvedValue([mockRule]);
    (api.pricing.updateRule as jest.Mock).mockResolvedValue(updatedRule);

    render(<PricingPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Rule")).toBeInTheDocument();
    });

    const activeButton = screen.getByRole("button", { name: "Yes" });
    fireEvent.click(activeButton);

    await waitFor(() => {
      expect(api.pricing.updateRule).toHaveBeenCalledWith(1, { is_active: false });
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "No" })).toBeInTheDocument();
    });
  });

  it("shows form error when save fails", async () => {
    (api.pricing.listRules as jest.Mock).mockResolvedValue([]);
    (api.pricing.createRule as jest.Mock).mockRejectedValue(new Error("Save failed"));

    render(<PricingPage />);

    await waitFor(() => {
      expect(screen.getByText("No pricing rules found.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Add Rule" }));

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Bad Rule" },
    });
    fireEvent.change(screen.getByLabelText("Value"), {
      target: { value: "10" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Create Rule" }));

    await waitFor(() => {
      expect(screen.getByText("Save failed")).toBeInTheDocument();
    });
  });

  it("shows active / inactive badges correctly", async () => {
    (api.pricing.listRules as jest.Mock).mockResolvedValue([mockRule, mockRuleInactive]);
    render(<PricingPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Rule")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: "Yes" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "No" })).toBeInTheDocument();
  });
});
