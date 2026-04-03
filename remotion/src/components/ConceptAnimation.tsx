import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  spring,
} from "remotion";
import { Signature } from "./Signature";

interface ConceptAnimationProps {
  concept: "network" | "flow" | "gears" | "growth";
  title: string;
  accent: string;
  backgroundColor: string;
}

/**
 * Concept Animation.
 * Visual metaphors in motion. Draws abstract shapes that represent
 * concepts like networks, data flow, gears, or growth.
 */
export const ConceptAnimation: React.FC<ConceptAnimationProps> = ({
  concept,
  title,
  accent,
  backgroundColor,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Title fade in
  const titleOpacity = interpolate(frame, [fps * 0.5, fps * 1.0], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  // Fade out for loop
  const fadeOut = interpolate(
    frame,
    [durationInFrames - fps * 0.5, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <AbsoluteFill
      style={{
        backgroundColor,
        justifyContent: "center",
        alignItems: "center",
        opacity: fadeOut,
      }}
    >
      {/* Concept visualization */}
      <div style={{ position: "relative", width: 600, height: 600 }}>
        {concept === "network" && <NetworkViz frame={frame} fps={fps} accent={accent} />}
        {concept === "flow" && <FlowViz frame={frame} fps={fps} accent={accent} />}
        {concept === "gears" && <GearsViz frame={frame} fps={fps} accent={accent} />}
        {concept === "growth" && <GrowthViz frame={frame} fps={fps} accent={accent} />}
      </div>

      {/* Title */}
      <div
        style={{
          position: "absolute",
          bottom: 100,
          fontSize: 32,
          fontFamily: "Inter, system-ui, sans-serif",
          fontWeight: 700,
          color: "#ffffff",
          opacity: titleOpacity,
          textAlign: "center",
          maxWidth: 700,
        }}
      >
        {title}
      </div>

      <Signature accent={accent} />
    </AbsoluteFill>
  );
};

// Network: nodes appearing and connecting with lines
const NetworkViz: React.FC<{ frame: number; fps: number; accent: string }> = ({
  frame,
  fps,
  accent,
}) => {
  const nodes = [
    { x: 300, y: 150 },
    { x: 150, y: 300 },
    { x: 450, y: 300 },
    { x: 200, y: 450 },
    { x: 400, y: 450 },
    { x: 300, y: 350 },
  ];

  return (
    <svg width={600} height={600} viewBox="0 0 600 600">
      {/* Connections */}
      {nodes.map((node, i) =>
        nodes.slice(i + 1).map((other, j) => {
          const dist = Math.hypot(node.x - other.x, node.y - other.y);
          if (dist > 250) return null;
          const connectionFrame = frame - (i + j) * fps * 0.2;
          const lineOpacity = interpolate(connectionFrame, [0, fps * 0.3], [0, 0.3], {
            extrapolateRight: "clamp",
            extrapolateLeft: "clamp",
          });
          return (
            <line
              key={`${i}-${j}`}
              x1={node.x}
              y1={node.y}
              x2={other.x}
              y2={other.y}
              stroke={accent}
              strokeWidth={1.5}
              opacity={lineOpacity}
            />
          );
        })
      )}
      {/* Nodes */}
      {nodes.map((node, i) => {
        const nodeScale = spring({
          frame: Math.max(0, frame - i * fps * 0.15),
          fps,
          config: { damping: 10, stiffness: 120, mass: 0.4 },
        });
        return (
          <circle
            key={i}
            cx={node.x}
            cy={node.y}
            r={12 * nodeScale}
            fill={accent}
            opacity={0.8}
          />
        );
      })}
    </svg>
  );
};

// Flow: particles moving along a curved path
const FlowViz: React.FC<{ frame: number; fps: number; accent: string }> = ({
  frame,
  fps,
  accent,
}) => {
  const particles = Array.from({ length: 8 }, (_, i) => {
    const progress = ((frame / fps + i * 0.12) % 1);
    const x = 100 + progress * 400;
    const y = 300 + Math.sin(progress * Math.PI * 2) * 100;
    const opacity = Math.sin(progress * Math.PI);
    return { x, y, opacity };
  });

  return (
    <svg width={600} height={600} viewBox="0 0 600 600">
      <path
        d="M 100 300 Q 300 150 500 300"
        fill="none"
        stroke={accent}
        strokeWidth={1}
        opacity={0.2}
      />
      {particles.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={6} fill={accent} opacity={p.opacity * 0.8} />
      ))}
    </svg>
  );
};

// Gears: rotating circles with teeth
const GearsViz: React.FC<{ frame: number; fps: number; accent: string }> = ({
  frame,
  fps,
  accent,
}) => {
  const rotation = (frame / fps) * 60;

  return (
    <svg width={600} height={600} viewBox="0 0 600 600">
      <g transform={`rotate(${rotation}, 250, 280)`}>
        <circle cx={250} cy={280} r={80} fill="none" stroke={accent} strokeWidth={3} opacity={0.6} />
        <circle cx={250} cy={280} r={60} fill="none" stroke={accent} strokeWidth={2} opacity={0.3} />
      </g>
      <g transform={`rotate(${-rotation * 0.7}, 380, 320)`}>
        <circle cx={380} cy={320} r={55} fill="none" stroke={accent} strokeWidth={3} opacity={0.6} />
        <circle cx={380} cy={320} r={40} fill="none" stroke={accent} strokeWidth={2} opacity={0.3} />
      </g>
    </svg>
  );
};

// Growth: line chart drawing itself
const GrowthViz: React.FC<{ frame: number; fps: number; accent: string }> = ({
  frame,
  fps,
  accent,
}) => {
  const points = [
    [80, 450],
    [180, 420],
    [280, 380],
    [350, 340],
    [400, 250],
    [450, 180],
    [520, 120],
  ];

  const pathData = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p[0]} ${p[1]}`)
    .join(" ");

  const totalLength = 600;
  const drawProgress = interpolate(frame, [fps * 0.3, fps * 2.5], [0, totalLength], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  return (
    <svg width={600} height={600} viewBox="0 0 600 600">
      {/* Grid lines */}
      {[150, 250, 350, 450].map((y) => (
        <line key={y} x1={60} y1={y} x2={540} y2={y} stroke="#ffffff10" strokeWidth={1} />
      ))}
      {/* Growth line */}
      <path
        d={pathData}
        fill="none"
        stroke={accent}
        strokeWidth={3}
        strokeDasharray={totalLength}
        strokeDashoffset={totalLength - drawProgress}
        strokeLinecap="round"
      />
    </svg>
  );
};
