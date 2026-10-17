/** @type {import('next').NextConfig} */
const nextConfig = {
  // Type errors fail the build (they used to be ignored; review finding F-22). Lint runs as its own step.
  typescript: {
    ignoreBuildErrors: false,
  },
  async rewrites() {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
