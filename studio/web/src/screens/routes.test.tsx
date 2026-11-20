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
  ["/studio/listening", "Listening test"],
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

  it.each([
    ["review", "Nothing to review yet"],
    ["layers", "Nothing to show yet"],
    ["deliver", "Nothing to deliver yet"],
  ])("a running edit's %s tab explains why it's empty and links to Live", async (tab, title) => {
    render(<TestApp api={createMockApi()} path={`/p/cafe-opening-reel/${tab}`} />);
    expect(await screen.findByRole("heading", { name: title }, T)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Watch it live" })).toBeInTheDocument();
  });

  it("deliver creates a review link and can turn it off", async () => {
    const api = createMockApi();
    render(<TestApp api={api} path={`/p/${HOLD}/deliver`} />);
    fireEvent.click(await screen.findByRole("button", { name: "Create review link" }, T));
    const list = await screen.findByRole("list", { name: "Active review links" }, T);
    expect(within(list).getByText(/\/r\/mock/)).toBeInTheDocument();
    const id = (await api.reviewLinks(HOLD)).links[0].id;
    await api.revokeReviewLink(HOLD, id);
    expect((await api.reviewLinks(HOLD)).links[0].state).toBe("revoked");
  });

  it("review explains each failed check in plain words with jump links", async () => {
    render(<TestApp api={createMockApi()} path={`/p/${HOLD}/review`} />);
    const list = await screen.findByRole("list", { name: "What the checks found" }, T);
    expect(within(list).getByText(/speech recogniser was unsure/)).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "Jump to 0:12.40" })).toBeInTheDocument();
    expect(screen.getByText("Details (the engine’s wording)")).toBeInTheDocument();
  });

  it("renames a project and sets its client from the header", async () => {
    const api = createMockApi();
    render(<TestApp api={api} path={`/p/${HOLD}/review`} />);
    fireEvent.click(await screen.findByRole("button", { name: "Rename project or set the client" }, T));
    fireEvent.change(screen.getByRole("textbox", { name: "Project name" }), { target: { value: "Juice myth" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Client" }), { target: { value: "Globex" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("heading", { name: "Juice myth" }, T)).toBeInTheDocument();
    expect((await api.project(HOLD)).client).toBe("Globex");
  });

  it("deliver shows the post copy with a copy button per field", async () => {
    render(<TestApp api={createMockApi()} path={`/p/${HOLD}/deliver`} />);
    expect(await screen.findByText("Instagram caption", undefined, T)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy youtube shorts title" })).toBeInTheDocument();
    expect(screen.getByText(/What would you add\?/)).toBeInTheDocument();
  });

  it("revise shows notes sent through a review link and puts them in the box", async () => {
    render(<TestApp api={createMockApi()} path={`/p/${HOLD}/revise`} />);
    const inbox = await screen.findByRole("region", { name: "From the review link" }, T);
    fireEvent.click(within(inbox).getByRole("button", { name: "Use in the box" }));
    expect((screen.getByRole("textbox", { name: "Paste the client's notes" }) as HTMLTextAreaElement).value).toContain("0:12 spell the brand DearMa");
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

  it("story lines can be dropped in Adjust (C4)", async () => {
    const api = createMockApi();
    const calls: unknown[] = [];
    const orig = api.adjust.bind(api);
    api.adjust = async (id, kind, value) => {
      calls.push([kind, value]);
      return orig(id, kind, value);
    };
    render(<TestApp api={api} path={`/p/${HOLD}/adjust`} />);
    const list = await screen.findByRole("list", { name: "Kept lines in order" }, T);
    const first = within(list).getAllByRole("button", { name: /^Drop / })[0];
    fireEvent.click(first);
    fireEvent.click(screen.getByRole("button", { name: "Apply kept lines" }));
    await screen.findAllByText(/Applied/, undefined, T);
    expect(calls[0]).toEqual(["story_lines", expect.any(Array)]);
    expect((calls[0] as [string, string[]])[1].length).toBeGreaterThan(0);
  });

  it("words can be cut out of a line in Adjust (3a.3)", async () => {
    const api = createMockApi();
    const calls: unknown[] = [];
    const orig = api.adjust.bind(api);
    api.adjust = async (id, kind, value) => {
      calls.push([kind, value]);
      return orig(id, kind, value);
    };
    render(<TestApp api={api} path={`/p/${HOLD}/adjust`} />);
    fireEvent.click(await screen.findByRole("button", { name: "Cut “almost”" }, T));
    fireEvent.click(screen.getByRole("button", { name: "Cut “gave”" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply cut words" }));
    await screen.findAllByText(/Applied/, undefined, T);
    expect(calls[0]).toEqual(["story_words", { item: "k01", remove: [[1, 2]] }]);
  });

  it("the owner picks ours vs the pro blind in the Quality lab (3b.2)", async () => {
    const api = createMockApi();
    render(<TestApp api={api} path="/studio/quality" />);
    expect(await screen.findByText(/2 win · 5 tie · 5 loss/, undefined, T)).toBeInTheDocument();
    expect(screen.getByText(/2 to go/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "A is better" }));
    expect(await screen.findByText(/1 to go/, undefined, T)).toBeInTheDocument();
  });

  it("New edit offers the beauty pass, off by default (3c.1)", async () => {
    render(<TestApp api={createMockApi()} path="/new" />);
    const toggle = await screen.findByRole("switch", { name: /Beauty pass/ }, T).catch(() => screen.findByRole("checkbox", { name: /Beauty pass/ }, T));
    expect(toggle).not.toBeChecked();
  });

  it("a cleared gate can be switched to block in the Quality lab (C3)", async () => {
    const api = createMockApi();
    render(<TestApp api={api} path="/studio/quality" />);
    const frozen = await screen.findByRole("button", { name: /Frozen: warn, switch to block/ }, T);
    fireEvent.click(frozen);
    expect(await screen.findByRole("button", { name: /Frozen: block, switch to warn/ }, T)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Black: warn" })).toBeDisabled(); // not cleared by calibration
  });

  it("New edit shows the client's style and can match a past reel (3a.2)", async () => {
    const api = createMockApi();
    api.clientStyle = async (client) => ({
      client, reels: [{ id: "glow-serum-testimonial", name: "Glow serum testimonial", why: "delivered", has_video: true }],
      profile: { reels: 3, caption_family: "bold_pop", look: "warm", cuts_per_min: 21, length_s: 38, music_mood: "upbeat", hook_title: "card",
                 recurring_settings: [{ kind: "music_gain_db", value: -20, reels: 2 }] },
    });
    render(<TestApp api={api} path="/new" />);
    fireEvent.change(await screen.findByRole("textbox", { name: "Client" }, T), { target: { value: "DearMa" } });
    expect(await screen.findByText(/from 3 approved reels/, undefined, T)).toBeInTheDocument();
    expect(screen.getByText(/always: music gain db -20/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Match a past reel" }), { target: { value: "glow-serum-testimonial" } });
    expect((screen.getByRole("combobox", { name: "Match a past reel" }) as HTMLSelectElement).value).toBe("glow-serum-testimonial");
  });

  it("a story check-in shows the plan and finishes the edit on approval (3a.1)", async () => {
    const api = createMockApi();
    const { id } = await api.createProject({ files: [], name: "Save first", brief: { project: "Save first" } as never, story_checkin: true });
    let sent: unknown = null;
    const orig = api.answerCheckin.bind(api);
    api.answerCheckin = async (pid, yes, note) => {
      sent = { yes, note };
      return orig(pid, yes, note);
    };
    render(<TestApp api={api} path={`/p/${id}/live`} />);
    expect(await screen.findByText("Check the story before the full edit", undefined, T)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: /Open with/ }));
    fireEvent.click(screen.getByRole("button", { name: "Apply and finish the edit" }));
    await screen.findByRole("heading", { name: /Save first/ }, T);
    expect(sent).toEqual({ yes: ["q1"], note: "" });
  });

  it("the listening test renders a set and takes blind votes (G2.5)", async () => {
    const api = createMockApi();
    render(<TestApp api={api} path="/studio/listening" />);
    fireEvent.click(await screen.findByRole("button", { name: "Render the sfx set" }, T));
    expect(await screen.findByText("Pair 1 of 3", undefined, T)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "I’d use B in a client reel" }));
    fireEvent.click(screen.getByRole("button", { name: "B is better" }));
    expect(await screen.findByText("Pair 2 of 3", undefined, T)).toBeInTheDocument();
  });

  it("a long recording shows its Clips board and makes the picked reels (G2.2)", async () => {
    const api = createMockApi();
    const { id } = await api.createProject({ files: [], name: "Podcast ep 4", brief: { project: "Podcast ep 4" } as never, mode: "long" });
    render(<TestApp api={api} path={`/p/${id}/clips`} />);
    expect(await screen.findByText("Reels found in this recording", undefined, T)).toBeInTheDocument();
    expect(screen.getByText(/Editor's estimate|editor's estimate/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review" })).toBeNull(); // a source has no edit of its own
    const pick = screen.getByRole("checkbox", { name: "Pick Pay yourself first, every month" });
    expect(pick).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: /Make 3 reels/ }));
    expect(await screen.findByText("3 reel projects queued", undefined, T)).toBeInTheDocument();
  });
});
