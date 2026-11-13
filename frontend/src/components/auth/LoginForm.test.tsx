import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginForm, destinationAfterLogin } from "./LoginForm";

const loadPage = vi.fn();
const login = vi.fn();

vi.mock("@/lib/navigation", () => ({ loadPage: (url: string) => loadPage(url) }));
vi.mock("@/lib/auth", () => ({ login: (user: string, pw: string) => login(user, pw) }));

beforeEach(() => {
  loadPage.mockReset();
  login.mockReset();
});

describe("destinationAfterLogin", () => {
  it("returns to the requested page only inside the role's own area", () => {
    expect(destinationAfterLogin("coach", "/coach/datasets/x")).toBe("/coach/datasets/x");
    expect(destinationAfterLogin("coach", "/admin")).toBe("/coach");
    expect(destinationAfterLogin("admin", "https://evil.example")).toBe("/admin");
    expect(destinationAfterLogin("admin")).toBe("/admin");
  });
});

describe("LoginForm", () => {
  it("signs in and goes to the role's home", async () => {
    login.mockResolvedValue({ role: "coach", name: "Jeff" });
    render(<LoginForm />);
    const submit = screen.getByRole("button", { name: "Sign in" }) as HTMLButtonElement;
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "jeff" } });
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: " jeff " } });
    fireEvent.click(submit);
    await waitFor(() => expect(loadPage).toHaveBeenCalledWith("/coach"));
    expect(login).toHaveBeenCalledWith("jeff", "jeff");
  });

  it("shows the server's message for a wrong password", async () => {
    login.mockRejectedValue(new Error("That username or password isn't right."));
    render(<LoginForm next="/admin" />);
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect((await screen.findByRole("alert")).textContent).toBe("That username or password isn't right.");
    expect(loadPage).not.toHaveBeenCalled();
  });
});
