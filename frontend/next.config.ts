import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  
  // Enable standalone output for Docker
  output: 'standalone',
  
  // Code splitting optimization
  experimental: {
    optimizePackageImports: ['@/components', '@/lib'],
  },

  images: {
    domains: [],
  },
};

export default withNextIntl(nextConfig);
