import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginForm, destinationAfterLogin } from "./LoginForm";

const replace = vi.fn();
const login = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/lib/auth", () => ({ login: (pw: string) => login(pw) }));

beforeEach(() => {
  replace.mockReset();
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
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/coach"));
    expect(login).toHaveBeenCalledWith("pw");
  });

  it("shows the server's message for a wrong password", async () => {
    login.mockRejectedValue(new Error("That password isn't right."));
    render(<LoginForm next="/admin" />);
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect((await screen.findByRole("alert")).textContent).toBe("That password isn't right.");
    expect(replace).not.toHaveBeenCalled();
  });
});
