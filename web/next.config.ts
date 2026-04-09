import type { NextConfig } from "next";
import path from "path";
import withBundleAnalyzer from "@next/bundle-analyzer";

const enableAnalyze = process.env.ANALYZE === "true";

const nextConfig: NextConfig = {
  output: "export",
  images: {
    // Static export cannot use on-demand Image Optimization.
    // Keep unoptimized in export mode, but allow override for non-export builds.
    unoptimized: process.env.NEXT_IMAGE_UNOPTIMIZED !== "false",
  },
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default withBundleAnalyzer({ enabled: enableAnalyze })(nextConfig);
