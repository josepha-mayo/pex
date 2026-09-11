import pexSheet from "./pex/spritesheet.webp";
import vonSheet from "./von/spritesheet.webp";

const BUNDLED_PET_SHEETS: Readonly<Record<string, string>> = Object.freeze({
  pex: pexSheet,
  von: vonSheet,
});

export function bundledPetSheet(petId?: string | null): string | undefined {
  if (!petId) return undefined;
  return BUNDLED_PET_SHEETS[petId];
}

export const defaultBundledPetSheet = pexSheet;
