import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useLargura } from "./useLargura";

function Medidor() {
  const [ref, largura] = useLargura<HTMLDivElement>(640);
  return <div ref={ref}>{largura}</div>;
}

describe("useLargura", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("usa a largura padrão sem ResizeObserver (jsdom)", () => {
    render(<Medidor />);
    expect(screen.getByText("640")).toBeInTheDocument();
  });

  it("acompanha a largura medida e desconecta ao desmontar", () => {
    let callback: ResizeObserverCallback = () => {};
    const disconnect = vi.fn();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(cb: ResizeObserverCallback) {
          callback = cb;
        }
        observe() {}
        disconnect = disconnect;
      },
    );

    const { unmount } = render(<Medidor />);
    const medir = (width: number) =>
      act(() =>
        callback(
          [{ contentRect: { width } } as ResizeObserverEntry],
          {} as ResizeObserver,
        ),
      );

    medir(480.7);
    expect(screen.getByText("480")).toBeInTheDocument();

    medir(0);
    expect(screen.getByText("480")).toBeInTheDocument();

    unmount();
    expect(disconnect).toHaveBeenCalled();
  });
});
