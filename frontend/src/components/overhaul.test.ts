import { describe, expect, it } from "vitest";

import type { InventoryItem } from "../api";
import {
  participantLabel,
  visibleOtherSlotCount,
  visualDiceCount,
} from "../viewRules";

describe("overhaul view rules", () => {
  it("renders every actual die in one or two simultaneous attempts", () => {
    expect(visualDiceCount("1d20", "neutral")).toBe(1);
    expect(visualDiceCount("4d6", "neutral")).toBe(4);
    expect(visualDiceCount("3d8+2", "advantage")).toBe(6);
    expect(visualDiceCount("1d20", "disadvantage")).toBe(2);
  });

  it("shows at most one empty other slot after the occupied slots", () => {
    const item = (slot: string): InventoryItem => ({
      id: slot,
      name: slot,
      quantity: 1,
      consumable: false,
      locked: false,
      equipment_slot: slot,
    });
    expect(visibleOtherSlotCount([])).toBe(1);
    expect(visibleOtherSlotCount([item("other_1")])).toBe(2);
    expect(visibleOtherSlotCount([item("other_3")])).toBe(4);
    expect(visibleOtherSlotCount([item("other_4")])).toBe(4);
  });

  it("uses the correct Russian participant form", () => {
    expect(participantLabel(1)).toBe("1 участник");
    expect(participantLabel(2)).toBe("2 участника");
    expect(participantLabel(11)).toBe("11 участников");
    expect(participantLabel(22)).toBe("22 участника");
    expect(participantLabel(25)).toBe("25 участников");
  });
});
