import React from "react"
import { useCurrentFrame, interpolate, Easing } from "remotion"
import { colors, glowColors, type AccentColor } from "../lib/design-tokens"

interface GradientBackgroundProps {
  accent: AccentColor
  children: React.ReactNode
}

/**
 * Animated gradient background with floating orbs.
 * Light bg with subtle colored glow that shifts.
 * Ported from Rayni's GradientBackground.
 */
export const GradientBackground: React.FC<GradientBackgroundProps> = ({
  accent,
  children,
}) => {
  const frame = useCurrentFrame()

  const float1 = interpolate(frame % 90, [0, 45, 90], [0, 6, 0], {
    easing: Easing.inOut(Easing.sin),
  })
  const float2 = interpolate(frame % 100, [0, 50, 100], [0, -8, 0], {
    easing: Easing.inOut(Easing.sin),
  })

  const glowColor = glowColors[accent]

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        backgroundColor: colors.bg,
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Top-right glow orb */}
      <div
        style={{
          position: "absolute",
          top: -150 + float1,
          right: -150,
          width: 500,
          height: 500,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${glowColor} 0%, transparent 60%)`,
          filter: "blur(80px)",
          opacity: 0.7,
        }}
      />
      {/* Bottom-left glow orb */}
      <div
        style={{
          position: "absolute",
          bottom: -100 + float2,
          left: -100,
          width: 400,
          height: 400,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${glowColor} 0%, transparent 60%)`,
          filter: "blur(100px)",
          opacity: 0.5,
        }}
      />
      <div style={{ position: "relative", zIndex: 1, width: "100%", height: "100%" }}>
        {children}
      </div>
    </div>
  )
}
