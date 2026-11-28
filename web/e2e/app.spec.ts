import { expect, test } from "@playwright/test";

test("renders SP hex map, switches all lenses with notes, opens City View and Explorer (645 rows)", async ({
  page,
}, testInfo) => {
  const consoleErrors: string[] = [];
  const externalRequests: string[] = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(err.message);
  });
  page.on("request", (req) => {
    const url = req.url();
    if (!url.startsWith("http://127.0.0.1:4173") && !url.startsWith("data:") && !url.startsWith("blob:")) {
      externalRequests.push(url);
    }
  });

  await page.goto("/");
  const canvas = page.locator("#map-canvas");
  await expect(canvas).toBeVisible();
  await expect(page.locator("#status")).toContainText("1091 hexes");

  // Switch across all lenses and verify legend source/year/notes
  const lensBtns = page.locator(".lens-btn");
  const lensCount = await lensBtns.count();
  expect(lensCount).toBeGreaterThanOrEqual(11);

  for (let i = 0; i < lensCount; i++) {
    const btn = lensBtns.nth(i);
    await btn.click();
    await expect(page.locator("#legend")).toContainText("Fonte:");
    await expect(page.locator("#legend")).toContainText("Ano:");
  }

  // Verify sensitive lens mandatory notes
  await page.locator('[data-lens-id="desenvolvimento"]').click();
  await expect(page.locator("#legend")).toContainText("2010");
  await page.locator('[data-lens-id="descontentamento"]').click();
  await expect(page.locator("#legend")).toContainText("subnotificação");

  // Search for São José dos Campos and verify City View opens
  await page.locator("#btn-search").click();
  await page.locator("#search-input").fill("Sao Jose dos Campos");
  const firstResult = page.locator(".search-result-item").first();
  await expect(firstResult).toContainText("São José dos Campos");
  await firstResult.click();

  const cityDrawer = page.locator("#city-drawer");
  await expect(cityDrawer).toBeVisible();
  await expect(cityDrawer).toContainText("São José dos Campos");
  await expect(cityDrawer).toContainText("Aeroespacial");

  if (testInfo.project.name === "desktop-1280x800") {
    await page.screenshot({ path: "../docs/evidencias/pr4/desktop-city-view.png" });
  }
  await page.keyboard.press("Escape");
  await expect(cityDrawer).toBeHidden();

  // Open Explorer and verify 645 rows + 645 scatter points
  await page.locator("#btn-explorer").click();
  const explorerModal = page.locator("#explorer-modal");
  await expect(explorerModal).toBeVisible();
  await expect(page.locator('[data-testid="explorer-row"]')).toHaveCount(645);
  await expect(page.locator('[data-testid="explorer-scatter"]')).toHaveAttribute(
    "data-point-count",
    "645",
  );

  if (testInfo.project.name === "desktop-1280x800") {
    await page.screenshot({ path: "../docs/evidencias/pr4/desktop-explorer.png" });
  } else {
    await page.screenshot({ path: "../docs/evidencias/pr4/mobile-explorer.png" });
  }

  // Filter without accents in Explorer and jump to Campinas
  await page.locator(".explorer-search").fill("campinas");
  await expect(page.locator('[data-testid="explorer-row"]')).toHaveCount(1);
  await page.locator('[data-testid="explorer-row"]').first().click();
  await expect(explorerModal).toBeHidden();
  await expect(cityDrawer).toBeVisible();
  await expect(cityDrawer).toContainText("Campinas");

  // Open Almanac / Fontes modal and verify official sources
  await page.locator("#btn-almanac").click();
  const almanacModal = page.locator("#almanac-modal");
  await expect(almanacModal).toBeVisible();
  await expect(almanacModal).toContainText("IBGE");
  await expect(almanacModal).toContainText("TSE");
  await expect(almanacModal).toContainText("SSP-SP");
  await page.keyboard.press("Escape");
  await expect(almanacModal).toBeHidden();

  expect(externalRequests).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("restores shareable URL state (lens, Civ mode, and City View)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(err.message));

  await page.goto("/?lente=distritos&modo=civ&cidade=3549904");
  await expect(page.locator("#btn-mode")).toHaveText("Modo: Civ");
  await expect(page.locator("#legend")).toContainText("Distritos");
  const cityDrawer = page.locator("#city-drawer");
  await expect(cityDrawer).toBeVisible();
  await expect(cityDrawer).toContainText("São José dos Campos");

  // Default statewide camera must be preserved (no implicit zoom x/y/z injected)
  await page.locator("#btn-share").click();
  const sharedUrl = new URL(page.url());
  expect(sharedUrl.searchParams.get("cidade")).toBe("3549904");
  expect(sharedUrl.searchParams.get("x")).toBeNull();
  expect(sharedUrl.searchParams.get("z")).toBeNull();

  // Rapid second click must not leave the button stuck on a feedback label
  await page.locator("#btn-share").click();
  await expect(page.locator("#btn-share")).toHaveText("Compartilhar", { timeout: 3000 });
  expect(consoleErrors).toEqual([]);
});
