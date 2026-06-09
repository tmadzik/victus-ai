'use client';

import type { CalibrationStatsBlock } from '@victus/contracts';

/**
 * Canonical Bland-Altman scatter rendered as a dependency-free inline SVG.
 *
 * X-axis: mean of paired values  (rppg + ref) / 2
 * Y-axis: difference             rppg - ref
 * Horizontal lines:
 *   solid     bias
 *   dashed    bias + 1.96 σ  (upper LoA)
 *   dashed    bias − 1.96 σ  (lower LoA)
 *
 * The plot scales to fit the data window with a small padding margin; if
 * fewer than 2 pairs are available the caller should not render this
 * component (the StatsPanel handles that gating).
 */
export function BlandAltmanChart({
  stats,
}: {
  stats: CalibrationStatsBlock;
}): React.ReactElement {
  const width = 640;
  const height = 360;
  const margin = { top: 24, right: 32, bottom: 48, left: 56 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const xs = stats.means;
  const ys = stats.differences;
  const xMin = Math.min(...xs, stats.ref_min - 5);
  const xMax = Math.max(...xs, stats.ref_max + 5);
  // Y bounds incorporate the LoA band so the dashed lines are always in view.
  const yPadding = Math.max(
    Math.abs(stats.loa_upper_bpm),
    Math.abs(stats.loa_lower_bpm),
    Math.max(...ys.map((d) => Math.abs(d))),
  ) * 0.15;
  const yLo = Math.min(stats.loa_lower_bpm - yPadding, ...ys) - 1;
  const yHi = Math.max(stats.loa_upper_bpm + yPadding, ...ys) + 1;

  const xScale = (v: number): number =>
    margin.left + ((v - xMin) / (xMax - xMin || 1)) * innerW;
  const yScale = (v: number): number =>
    margin.top + innerH - ((v - yLo) / (yHi - yLo || 1)) * innerH;

  const xTicks = niceTicks(xMin, xMax, 5);
  const yTicks = niceTicks(yLo, yHi, 5);

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Bland-Altman agreement plot"
        className="h-auto w-full max-w-3xl"
      >
        {/* Axis frame */}
        <rect
          x={margin.left}
          y={margin.top}
          width={innerW}
          height={innerH}
          fill="white"
          stroke="oklch(0.9 0.04 220)"
        />

        {/* Y gridlines + labels */}
        {yTicks.map((t) => (
          <g key={`y-${t}`}>
            <line
              x1={margin.left}
              x2={margin.left + innerW}
              y1={yScale(t)}
              y2={yScale(t)}
              stroke="oklch(0.95 0.04 220)"
              strokeDasharray="2 4"
            />
            <text
              x={margin.left - 8}
              y={yScale(t)}
              fontSize="11"
              textAnchor="end"
              dominantBaseline="middle"
              fill="oklch(0.43 0.14 220)"
            >
              {t.toFixed(1)}
            </text>
          </g>
        ))}

        {/* X gridlines + labels */}
        {xTicks.map((t) => (
          <g key={`x-${t}`}>
            <line
              x1={xScale(t)}
              x2={xScale(t)}
              y1={margin.top}
              y2={margin.top + innerH}
              stroke="oklch(0.95 0.04 220)"
              strokeDasharray="2 4"
            />
            <text
              x={xScale(t)}
              y={margin.top + innerH + 18}
              fontSize="11"
              textAnchor="middle"
              fill="oklch(0.43 0.14 220)"
            >
              {t.toFixed(0)}
            </text>
          </g>
        ))}

        {/* Bias line (solid) */}
        <line
          x1={margin.left}
          x2={margin.left + innerW}
          y1={yScale(stats.bias_bpm)}
          y2={yScale(stats.bias_bpm)}
          stroke="oklch(0.52 0.16 220)"
          strokeWidth={2}
        />
        <text
          x={margin.left + innerW - 4}
          y={yScale(stats.bias_bpm) - 4}
          fontSize="11"
          textAnchor="end"
          fill="oklch(0.43 0.14 220)"
        >
          bias {stats.bias_bpm >= 0 ? '+' : ''}
          {stats.bias_bpm.toFixed(2)}
        </text>

        {/* LoA upper (dashed) */}
        <line
          x1={margin.left}
          x2={margin.left + innerW}
          y1={yScale(stats.loa_upper_bpm)}
          y2={yScale(stats.loa_upper_bpm)}
          stroke="oklch(0.55 0.2 25)"
          strokeWidth={1.5}
          strokeDasharray="6 4"
        />
        <text
          x={margin.left + innerW - 4}
          y={yScale(stats.loa_upper_bpm) - 4}
          fontSize="11"
          textAnchor="end"
          fill="oklch(0.36 0.13 25)"
        >
          +1.96 σ ({stats.loa_upper_bpm.toFixed(1)})
        </text>

        {/* LoA lower (dashed) */}
        <line
          x1={margin.left}
          x2={margin.left + innerW}
          y1={yScale(stats.loa_lower_bpm)}
          y2={yScale(stats.loa_lower_bpm)}
          stroke="oklch(0.55 0.2 25)"
          strokeWidth={1.5}
          strokeDasharray="6 4"
        />
        <text
          x={margin.left + innerW - 4}
          y={yScale(stats.loa_lower_bpm) + 14}
          fontSize="11"
          textAnchor="end"
          fill="oklch(0.36 0.13 25)"
        >
          −1.96 σ ({stats.loa_lower_bpm.toFixed(1)})
        </text>

        {/* Zero reference */}
        <line
          x1={margin.left}
          x2={margin.left + innerW}
          y1={yScale(0)}
          y2={yScale(0)}
          stroke="oklch(0.85 0.02 220)"
          strokeWidth={1}
        />

        {/* Points */}
        {xs.map((x, i) => {
          const y = ys[i] ?? 0;
          return (
            <circle
              key={i}
              cx={xScale(x)}
              cy={yScale(y)}
              r={4}
              fill="oklch(0.52 0.16 220)"
              opacity={0.75}
            />
          );
        })}

        {/* Axis labels */}
        <text
          x={margin.left + innerW / 2}
          y={height - 12}
          fontSize="12"
          textAnchor="middle"
          fill="oklch(0.25 0.08 220)"
        >
          Mean (rppg + ref) / 2  (bpm)
        </text>
        <text
          transform={`translate(16,${margin.top + innerH / 2}) rotate(-90)`}
          fontSize="12"
          textAnchor="middle"
          fill="oklch(0.25 0.08 220)"
        >
          Difference (rppg − ref)  (bpm)
        </text>
      </svg>
    </div>
  );
}

function niceTicks(lo: number, hi: number, target: number): number[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo) {
    return [lo, hi];
  }
  const span = hi - lo;
  const step = niceStep(span / Math.max(target, 2));
  const first = Math.ceil(lo / step) * step;
  const out: number[] = [];
  for (let v = first; v <= hi + 1e-9; v += step) {
    out.push(Number(v.toFixed(6)));
  }
  return out;
}

function niceStep(raw: number): number {
  if (raw <= 0) return 1;
  const exp = Math.floor(Math.log10(raw));
  const mant = raw / Math.pow(10, exp);
  let nice = 1;
  if (mant >= 5) nice = 5;
  else if (mant >= 2.5) nice = 2.5;
  else if (mant >= 2) nice = 2;
  else if (mant >= 1) nice = 1;
  return nice * Math.pow(10, exp);
}
