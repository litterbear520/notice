import type { CSSProperties } from "react";

// Fable 5 主题：复古博物志蝴蝶（参照官方发布视觉——蝴蝶标本拼成的"5"）
// 翅膀几何画在 x>0 的右半侧，左半侧用 scale(-1,1) 镜像

export type ButterflyTone = "coral" | "gold" | "ink" | "sage";

function WingHalf() {
  return (
    <g className="flap">
      <path
        className="fw"
        d="M1,-1.5 C3.5,-8 10,-12.8 15.5,-11 C19.5,-9.6 18.6,-4.4 14,-1.8 C10,0.4 4.5,0.8 1,0.2 Z"
      />
      <path
        className="hw"
        d="M1,1 C4.5,0.8 8.8,2.4 9.8,5.8 C10.6,8.8 8,11.4 5,10.2 C2.6,9.2 1.2,5.8 0.8,2.6 Z"
      />
      <circle className="spot" cx="12.6" cy="-6.6" r="1.5" />
    </g>
  );
}

interface BflyProps {
  x?: number;
  y?: number;
  rotate?: number;
  scale?: number;
  tone?: ButterflyTone;
  delay?: number;
}

export function BflyGroup({ x = 0, y = 0, rotate = 0, scale = 1, tone = "coral", delay = 0 }: BflyProps) {
  return (
    <g
      className={`bfly bfly-${tone}`}
      transform={`translate(${x} ${y}) rotate(${rotate}) scale(${scale})`}
      style={{ "--d": `${delay}s` } as CSSProperties}
    >
      <g className="drift">
        <WingHalf />
        <g transform="scale(-1 1)">
          <WingHalf />
        </g>
        <ellipse className="body-seg" cx="0" cy="1.2" rx="1.05" ry="4.4" />
        <circle className="body-seg" cx="0" cy="-3.4" r="1.3" />
        <path className="feeler" d="M-0.7,-4.4 C-1.6,-7.4 -3.4,-9.4 -5.2,-10.4" />
        <path className="feeler" d="M0.7,-4.4 C1.6,-7.4 3.4,-9.4 5.2,-10.4" />
        <circle className="body-seg" cx="-5.4" cy="-10.6" r="0.6" />
        <circle className="body-seg" cx="5.4" cy="-10.6" r="0.6" />
      </g>
    </g>
  );
}

export function Butterfly({ size = 18, tone = "coral", className }: { size?: number; tone?: ButterflyTone; className?: string }) {
  return (
    <svg
      className={className}
      width={size}
      height={Math.round(size * 0.7)}
      viewBox="-20 -14 40 28"
      aria-hidden="true"
    >
      <BflyGroup tone={tone} />
    </svg>
  );
}

// 首页时间线上方的装饰带：五只蝴蝶沿虚线轨迹蜿蜒飞行（呼应 Fable 5）
export function FableFlight() {
  return (
    <svg className="fable-flight" viewBox="0 0 520 110" aria-hidden="true">
      <path
        className="flight-path"
        d="M6,98 C70,52 118,110 190,80 C262,50 292,104 356,68 C408,38 448,52 508,18"
      />
      <BflyGroup x={46} y={78} rotate={-18} scale={0.5} tone="ink" delay={1.1} />
      <BflyGroup x={140} y={92} rotate={12} scale={0.62} tone="gold" delay={0.4} />
      <BflyGroup x={238} y={68} rotate={-8} scale={0.8} tone="sage" delay={1.8} />
      <BflyGroup x={344} y={80} rotate={16} scale={0.66} tone="gold" delay={0.9} />
      <BflyGroup x={462} y={36} rotate={-12} scale={1.12} tone="coral" delay={0} />
    </svg>
  );
}
