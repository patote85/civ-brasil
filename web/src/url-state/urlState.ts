import type { VisualMode } from "../data";

export type PointsMode = "auto" | "on" | "off";

export interface UrlAppState {
  readonly uf?: string | null;
  readonly lensId: string | null;
  readonly mode: VisualMode | null;
  readonly pointsMode: PointsMode | null;
  readonly cityCd: string | null;
  readonly camX: number | null;
  readonly camY: number | null;
  readonly camZ: number | null;
}

function parseClampedFloat(raw: string | null, min: number, max: number): number | null {
  if (raw === null || raw.trim() === "") return null;
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  return Math.max(min, Math.min(max, n));
}

export function parseUrlState(search: string): UrlAppState {
  const params = new URLSearchParams(search);
  const rawUf = params.get("uf")?.trim().toUpperCase() || null;
  const uf = rawUf && /^[A-Z]{2}$/.test(rawUf) ? rawUf : null;
  const rawLens = params.get("lente")?.trim() || null;
  const rawMode = params.get("modo");
  const mode: VisualMode | null = rawMode === "civ" || rawMode === "atlas" ? rawMode : null;
  const rawPts = params.get("pontos");
  const pointsMode: PointsMode | null =
    rawPts === "auto" || rawPts === "on" || rawPts === "off" ? rawPts : null;
  const rawCity = params.get("cidade")?.trim() || null;
  const cityCd = rawCity && /^\d{7}$/.test(rawCity) ? rawCity : null;

  return {
    uf,
    lensId: rawLens,
    mode,
    pointsMode,
    cityCd,
    camX: parseClampedFloat(params.get("x"), 0, 1000),
    camY: parseClampedFloat(params.get("y"), 0, 700),
    camZ: parseClampedFloat(params.get("z"), 0.75, 7.0),
  };
}

export function serializeUrlState(baseHref: string, state: UrlAppState): string {
  const url = new URL(baseHref);
  if (state.uf && state.uf !== "SP") url.searchParams.set("uf", state.uf);
  else url.searchParams.delete("uf");

  if (state.lensId) url.searchParams.set("lente", state.lensId);
  else url.searchParams.delete("lente");

  if (state.mode && state.mode !== "atlas") url.searchParams.set("modo", state.mode);
  else url.searchParams.delete("modo");

  if (state.pointsMode && state.pointsMode !== "auto") {
    url.searchParams.set("pontos", state.pointsMode);
  } else {
    url.searchParams.delete("pontos");
  }

  if (state.cityCd) url.searchParams.set("cidade", state.cityCd);
  else url.searchParams.delete("cidade");

  if (
    state.camX !== null &&
    state.camY !== null &&
    state.camZ !== null &&
    (Math.abs(state.camX - 500) > 2 || Math.abs(state.camY - 350) > 2 || Math.abs(state.camZ - 1) > 0.05)
  ) {
    url.searchParams.set("x", state.camX.toFixed(1));
    url.searchParams.set("y", state.camY.toFixed(1));
    url.searchParams.set("z", state.camZ.toFixed(2));
  } else {
    url.searchParams.delete("x");
    url.searchParams.delete("y");
    url.searchParams.delete("z");
  }

  return url.toString();
}
