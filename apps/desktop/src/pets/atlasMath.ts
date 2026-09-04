export function animationFrameIndex(frame: number, frameCount: number): number {
  if (!Number.isFinite(frame) || !Number.isFinite(frameCount) || frameCount < 1) return 0;
  const count = Math.trunc(frameCount);
  const value = Math.trunc(frame) % count;
  return value < 0 ? value + count : value;
}
