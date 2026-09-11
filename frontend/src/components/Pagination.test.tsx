import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { Pagination } from "./Pagination";

it("clamps ranges and requests adjacent pages", () => {
  const setOffset = vi.fn();
  const { rerender } = render(
    <Pagination data={{ offset: 100, limit: 100, total: 250, setOffset }} />,
  );

  expect(screen.getByText("101-200 / 250")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Previous" }));
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(setOffset.mock.calls).toEqual([[0], [200]]);

  rerender(<Pagination data={{ offset: 200, limit: 100, total: 200, setOffset }} />);
  expect(screen.getByText("200-200 / 200")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(true);
});
