import { test, expect } from "@playwright/test";
import fs from "fs";
import path from "path";

const DASH = "http://localhost:5173";
const API = "http://localhost:8000";
const TS = Date.now();
const EMAIL = `screenshot-comprehensive+${TS}@aegis.test`;
const PASSWORD = "ScreenshotPass1!";
const SCREENSHOTS_PATH = path.join("tests", "playwright_tests");

let authToken = "";

test.beforeAll(async ({ request }) => {
  const resp = await request.post(`${API}/api/auth/register`, {
    data: {
      username: EMAIL,
      password: PASSWORD,
      organization_name: `Screenshot Org ${TS}`,
    },
  });
  expect(resp.status(), `register failed: ${await resp.text()}`).toBe(201);
  authToken = (await resp.json()).access_token;

  if (!fs.existsSync(SCREENSHOTS_PATH)) {
    fs.mkdirSync(SCREENSHOTS_PATH, { recursive: true });
  }
});

test.describe("Comprehensive Screenshots", () => {
  test("Login Page", async ({ page }) => {
    test.setTimeout(60000);
    await page.goto(`${DASH}/login`);
    await page.waitForLoadState("networkidle");

    // Screenshot empty login form
    await page.screenshot({
      path: path.join(SCREENSHOTS_PATH, "login_page_empty.png"),
      fullPage: true,
    });

    // Screenshot login form with invalid credentials
    const usernameInput = page.getByRole("textbox", { name: /username/i });
    await usernameInput.waitFor({ state: "visible", timeout: 10000 });
    await usernameInput.fill(EMAIL);
    await page.locator('input[type="password"]').fill("WrongPassword!!");

    // Corrected selector based on the page snapshot
    const signInButton = page.getByRole("button", { name: /enter dashboard/i });
    await signInButton.waitFor({ state: "visible", timeout: 5000 }); // Wait for the button to be visible
    await signInButton.click();

    await page.waitForTimeout(2000); // Wait for error to appear
    await page.screenshot({
      path: path.join(SCREENSHOTS_PATH, "login_page_error.png"),
      fullPage: true,
    });
  });

  test.describe("Authenticated Pages", () => {
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((t) => {
        window.localStorage.setItem("risk_token", t);
      }, authToken);
    });

    test("Overview Page", async ({ page }) => {
      await page.goto(`${DASH}/overview`);
      await page.waitForURL(/\/overview/, { timeout: 10_000 });
      await page.waitForLoadState("networkidle");
      await page.screenshot({
        path: path.join(SCREENSHOTS_PATH, "overview_page.png"),
        fullPage: true,
      });
    });

    for (const p of ["alerts", "events", "models", "settings"]) {
      test(`${p} page`, async ({ page }) => {
        await page.goto(`${DASH}/${p}`);
        await page.waitForLoadState("networkidle");
        await page.screenshot({
          path: path.join(SCREENSHOTS_PATH, `${p}_page.png`),
          fullPage: true,
        });
      });
    }
  });
});
