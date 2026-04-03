import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  spring,
} from "remotion";

interface BrandIntroProps {
  accent: string;
  backgroundColor: string;
}

/**
 * Brand intro animation component.
 * A subtle animated "mp" monogram that fades in with a scale spring.
 * Used as the first ~0.5s of every animation for brand recognition.
 */
export const BrandIntro: React.FC<BrandIntroProps> = ({
  accent,
  backgroundColor,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 100, mass: 0.5 },
  });

  const opacity = interpolate(frame, [0, fps * 0.3], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          transform: `scale(${scale})`,
          opacity,
          fontSize: 72,
          fontFamily: "Inter, system-ui, sans-serif",
          fontWeight: 800,
          color: accent,
          letterSpacing: -3,
        }}
      >
        mp
      </div>
    </AbsoluteFill>
  );
};
