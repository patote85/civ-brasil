import {
  bucketIndexForValue,
  colorForValue,
  formatPtBrCompact,
  type CityHub,
  type LensMetadata,
  type PointsDataset,
  type PositionalLensData,
  type UfGridDataset,
  type VisualMode,
} from "./data";

export interface CameraState {
  x: number;
  y: number;
  zoom: number;
}

export interface RenderOptions {
  readonly grid: UfGridDataset;
  readonly lensMeta: LensMetadata;
  readonly lensData: PositionalLensData;
  readonly mode: VisualMode;
  readonly showBanners: boolean;
  readonly showPoints: boolean;
  readonly points: PointsDataset | null;
  readonly camera: CameraState;
  readonly hoverIndex: number | null;
  readonly selectedIndex: number | null;
  readonly filterBucket: number | null;
}

export interface MinimapRect {
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
}

export function computeMinimapViewportRect(
  wx0: number,
  wy0: number,
  wx1: number,
  wy1: number,
  mw: number,
  mh: number,
): MinimapRect | null {
  const sx = mw / 1000;
  const sy = mh / 700;
  const x0 = Math.max(0, Math.min(mw, wx0 * sx));
  const y0 = Math.max(0, Math.min(mh, wy0 * sy));
  const x1 = Math.max(0, Math.min(mw, wx1 * sx));
  const y1 = Math.max(0, Math.min(mh, wy1 * sy));
  const w = x1 - x0;
  const h = y1 - y0;
  if (w <= 0 || h <= 0) return null;
  return { x: x0, y: y0, w, h };
}

export class HexMapRenderer {
  private readonly canvas: HTMLCanvasElement;
  private readonly ctx: CanvasRenderingContext2D;
  private readonly minimap: HTMLCanvasElement;
  private readonly mctx: CanvasRenderingContext2D;

  constructor(canvas: HTMLCanvasElement, minimap: HTMLCanvasElement) {
    this.canvas = canvas;
    const ctx = canvas.getContext("2d");
    const mctx = minimap.getContext("2d");
    if (!ctx || !mctx) {
      throw new Error("Contexto Canvas 2D indisponível");
    }
    this.ctx = ctx;
    this.minimap = minimap;
    this.mctx = mctx;
  }

