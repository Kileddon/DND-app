import type { DiceRoll, InventoryItem } from "./api";

export const statLabels: Record<string, string> = {
  strength: "Сила",
  dexterity: "Ловкость",
  constitution: "Телосложение",
  intelligence: "Интеллект",
  wisdom: "Мудрость",
  charisma: "Харизма",
};

export function abilityModifier(value: number) {
  const modifier = abilityModifierValue(value);
  return modifier >= 0 ? `+${modifier}` : String(modifier);
}

export function abilityModifierValue(value: number) {
  return Math.floor((value - 10) / 2);
}

export function participantLabel(count: number) {
  const tail = count % 100;
  if (tail >= 11 && tail <= 14) return `${count} участников`;
  if (count % 10 === 1) return `${count} участник`;
  if ([2, 3, 4].includes(count % 10)) return `${count} участника`;
  return `${count} участников`;
}

export function visualDiceCount(
  expression: string,
  selection: DiceRoll["selection"],
) {
  const match = /^(\d*)d(\d+)([+-]\d+)?$/i.exec(expression);
  const count = Number(match?.[1] || 1);
  return count * (selection === "neutral" ? 1 : 2);
}

export function visibleOtherSlotCount(items: InventoryItem[]) {
  const occupied = items.flatMap((item) =>
    item.equipment_slot?.startsWith("other_")
      ? [Number(item.equipment_slot.slice(-1))]
      : [],
  );
  return Math.min(4, Math.max(1, Math.max(0, ...occupied) + 1));
}
