import React from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

const PIE_COLORS = ["#0c8f81", "#4393ff", "#f1a64a", "#8a8ef0", "#88939b"];

export function CompositionPieChart({
  contentTypes,
}: {
  contentTypes: Array<{ name: string; value: number }>;
}) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <PieChart>
        <Pie
          data={contentTypes}
          dataKey="value"
          nameKey="name"
          innerRadius={42}
          outerRadius={66}
          paddingAngle={2}
        >
          {contentTypes.map((_, index) => (
            <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip />
        <Legend
          verticalAlign="middle"
          align="right"
          layout="vertical"
          wrapperStyle={{ fontSize: 12, lineHeight: "22px" }}
          iconSize={8}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
