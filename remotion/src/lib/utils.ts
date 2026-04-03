/**
 * Animation utilities for MindPattern Remotion compositions.
 * Ported from Rayni's utils.ts with adjustments for GIF timing.
 */
import { interpolate, Easing } from "remotion"

/**
 * Fade in animation helper
 */
export function fadeIn(
  frame: number,
  startFrame: number,
  duration: number = 8
): number {
  return interpolate(frame, [startFrame, startFrame + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })
}

/**
 * Slide up animation helper (returns Y offset)
 */
export function slideUp(
  frame: number,
  startFrame: number,
  duration: number = 8,
  distance: number = 30
): number {
  return interpolate(frame, [startFrame, startFrame + duration], [distance, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })
}

/**
 * Slide in from left (returns X offset)
 */
export function slideInLeft(
  frame: number,
  startFrame: number,
  duration: number = 8,
  distance: number = 40
): number {
  return interpolate(frame, [startFrame, startFrame + duration], [-distance, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })
}

/**
 * Slide in from right (returns X offset)
 */
export function slideInRight(
  frame: number,
  startFrame: number,
  duration: number = 8,
  distance: number = 40
): number {
  return interpolate(frame, [startFrame, startFrame + duration], [distance, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })
}

/**
 * Scale animation helper
 */
export function scaleIn(
  frame: number,
  startFrame: number,
  duration: number = 8,
  startScale: number = 0.92
): number {
  return interpolate(
    frame,
    [startFrame, startFrame + duration],
    [startScale, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.back(1.1)),
    }
  )
}

/**
 * Fade out for seamless GIF loop
 */
export function fadeOut(
  frame: number,
  totalFrames: number,
  duration: number = 6
): number {
  return interpolate(frame, [totalFrames - duration, totalFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.in(Easing.cubic),
  })
}

/**
 * Count up animation for numbers
 */
export function countUp(
  frame: number,
  startFrame: number,
  duration: number = 15,
  target: number
): number {
  const progress = interpolate(
    frame,
    [startFrame, startFrame + duration],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    }
  )
  return Math.round(progress * target)
}

/**
 * Wipe reveal (horizontal, left to right)
 */
export function wipeReveal(
  frame: number,
  startFrame: number,
  duration: number = 10
): number {
  return interpolate(
    frame,
    [startFrame, startFrame + duration],
    [0, 100],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    }
  )
}

/**
 * Combined entrance animation (fade + slide + scale)
 */
export function entrance(
  frame: number,
  startFrame: number,
  duration: number = 10
) {
  return {
    opacity: fadeIn(frame, startFrame, duration),
    translateY: slideUp(frame, startFrame, duration),
    scale: scaleIn(frame, startFrame, duration),
  }
}
