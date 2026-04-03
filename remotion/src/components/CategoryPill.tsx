import React from "react"
import { useCurrentFrame } from "remotion"
import {
  accentColors,
  pillColors,
  fonts,
  fontSizes,
  fontWeights,
  type AccentColor,
} from "../lib/design-tokens"
import { fadeIn, scaleIn } from "../lib/utils"

interface CategoryPillProps {
  label: string
  accent: AccentColor
  startFrame?: number
  variant?: "filled" | "outline" | "dark"
}

/**
 * Category pill label. Used for topic categorization.
 * Filled: colored background, dark text
 * Dark: dark background, white text (like the LinkedIn reference infographics)
 */
export const CategoryPill: React.FC<CategoryPillProps> = ({
  label,
  accent,
  startFrame = 0,
  variant = "filled",
}) => {
  const frame = useCurrentFrame()
  const opacity = fadeIn(frame, startFrame, 6)
  const scale = scaleIn(frame, startFrame, 6, 0.85)

  const styles: Record<string, React.CSSProperties> = {
    filled: {
      backgroundColor: pillColors[accent],
      color: accentColors[accent],
      border: "none",
    },
    outline: {
      backgroundColor: "transparent",
      color: accentColors[accent],
      border: `2px solid ${accentColors[accent]}`,
    },
    dark: {
      backgroundColor: accentColors[accent],
      color: "#ffffff",
      border: "none",
    },
  }

  return (
    <div
      style={{
        opacity,
        transform: `scale(${scale})`,
        display: "inline-flex",
        alignItems: "center",
        padding: "6px 16px",
        borderRadius: 6,
        fontFamily: fonts.body,
        fontSize: fontSizes.sm,
        fontWeight: fontWeights.bold,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        ...styles[variant],
      }}
    >
      {label}
    </div>
  )
}
