import { expect, test } from "@playwright/test";

test("GM and player complete the local multiplayer slice", async ({
  page,
  browser,
}) => {
  const campaign = `E2E ${Date.now()}`;
  await page.goto("/#/host");
  await page.getByLabel("Название кампании").fill(campaign);
  await page.getByRole("button", { name: "Создать и открыть панель" }).click();
  await expect(page.getByRole("heading", { name: campaign })).toBeVisible();
  await page.getByRole("button", { name: "Новый QR" }).click();
  const shortCode = await page.locator(".pairing strong").innerText();

  const playerContext = await browser.newContext();
  const player = await playerContext.newPage();
  await player.goto("/");
  await player.getByLabel("Короткий код подключения").fill(shortCode);
  await player.getByRole("button", { name: "Подключиться как игрок" }).click();
  await player.getByLabel("Имя за столом").fill("Mira");
  await player.getByRole("button", { name: "Создать профиль" }).click();
  await expect(
    player.getByRole("heading", { name: "Сохраните код восстановления" }),
  ).toBeVisible();
  await player.getByRole("button", { name: "Я сохранил код" }).click();

  await player.getByLabel("Имя нового персонажа").fill("Aria");
  await player
    .getByRole("button", { name: "Начать простой конструктор" })
    .click();
  for (let round = 0; round < 4; round += 1) {
    await player.locator(".ability-card").first().click();
  }
  await player.getByRole("button", { name: "Подтвердить персонажа" }).click();
  await expect(player.getByRole("heading", { name: "Aria" })).toBeVisible();

  await expect(page.getByText("Mira")).toBeVisible();
  await page.getByRole("button", { name: "Новая сессия" }).click();
  await page.getByRole("button", { name: "Открыть лобби" }).click();
  await page.getByRole("button", { name: "Начать игру" }).click();
  await expect(player.getByText("ACTIVE")).toBeVisible();

  await player.getByLabel("Название предмета").fill("Rope");
  await player.getByRole("button", { name: "Добавить" }).click();
  await expect(player.getByText("Rope")).toBeVisible();
  await player.reload();
  await expect(player.getByRole("heading", { name: "Aria" })).toBeVisible();
  await player.getByRole("button", { name: "Удалить 1" }).click();
  await expect(player.getByText("Инвентарь пуст.")).toBeVisible();

  await page.getByRole("button", { name: "Завершить сессию" }).click();
  await expect(page.getByText("Нет активной")).toBeVisible();
  await playerContext.close();
});
