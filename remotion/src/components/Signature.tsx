import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface SignatureProps {
  accent?: string;
}

/**
 * Animated signature overlay.
 * A subtle "mindpattern" text that slides in at the bottom-right corner.
 * Layered on top of every composition for brand recognition.
 */
export const Signature: React.FC<SignatureProps> = ({
  accent = "#e94560",
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Slide in from right during first 0.5s
  const slideIn = interpolate(frame, [0, fps * 0.5], [40, 0], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  // Fade in
  const opacity = interpolate(frame, [0, fps * 0.4], [0, 0.6], {
    extrapolateRight: "clamp",
  });

  // Fade out in last 0.3s for seamless loop
  const fadeOut = interpolate(
    frame,
    [durationInFrames - fps * 0.3, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          bottom: 32,
          right: 32,
          transform: `translateX(${slideIn}px)`,
          opacity: opacity * fadeOut,
          fontSize: 14,
          fontFamily: "Inter, system-ui, sans-serif",
          fontWeight: 600,
          color: accent,
          letterSpacing: 2,
          textTransform: "uppercase",
        }}
      >
        mindpattern
      </div>
    </AbsoluteFill>
  );
};
