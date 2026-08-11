import type { NextConfig } from "next";

const config: NextConfig = {
  // The API is the only boundary between web/ and api/ (CLAUDE.md). Proxying
  // keeps that true in the browser too: the page never learns the API's host.
  async rewrites() {
    const api = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};

export default config;
