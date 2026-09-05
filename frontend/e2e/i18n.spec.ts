import { expect, test } from "@playwright/test";

const STORAGE_KEY = "listening-studio.locale";

test.describe("language switching", () => {
  test("defaults to English and switches the whole UI to Japanese", async ({
    page,
  }) => {
    await page.goto("/create");

    await expect(page.getByRole("button", { name: "Save & parse" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Monologue" })).toBeVisible();

    await page.getByRole("button", { name: "日本語" }).click();

    await expect(page.getByRole("button", { name: "保存して解析" })).toBeVisible();
    await expect(page.getByRole("button", { name: "単読" })).toBeVisible();
    await expect(page.getByRole("button", { name: "会話" })).toBeVisible();
    await expect(page.getByText("生成時の話速")).toBeVisible();

    // Accent options come from the API but are labelled from the catalog.
    await expect(
      page.getByRole("option", { name: "イギリス英語" }).first(),
    ).toBeAttached();

    await page.getByRole("button", { name: "English" }).click();
    await expect(page.getByRole("button", { name: "Save & parse" })).toBeVisible();
  });

  test("the choice persists across a reload", async ({ page }) => {
    await page.goto("/create");
    await page.getByRole("button", { name: "日本語" }).click();
    await expect(page.getByRole("button", { name: "保存して解析" })).toBeVisible();

    await page.reload();
    await expect(page.getByRole("button", { name: "保存して解析" })).toBeVisible();

    const stored = await page.evaluate(
      (key) => window.localStorage.getItem(key),
      STORAGE_KEY,
    );
    expect(stored).toBe("ja");
  });

  test("sets the document language for screen readers", async ({ page }) => {
    await page.goto("/create");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");

    await page.getByRole("button", { name: "日本語" }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "ja");
  });

  test("a Japanese browser starts in Japanese without a stored choice", async ({
    browser,
  }) => {
    const context = await browser.newContext({ locale: "ja-JP" });
    const page = await context.newPage();
    await page.goto("/create");

    await expect(page.getByRole("button", { name: "保存して解析" })).toBeVisible();
    await context.close();
  });

  test("the player and project list are localized too", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "日本語" }).click();
    await expect(page.getByRole("link", { name: "新規プロジェクト" })).toBeVisible();

    await page.getByRole("link", { name: "新規プロジェクト" }).click();
    await expect(page.getByText("音声を生成すると再生できます。")).toBeVisible();
  });
});
