import { expect, test } from "@playwright/test";

test("GM and player complete the local multiplayer slice", async ({
  page,
  browser,
}) => {
  const campaign = `E2E ${Date.now()}`;
  await page.goto("/");
  await page.getByRole("link", { name: "Создать комнату" }).click();
  await expect(
    page.getByRole("heading", { name: "Создать комнату" }),
  ).toBeVisible();
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

  await page.getByRole("button", { name: "Создать бой" }).click();
  await expect(page.getByRole("heading", { name: "Раунд 0" })).toBeVisible();
  await page
    .getByRole("button", { name: "Добавить выбранных персонажей" })
    .click();
  await expect(
    page.locator(".initiative-list").getByText("Aria", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Имя монстра").fill("Гоблин");
  await page.getByLabel("HP монстра").fill("10");
  await page.getByLabel("Количество монстров").fill("2");
  await page.getByRole("button", { name: "Добавить монстров" }).click();
  await expect(page.getByText("Группа: 2")).toBeVisible();
  await page.getByRole("button", { name: "Начать бой" }).click();
  await expect(player.getByRole("heading", { name: "Раунд 1" })).toBeVisible();

  await page.locator(".target").filter({ hasText: "Гоблин 1" }).click();
  await page.getByLabel("Величина эффекта").fill("6");
  await page.getByRole("button", { name: "Урон" }).click();
  await expect(
    player.getByText("ранен", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Следующий ход" }).click();
  await player.getByLabel("Формула броска").fill("1d20+2");
  await player.getByRole("button", { name: "Бросить" }).click();
  await player.getByLabel("Заявка поддержки").fill("Отвлекаю второго гоблина");
  await player.getByRole("button", { name: "Предложить поддержку" }).click();
  await expect(page.getByText("Заявка поддержки")).toBeVisible();
  await page.getByRole("button", { name: "Завершить бой" }).click();
  await expect(
    page.getByText("БОЙ · COMPLETED", { exact: true }),
  ).toBeVisible();

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
