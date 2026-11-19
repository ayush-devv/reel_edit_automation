import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TestApp } from "../App";
import { ApiError } from "../api/errors";
import { createMockApi } from "../api/mock/mockApi";

const HOLD = "glow-serum-testimonial";
const FAILED = "podcast-ep12-clip";
const T = { timeout: 4000 };

const ROUTES: [string, RegExp | string][] = [
  ["/", "Projects"],
  ["/new", "New edit"],
  [`/p/cafe-opening-reel/live`, "The Editor’s decisions"],
  [`/p/${HOLD}/review`, "Proof words"],
  [`/p/${HOLD}/layers`, "Story strip"],
  [`/p/${HOLD}/revise`, "Ask for changes"],
  [`/p/${HOLD}/adjust`, "Captions"],
  [`/p/${HOLD}/deliver`, "Extra versions"],
  ["/studio/libraries", "Libraries"],
  ["/studio/brands", "Brand kits"],
  ["/studio/quality", "Quality lab"],
  ["/studio/settings", "Health"],
];

describe("every route renders in mock mode", () => {
  it.each(ROUTES)("%s", async (path, text) => {
    render(<TestApp api={createMockApi()} path={path} />);
    expect(await screen.findByRole("heading", { name: text }, T)).toBeInTheDocument();
  });
});

describe("screens", () => {
  it("home lists projects needs-you first (AC-1)", async () => {
    render(<TestApp api={createMockApi()} path="/" />);
    const list = await screen.findByRole("list", { name: /needs-you first/ }, T);
    const names = within(list)
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(names.slice(0, 3)).toEqual(["Glow serum testimonial", "Podcast ep. 12 — money clip", "Founder story — cut 1"]);
    expect(names.at(-1)).toBe("Gym launch promo");
    expect(screen.getAllByText(/Editing · Story/).length).toBeGreaterThan(0);
  });

  it("first run: one amber action and the three steps, no header New edit", async () => {
    const api = createMockApi();
    api.projects = async () => [];
    render(<TestApp api={api} path="/" />);
    expect(await screen.findByRole("button", { name: "Start your first edit" }, T)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "No edits yet" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New edit" })).toBeNull();
  });

  it("project screens dock the story strip with the reel's beats", async () => {
    render(<TestApp api={createMockApi()} path={`/p/${HOLD}/review`} />);
    const strip = await screen.findByRole("region", { name: "Story strip" }, T);
    expect(within(strip).getByRole("list", { name: /Beats in order/ }).children.length).toBeGreaterThan(0);
  });

  it("shows how to start the engine when it is down (AC-2)", async () => {
    render(<TestApp api={createMockApi({ engineDown: true })} path="/" />);
    expect(await screen.findByRole("heading", { name: "Engine is not running" }, T)).toBeInTheDocument();
    expect(screen.getByText("reel studio --open")).toBeInTheDocument();
  });

  it("failed stage shows the reason and a retry (AC-5)", async () => {
    render(<TestApp api={createMockApi()} path={`/p/${FAILED}/live`} />);
    expect(await screen.findByText(/source file was moved or deleted/, {}, T)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry from Render/ })).toBeInTheDocument();
    // Flat pipeline (no WebGL in tests) is the keyboard-reachable list of stages
    expect(screen.getByRole("button", { name: "Render: failed" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Story: done" })).toBeInTheDocument();
  });

  it("layers fall back to flat tracks and explain a punch-in (AC-8/9)", async () => {
    render(<TestApp api={createMockApi()} path={`/p/${HOLD}/layers`} />);
    const [punch] = await screen.findAllByRole("button", { name: /^Punch-ins: 1\.18×/ }, T);
    fireEvent.click(punch);
    expect(screen.getByText(/Punch-in 1\.18× on “ten days later”/)).toBeInTheDocument();
  });
});

describe("adjust validation display (FR-8, AC-12)", () => {
  it("shows the client-side check instantly and blocks Apply", async () => {
    render(<TestApp api={createMockApi()} path={`/p/${HOLD}/adjust`} />);
    const input = await screen.findByRole("textbox", { name: "Longest pause kept" }, T);
    fireEvent.change(input, { target: { value: "100" } });
    const alert = await screen.findByRole("alert", { name: "Validator issues" });
    expect(alert).toHaveTextContent("Pause limit must be 0 (keep every pause) or between 300 and 3000 ms.");
    expect(alert).toHaveTextContent("Use 400 ms (the default) or 0.");
  });

  it("shows the engine validator's 422 issues after Apply", async () => {
    const api = createMockApi();
    api.adjust = async () => {
      throw new ApiError(422, "invalid", { issues: [{ code: "must_keep", path: "story.items", message: "This removes a must-keep line", fix: "Keep k04 in the story." }] });
    };
    render(<TestApp api={api} path={`/p/${HOLD}/adjust`} />);
    const input = await screen.findByRole("textbox", { name: "Longest pause kept" }, T);
    fireEvent.change(input, { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply longest pause kept" }));
    expect(await screen.findByText("This removes a must-keep line")).toBeInTheDocument();
    expect(screen.getByText("Keep k04 in the story.")).toBeInTheDocument();
  });
});