  public resize(): void {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    const w = Math.max(1, Math.floor(rect.width));
    const h = Math.max(1, Math.floor(rect.height));
    this.canvas.width = Math.floor(w * dpr);
    this.canvas.height = Math.floor(h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  public worldToScreen(wx: number, wy: number, camera: CameraState): [number, number, number] {
    const w = this.canvas.clientWidth || 1;
    const h = this.canvas.clientHeight || 1;
    const baseScale = Math.min(w / 1000, h / 700) * 0.94;
    const s = baseScale * camera.zoom;
    return [(wx - camera.x) * s + w / 2, (wy - camera.y) * s + h / 2, s];
  }

  public screenToWorld(sx: number, sy: number, camera: CameraState): [number, number] {
    const w = this.canvas.clientWidth || 1;
    const h = this.canvas.clientHeight || 1;
    const baseScale = Math.min(w / 1000, h / 700) * 0.94;
    const s = baseScale * camera.zoom;
    return [(sx - w / 2) / s + camera.x, (sy - h / 2) / s + camera.y];
  }

  public pickHex(sx: number, sy: number, grid: UfGridDataset, camera: CameraState): number | null {
    const [wx, wy] = this.screenToWorld(sx, sy, camera);
    let bestIdx: number | null = null;
    let bestDist = 11.5;
    for (let i = 0; i < grid.hex_count; i++) {
      const cx = grid.cx[i];
      const cy = grid.cy[i];
      if (cx === undefined || cy === undefined) continue;
      const dist = Math.hypot(wx - cx, wy - cy);
      if (dist < bestDist) {
        bestDist = dist;
        bestIdx = i;
      }
    }
    return bestIdx;
  }

  public pickHubAtScreen(
    sx: number,
    sy: number,
    grid: UfGridDataset,
    camera: CameraState,
  ): CityHub | null {
    const { ctx } = this;
    ctx.save();
    ctx.font = "600 11px system-ui, -apple-system, sans-serif";
    for (let i = grid.hubs.length - 1; i >= 0; i--) {
      const hub = grid.hubs[i];
      if (!hub) continue;
      const [bx, by] = this.worldToScreen(hub.x, hub.y, camera);
      const popLabel = formatPtBrCompact(hub.pop, "habitantes");
      const popW = ctx.measureText(popLabel).width + 10;
      const nameW = ctx.measureText(hub.nome).width + 12;
      const totalW = popW + nameW;
      const rx = bx - totalW / 2;
      const ry = by - 24;
      const rh = 18;
      if (sx >= rx && sx <= rx + totalW && sy >= ry && sy <= ry + rh) {
        ctx.restore();
        return hub;
      }
      if (Math.hypot(sx - bx, sy - by) <= 8) {
        ctx.restore();
        return hub;
      }
    }
    ctx.restore();
    return null;
  }

  public render(opts: RenderOptions): number {
    const t0 = performance.now();
    const { ctx } = this;
    const w = this.canvas.clientWidth || 1;
    const h = this.canvas.clientHeight || 1;
    const {
      grid,
      lensMeta,
      lensData,
      mode,
      showBanners,
      showPoints,
      points,
      camera,
      hoverIndex,
      selectedIndex,
      filterBucket,
    } = opts;

    if (mode === "civ") {
      const grad = ctx.createRadialGradient(w * 0.55, h * 0.5, 40, w * 0.5, h * 0.5, Math.max(w, h) * 0.78);
      grad.addColorStop(0, "#152b3c");
      grad.addColorStop(1, "#091521");
      ctx.fillStyle = grad;
    } else {
      ctx.fillStyle = "#0a1019";
    }
    ctx.fillRect(0, 0, w, h);

    ctx.save();
    ctx.strokeStyle = "rgba(148, 184, 218, 0.06)";
    ctx.lineWidth = 1;
    for (let gx = 0; gx <= 1000; gx += 125) {
      const [sx] = this.worldToScreen(gx, 0, camera);
      ctx.beginPath();
      ctx.moveTo(sx, 0);
      ctx.lineTo(sx, h);
      ctx.stroke();
    }
    for (let gy = 0; gy <= 700; gy += 125) {
      const [, sy] = this.worldToScreen(0, gy, camera);
      ctx.beginPath();
      ctx.moveTo(0, sy);
      ctx.lineTo(w, sy);
      ctx.stroke();
    }
    ctx.restore();

    const [, , scale] = this.worldToScreen(0, 0, camera);
    const offsets = grid.hex_offsets;

    for (let i = 0; i < grid.hex_count; i++) {
      const cx = grid.cx[i];
      const cy = grid.cy[i];
      if (cx === undefined || cy === undefined) continue;
      const [sx, sy] = this.worldToScreen(cx, cy, camera);
      if (sx < -32 || sx > w + 32 || sy < -32 || sy > h + 32) continue;

      const value = lensData.values[i] ?? null;
      const bucket = bucketIndexForValue(value, lensData.breaks);
      const dimmed = filterBucket !== null && bucket !== filterBucket;

      this.traceHex(ctx, sx, sy, scale * 1.015, offsets);
      ctx.fillStyle = colorForValue(value, lensData.breaks, lensMeta.palette, mode);
      ctx.globalAlpha = dimmed ? 0.16 : 0.94;
      ctx.fill();

      ctx.globalAlpha = dimmed ? 0.12 : 1;
      ctx.lineWidth = Math.max(0.6, 0.75 * Math.min(scale, 1.8));
      ctx.strokeStyle = mode === "civ" ? "rgba(24, 20, 14, 0.45)" : "rgba(16, 26, 38, 0.8)";
      ctx.stroke();

      if (hoverIndex === i || selectedIndex === i) {
        ctx.globalAlpha = 1;
        this.traceHex(ctx, sx, sy, scale * 1.03, offsets);
        ctx.lineWidth = 2.4;
        ctx.strokeStyle = selectedIndex === i ? "#facc15" : "#ffffff";
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;

    if (showPoints && points) {
      this.drawPoints(ctx, points, lensMeta.id, camera, w, h);
    }

    if (showBanners && grid.hubs.length > 0) {
      this.drawHubs(ctx, grid, camera, mode, w, h);
    }

    this.drawMinimap(grid, camera, mode);
    return performance.now() - t0;
  }

  public exportPngDataUrl(lensMeta: LensMetadata, grid: UfGridDataset): string {
    const off = document.createElement("canvas");
    off.width = 1600;
    off.height = 900;
    const octx = off.getContext("2d");
    if (!octx) {
      throw new Error("Falha ao criar canvas de exportação PNG");
    }
    octx.fillStyle = "#0a1019";
    octx.fillRect(0, 0, 1600, 900);
    octx.drawImage(this.canvas, 0, 0, 1600, 900);
    octx.fillStyle = "rgba(10, 16, 25, 0.86)";
    octx.fillRect(24, 836, 760, 40);
    octx.fillStyle = "#f8fafc";
    octx.font = "600 18px system-ui, sans-serif";
    octx.fillText(
      `civ-brasil · ${grid.uf} · ${lensMeta.civ_name} (${lensMeta.br_name}) · ${lensMeta.source_label} (${lensMeta.ano_ref})`,
      38,
      862,
    );
    return off.toDataURL("image/png");
  }

  private traceHex(
    ctx: CanvasRenderingContext2D,
    sx: number,
    sy: number,
    scale: number,
    offsets: readonly (readonly [number, number])[],
  ): void {
    ctx.beginPath();
    for (let i = 0; i < offsets.length; i++) {
      const pair = offsets[i];
      if (!pair) continue;
      const vx = sx + pair[0] * scale;
      const vy = sy + pair[1] * scale;
      if (i === 0) ctx.moveTo(vx, vy);
      else ctx.lineTo(vx, vy);
    }
    ctx.closePath();
  }

  private drawPoints(
    ctx: CanvasRenderingContext2D,
    points: PointsDataset,
    lensId: string,
    camera: CameraState,
    w: number,
    h: number,
  ): void {
    ctx.save();
    const showHosp = lensId === "saude";
    const showEnergyAndPorts = lensId !== "saude";

    if (showEnergyAndPorts) {
      ctx.fillStyle = "#facc15";
      ctx.strokeStyle = "#0a1019";
      ctx.lineWidth = 1;
      for (const u of points.usinas) {
        const [sx, sy] = this.worldToScreen(u.x, u.y, camera);
        if (sx < -16 || sx > w + 16 || sy < -16 || sy > h + 16) continue;
        const r = Math.max(2.6, Math.min(7.5, 2.2 + Math.log10(Math.max(1, u.val)) * 1.4));
        ctx.beginPath();
        ctx.moveTo(sx, sy - r);
        ctx.lineTo(sx + r * 0.9, sy + r * 0.8);
        ctx.lineTo(sx - r * 0.9, sy + r * 0.8);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }

      ctx.fillStyle = "#22d3ee";
      ctx.strokeStyle = "#0a1019";
      ctx.lineWidth = 1.2;
      for (const p of points.portos) {
        const [sx, sy] = this.worldToScreen(p.x, p.y, camera);
        if (sx < -16 || sx > w + 16 || sy < -16 || sy > h + 16) continue;
        const r = 5.5;
        ctx.beginPath();
        ctx.moveTo(sx, sy - r);
        ctx.lineTo(sx + r, sy);
        ctx.lineTo(sx, sy + r);
        ctx.lineTo(sx - r, sy);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
    }

    if (showHosp) {
      ctx.fillStyle = "#fb7185";
      ctx.strokeStyle = "#0a1019";
      ctx.lineWidth = 0.9;
      for (const hosp of points.hospitais) {
        const [sx, sy] = this.worldToScreen(hosp.x, hosp.y, camera);
        if (sx < -12 || sx > w + 12 || sy < -12 || sy > h + 12) continue;
        const r = Math.max(2.2, Math.min(6.0, 2.0 + Math.log10(Math.max(1, hosp.val)) * 1.2));
        ctx.beginPath();
        ctx.arc(sx, sy, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  private drawHubs(
    ctx: CanvasRenderingContext2D,
    grid: UfGridDataset,
    camera: CameraState,
    mode: VisualMode,
    w: number,
    h: number,
  ): void {
    ctx.save();
    ctx.font = "600 11px system-ui, -apple-system, sans-serif";
    for (const hub of grid.hubs) {
      const [bx, by] = this.worldToScreen(hub.x, hub.y, camera);
      if (bx < -80 || bx > w + 80 || by < -40 || by > h + 40) continue;

      ctx.beginPath();
      ctx.arc(bx, by, 3.8, 0, Math.PI * 2);
      ctx.fillStyle = mode === "civ" ? "#fbbf24" : "#38bdf8";
      ctx.fill();
      ctx.lineWidth = 1.4;
      ctx.strokeStyle = "#0a1019";
      ctx.stroke();

      const popLabel = formatPtBrCompact(hub.pop, "habitantes");
      const popW = ctx.measureText(popLabel).width + 10;
      const nameW = ctx.measureText(hub.nome).width + 12;
      const totalW = popW + nameW;
      const rx = bx - totalW / 2;
      const ry = by - 24;
      const rh = 18;

      ctx.fillStyle = mode === "civ" ? "rgba(28, 22, 16, 0.90)" : "rgba(15, 23, 42, 0.88)";
      ctx.strokeStyle = mode === "civ" ? "#d4a226" : "#475569";
      ctx.lineWidth = 1;
      ctx.fillRect(rx, ry, totalW, rh);
      ctx.strokeRect(rx, ry, totalW, rh);

      ctx.fillStyle = mode === "civ" ? "#d4a226" : "#0284c7";
      ctx.fillRect(rx, ry, popW, rh);

      ctx.fillStyle = mode === "civ" ? "#111827" : "#f8fafc";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(popLabel, rx + popW / 2, ry + rh / 2 + 0.5);

      ctx.fillStyle = "#f8fafc";
      ctx.fillText(hub.nome, rx + popW + nameW / 2, ry + rh / 2 + 0.5);
    }
    ctx.restore();
  }

  private drawMinimap(grid: UfGridDataset, camera: CameraState, mode: VisualMode): void {
    const mw = this.minimap.width;
    const mh = this.minimap.height;
    const { mctx } = this;
    mctx.fillStyle = "#0b1422";
    mctx.fillRect(0, 0, mw, mh);

    const sx = mw / 1000;
    const sy = mh / 700;
    mctx.fillStyle = mode === "civ" ? "#65a35c" : "#38bdf8";
    for (let i = 0; i < grid.hex_count; i++) {
      const cx = grid.cx[i];
      const cy = grid.cy[i];
      if (cx === undefined || cy === undefined) continue;
      mctx.fillRect(cx * sx, cy * sy, 1.8, 1.8);
    }

    const [wx0, wy0] = this.screenToWorld(0, 0, camera);
    const [wx1, wy1] = this.screenToWorld(this.canvas.clientWidth, this.canvas.clientHeight, camera);
    const rect = computeMinimapViewportRect(wx0, wy0, wx1, wy1, mw, mh);
    if (rect) {
      mctx.strokeStyle = "#facc15";
      mctx.lineWidth = 1.4;
      mctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
    }
  }
}
