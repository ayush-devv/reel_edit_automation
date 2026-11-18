// Generic short-video platform UI and safe-zone overlays, drawn to canvases (used as 3D textures and in
// the flat player). Deliberately generic: no platform logos, names or trademarked icons.
export const OVERLAY_W = 540;
export const OVERLAY_H = 960;

/** Safe area for captions/titles, as fractions of the 9:16 frame (keeps clear of top bar, side actions, caption area). */
export const SAFE = { top: 0.12, bottom: 0.78, left: 0.06, right: 0.8 };

function canvas(): [HTMLCanvasElement, CanvasRenderingContext2D | null] {
  const c = document.createElement("canvas");
  c.width = OVERLAY_W;
  c.height = OVERLAY_H;
  return [c, c.getContext("2d")];
}

export function drawPlatformUI(client = "client"): HTMLCanvasElement {
  const [c, ctx] = canvas();
  if (!ctx) return c;
  const W = OVERLAY_W;
  const H = OVERLAY_H;
  // Bottom scrim for legibility
  const g = ctx.createLinearGradient(0, H * 0.62, 0, H);
  g.addColorStop(0, "rgba(0,0,0,0)");
  g.addColorStop(1, "rgba(0,0,0,0.6)");
  ctx.fillStyle = g;
  ctx.fillRect(0, H * 0.62, W, H * 0.38);

  ctx.strokeStyle = "#fff";
  ctx.fillStyle = "#fff";
  ctx.lineWidth = 3.2;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.font = "600 15px Inter, system-ui, sans-serif";
  ctx.textAlign = "center";

  // Right action column: like, comment, share, more (generic shapes)
  const x = W - 42;
  let y = H * 0.5;
  const label = (t: string) => {
    ctx.fillText(t, x, y + 34);
    y += 82;
  };
  // heart
  ctx.beginPath();
  ctx.moveTo(x, y + 12);
  ctx.bezierCurveTo(x - 22, y - 2, x - 12, y - 18, x, y - 6);
  ctx.bezierCurveTo(x + 12, y - 18, x + 22, y - 2, x, y + 12);
  ctx.stroke();
  label("12.4k");
  // bubble
  ctx.beginPath();
  ctx.ellipse(x, y - 2, 16, 13, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x - 8, y + 9);
  ctx.lineTo(x - 13, y + 17);
  ctx.lineTo(x - 2, y + 11);
  ctx.stroke();
  label("318");
  // share (paper plane-ish arrow)
  ctx.beginPath();
  ctx.moveTo(x - 16, y);
  ctx.lineTo(x + 16, y - 12);
  ctx.lineTo(x + 4, y + 14);
  ctx.lineTo(x - 1, y + 3);
  ctx.closePath();
  ctx.stroke();
  label("1.1k");
  // more
  for (const dx of [-10, 0, 10]) {
    ctx.beginPath();
    ctx.arc(x + dx, y, 2.6, 0, Math.PI * 2);
    ctx.fill();
  }

  // Bottom: avatar, handle, follow pill, caption lines, audio row
  ctx.textAlign = "left";
  const by = H - 150;
  ctx.fillStyle = "#cfc7d8";
  ctx.beginPath();
  ctx.arc(36, by, 17, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#fff";
  ctx.font = "600 17px Inter, system-ui, sans-serif";
  const handle = "@" + client.toLowerCase().replace(/[^a-z0-9]+/g, "");
  ctx.fillText(handle, 64, by + 6);
  const hw = ctx.measureText(handle).width;
  ctx.strokeStyle = "rgba(255,255,255,0.85)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.roundRect(74 + hw, by - 13, 70, 26, 7);
  ctx.stroke();
  ctx.font = "600 14px Inter, system-ui, sans-serif";
  ctx.fillText("Follow", 84 + hw, by + 5);
  ctx.font = "400 16px Inter, system-ui, sans-serif";
  ctx.fillStyle = "rgba(255,255,255,0.92)";
  ctx.fillText("Ten days, one serum. My honest review ✨", 22, by + 44);
  ctx.fillStyle = "rgba(255,255,255,0.7)";
  ctx.fillText("#skincare #routine … more", 22, by + 68);
  ctx.font = "500 14px Inter, system-ui, sans-serif";
  ctx.fillStyle = "rgba(255,255,255,0.85)";
  ctx.fillText("♪  Original audio", 22, by + 100);

  // Top: generic camera glyph
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 2.6;
  ctx.beginPath();
  ctx.roundRect(W - 62, 34, 34, 26, 6);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(W - 45, 47, 7, 0, Math.PI * 2);
  ctx.stroke();
  return c;
}

export function drawSafeZones(): HTMLCanvasElement {
  const [c, ctx] = canvas();
  if (!ctx) return c;
  const W = OVERLAY_W;
  const H = OVERLAY_H;
  const x0 = SAFE.left * W;
  const x1 = SAFE.right * W;
  const y0 = SAFE.top * H;
  const y1 = SAFE.bottom * H;
  // Dim outside the safe area
  ctx.fillStyle = "rgba(54,214,231,0.10)";
  ctx.fillRect(0, 0, W, y0);
  ctx.fillRect(0, y1, W, H - y1);
  ctx.fillRect(0, y0, x0, y1 - y0);
  ctx.fillRect(x1, y0, W - x1, y1 - y0);
  // Soft glowing border
  for (let i = 6; i >= 1; i--) {
    ctx.strokeStyle = `rgba(54,214,231,${0.05 + (6 - i) * 0.05})`;
    ctx.lineWidth = i * 3;
    ctx.beginPath();
    ctx.roundRect(x0, y0, x1 - x0, y1 - y0, 18);
    ctx.stroke();
  }
  ctx.strokeStyle = "#36D6E7";
  ctx.lineWidth = 2;
  ctx.setLineDash([10, 8]);
  ctx.beginPath();
  ctx.roundRect(x0, y0, x1 - x0, y1 - y0, 18);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "#36D6E7";
  ctx.font = "600 15px Inter, system-ui, sans-serif";
  ctx.fillText("SAFE ZONE", x0 + 14, y0 + 26);
  return c;
}
