import React from "react";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import "echarts-wordcloud";

echarts.use([CanvasRenderer]);

export function CompositionWordCloud({
  words,
}: {
  words: Array<{ word: string; weight: number }>;
}) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const chartRef = React.useRef<ReturnType<typeof echarts.init> | null>(null);

  React.useEffect(() => {
    if (!containerRef.current) return;
    if (!chartRef.current) {
      chartRef.current = echarts.init(containerRef.current, undefined, { renderer: "canvas" });
    }
    const chart = chartRef.current;
    chart.setOption({
      tooltip: {
        backgroundColor: "rgba(9, 33, 29, 0.92)",
        borderWidth: 0,
        textStyle: { color: "#f7fbfa" },
        formatter: (params: { name: string; value: number }) => `${params.name}: ${params.value}`,
      },
      series: [
        {
          type: "wordCloud",
          shape: "circle",
          gridSize: 8,
          sizeRange: [12, 32],
          rotationRange: [0, 0],
          drawOutOfBound: false,
          textStyle: {
            fontWeight: 600,
            color: () => {
              const palette = ["#0c8f81", "#0f766e", "#149e91", "#2f7cf7", "#1eb980", "#f0a93e"];
              return palette[Math.floor(Math.random() * palette.length)];
            },
          },
          data: words.slice(0, 50).map((item) => ({ name: item.word, value: item.weight || 1 })),
        },
      ],
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [words]);

  React.useEffect(() => {
    return () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  return <div ref={containerRef} className="cmw-wordcloud" />;
}
