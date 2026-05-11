import { render, screen, fireEvent } from "@testing-library/react";
import Sidebar from "@/components/Sidebar";
import * as navigation from "next/navigation";

// Mock next/navigation with mutable pathname
const mockUsePathname = jest.fn(() => "/");
jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    refresh: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    prefetch: jest.fn(),
  }),
  usePathname: () => mockUsePathname(),
}));

describe("Sidebar", () => {
  beforeEach(() => {
    mockUsePathname.mockReturnValue("/");
  });

  it("renders brand name and tagline", () => {
    render(<Sidebar />);
    expect(screen.getByText("Reseller Hub")).toBeInTheDocument();
    expect(screen.getByText("Amazon → eBay")).toBeInTheDocument();
  });

  it("renders all navigation links", () => {
    render(<Sidebar />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Products")).toBeInTheDocument();
    expect(screen.getByText("Listings")).toBeInTheDocument();
    expect(screen.getByText("Orders")).toBeInTheDocument();
    expect(screen.getByText("Pricing Rules")).toBeInTheDocument();
  });

  it("marks Dashboard as active on home route", () => {
    mockUsePathname.mockReturnValue("/");
    render(<Sidebar />);
    const dashboardLink = screen.getByText("Dashboard").closest("a");
    expect(dashboardLink).toHaveClass("bg-neutral-200");
  });

  it("marks Products as active on /products", () => {
    mockUsePathname.mockReturnValue("/products");
    render(<Sidebar />);
    const productsLink = screen.getByText("Products").closest("a");
    expect(productsLink).toHaveClass("bg-neutral-200");
  });

  it("marks Listings as active on /listings", () => {
    mockUsePathname.mockReturnValue("/listings");
    render(<Sidebar />);
    const listingsLink = screen.getByText("Listings").closest("a");
    expect(listingsLink).toHaveClass("bg-neutral-200");
  });

  it("marks Orders as active on /orders", () => {
    mockUsePathname.mockReturnValue("/orders");
    render(<Sidebar />);
    const ordersLink = screen.getByText("Orders").closest("a");
    expect(ordersLink).toHaveClass("bg-neutral-200");
  });

  it("has a toggle button with aria-label", () => {
    render(<Sidebar />);
    expect(screen.getByLabelText("Toggle menu")).toBeInTheDocument();
  });

  it("toggles mobile menu on button click", () => {
    render(<Sidebar />);
    const toggleBtn = screen.getByLabelText("Toggle menu");
    const aside = document.querySelector("aside");
    expect(aside).toHaveClass("-translate-x-full");
    fireEvent.click(toggleBtn);
    expect(aside).toHaveClass("translate-x-0");
  });

  it("renders version in footer", () => {
    render(<Sidebar />);
    expect(screen.getByText("v0.1.0")).toBeInTheDocument();
  });
});
