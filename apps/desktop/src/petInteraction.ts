type Point = { x: number; y: number };

export function petDragThresholdReached(start: Point, current: Point): boolean {
  return Math.hypot(current.x - start.x, current.y - start.y) > 6;
}

export function petPointerShouldActivate(
  button: number,
  hasPointerStart: boolean,
  dragged: boolean,
): boolean {
  return button === 0 && hasPointerStart && !dragged;
}
