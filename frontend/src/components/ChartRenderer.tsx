import {
  ResponsiveContainer,
  LineChart,
  BarChart,
  PieChart,
  ScatterChart,
  Line,
  Bar,
  Pie,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell,
} from "recharts";
import type { ChartSpec, Row } from "@/lib/api";

const COLORS = [
  "hsl(199, 89%, 48%)",
  "hsl(160, 60%, 45%)",
  "hsl(280, 60%, 55%)",
  "hsl(35, 90%, 55%)",
  "hsl(340, 65%, 55%)",
];

interface ChartRendererProps {
  spec: ChartSpec;
  data: Row[];
}

/** MySQL DECIMALs arrive as strings; recharts needs numbers to size bars and lines. */
function toNumber(value: unknown): unknown {
  if (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))) {
    return Number(value);
  }
  return value;
}

/**
 * Turn long rows ({x, group, y}) into one wide row per x value ({x, [group]: y, ...}),
 * so each group becomes its own bar or line series.
 */
function pivot(data: Row[], x: string, y: string, groupBy: string) {
  const series: string[] = [];
  const byX = new Map<string, Row>();
  for (const row of data) {
    const group = String(row[groupBy]);
    if (!series.includes(group)) series.push(group);
    const key = String(row[x]);
    const wide = byX.get(key) ?? { [x]: row[x] };
    wide[group] = toNumber(row[y]);
    byX.set(key, wide);
  }
  return { rows: [...byX.values()], series };
}

const ChartRenderer = ({ spec, data }: ChartRendererProps) => {
  const { chart_type: chartType, x, y, group_by: groupBy, x_label, y_label, title } = spec;

  const numeric = data.map((row) => ({ ...row, [y]: toNumber(row[y]) }));
  const { rows, series } =
    groupBy && chartType !== "pie" && chartType !== "scatter"
      ? pivot(data, x, y, groupBy)
      : { rows: numeric, series: [y] };

  const commonAxisProps = {
    tick: { fill: "hsl(215, 12%, 50%)", fontSize: 12 },
    axisLine: { stroke: "hsl(220, 14%, 18%)" },
    tickLine: false,
  };

  const tooltipStyle = {
    contentStyle: {
      background: "hsl(220, 18%, 10%)",
      border: "1px solid hsl(220, 14%, 18%)",
      borderRadius: 8,
      color: "hsl(210, 20%, 90%)",
      fontSize: 13,
    },
  };

  const heading = title && <p className="text-sm font-medium text-foreground">{title}</p>;

  if (chartType === "pie") {
    return (
      <div>
        {heading}
        <div className="mt-4 h-72 w-full">
          <ResponsiveContainer>
            <PieChart>
              <Pie
                data={numeric}
                dataKey={y}
                nameKey={x}
                cx="50%"
                cy="50%"
                outerRadius={100}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {numeric.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip {...tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  const ChartComponent = chartType === "bar" ? BarChart : chartType === "scatter" ? ScatterChart : LineChart;

  return (
    <div>
      {heading}
      <div className="mt-4 h-72 w-full">
        <ResponsiveContainer>
          <ChartComponent data={rows} margin={{ bottom: 10, left: 10 }}>
            <CartesianGrid stroke="hsl(220, 14%, 15%)" strokeDasharray="3 3" />
            <XAxis
              dataKey={x}
              label={{ value: x_label, position: "insideBottom", offset: -5, fill: "hsl(215, 12%, 50%)" }}
              {...commonAxisProps}
            />
            <YAxis
              dataKey={chartType === "scatter" ? y : undefined}
              label={{ value: y_label, angle: -90, position: "insideLeft", fill: "hsl(215, 12%, 50%)" }}
              {...commonAxisProps}
            />
            <Tooltip {...tooltipStyle} />
            {series.length > 1 && <Legend verticalAlign="top" height={28} />}
            {chartType === "bar" &&
              series.map((s, i) => <Bar key={s} dataKey={s} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} />)}
            {chartType === "scatter" && <Scatter dataKey={y} fill={COLORS[0]} />}
            {chartType === "line" &&
              series.map((s, i) => (
                <Line
                  key={s}
                  type="monotone"
                  dataKey={s}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2}
                  dot={{ fill: COLORS[i % COLORS.length], r: 3 }}
                  activeDot={{ r: 5 }}
                />
              ))}
          </ChartComponent>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default ChartRenderer;
