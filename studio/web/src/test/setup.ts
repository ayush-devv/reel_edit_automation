import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
});

// jsdom gaps: matchMedia, EventSource, ResizeObserver, canvas 2D/WebGL, <dialog>, scrolling.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
});

class FakeEventSource extends EventTarget {
  url: string;
  readyState = 0;
  constructor(url: string) {
    super();
    this.url = url;
  }
  close() {
    this.readyState = 2;
  }
}
Object.defineProperty(globalThis, "EventSource", { writable: true, value: FakeEventSource });

class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
Object.defineProperty(globalThis, "ResizeObserver", { writable: true, value: FakeResizeObserver });

// No canvas backend in jsdom: report no context (so WebGL is "unavailable" and 2D drawing is skipped).
HTMLCanvasElement.prototype.getContext = vi.fn(() => null) as unknown as HTMLCanvasElement["getContext"];

if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
}
Element.prototype.scrollTo = function () {} as Element["scrollTo"];
Element.prototype.scrollIntoView = function () {};
