import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8080";

export default defineConfig({
  root: "api/webui",
  base: "/static/dist/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": apiProxyTarget,
      "/logos": apiProxyTarget
    }
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(__dirname, "api/webui/index.html"),
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            if (id.includes("ContentTrackingPageRedesign")) return "content-tracking";
            if (id.includes("competitor_monitor/CompositionBreakdown")) {
              return "competitor-monitor-composition";
            }
            if (id.includes("competitor_monitor/CompositionWordCloud")) {
              return "competitor-monitor-wordcloud";
            }
            if (id.includes("competitor_monitor/CompositionPieChart")) {
              return "competitor-monitor-piechart";
            }
            if (id.includes("competitor_monitor/mock")) return "competitor-monitor-mock";
            if (id.includes("competitor_monitor")) return "competitor-monitor";
            if (id.includes("GrowthIntelligencePages")) return "growth-intelligence";
            if (id.includes("creator-discovery")) return "creator-discovery";
            return undefined;
          }

          if (id.includes("react") || id.includes("scheduler")) {
            return "react-vendor";
          }
          if (id.includes("echarts") || id.includes("echarts-wordcloud") || id.includes("zrender")) {
            return "echarts-vendor";
          }
          if (id.includes("recharts") || id.includes("d3-")) {
            return "recharts-vendor";
          }
          if (
            id.includes("@radix-ui") ||
            id.includes("lucide-react") ||
            id.includes("class-variance-authority") ||
            id.includes("clsx")
          ) {
            return "ui-vendor";
          }
          return "vendor";
        },
      },
    },
  }
});
