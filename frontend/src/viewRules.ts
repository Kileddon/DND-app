import type { DiceRoll, InventoryItem } from "./api";

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
