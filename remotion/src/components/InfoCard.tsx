import React from "react"
import { useCurrentFrame } from "remotion"
import {
  colors,
  accentColors,
  fonts,
  fontSizes,
  fontWeights,
  type AccentColor,
} from "../lib/design-tokens"
import { fadeIn, slideUp, slideInLeft, slideInRight } from "../lib/utils"

interface InfoCardProps {
  title: string
  items: string[]
  accent: AccentColor
  startFrame?: number
  direction?: "left" | "right" | "up"
  showIcons?: boolean
}

/**
 * Information card with category color bar and staggered item list.
 * The building block for infographic-style compositions.
 */
export const InfoCard: React.FC<InfoCardProps> = ({
  title,
  items,
  accent,
  startFrame = 0,
  direction = "up",
  showIcons = true,
}) => {
  const frame = useCurrentFrame()

  const cardOpacity = fadeIn(frame, startFrame, 8)
  const cardSlide =
    direction === "left"
      ? slideInLeft(frame, startFrame, 8, 30)
      : direction === "right"
        ? slideInRight(frame, startFrame, 8, 30)
        : slideUp(frame, startFrame, 8, 20)

  const transform =
    direction === "up"
      ? `translateY(${cardSlide}px)`
      : `translateX(${cardSlide}px)`

  return (
    <div
      style={{
        opacity: cardOpacity,
        transform,
        backgroundColor: colors.white,
        borderRadius: 10,
        border: `1px solid ${colors.cardBorder}`,
        overflow: "hidden",
        boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
      }}
    >
      {/* Color accent bar at top */}
      <div
        style={{
          height: 4,
          backgroundColor: accentColors[accent],
        }}
      />

      <div style={{ padding: "16px 20px" }}>
        {/* Title */}
        <div
          style={{
            fontFamily: fonts.display,
            fontSize: fontSizes.base,
            fontWeight: fontWeights.bold,
            color: colors.text,
            marginBottom: 12,
            letterSpacing: "-0.01em",
          }}
        >
          {title}
        </div>

        {/* Items */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {items.map((item, i) => {
            const itemStart = startFrame + 4 + i * 3
            const itemOpacity = fadeIn(frame, itemStart, 6)
            const itemSlide = slideUp(frame, itemStart, 6, 12)

            return (
              <div
                key={i}
                style={{
                  opacity: itemOpacity,
                  transform: `translateY(${itemSlide}px)`,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                {showIcons && (
                  <div
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      backgroundColor: accentColors[accent],
                      flexShrink: 0,
                    }}
                  />
                )}
                <span
                  style={{
                    fontFamily: fonts.body,
                    fontSize: fontSizes.sm,
                    color: colors.textBody,
                    lineHeight: 1.4,
                  }}
                >
                  {item}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
