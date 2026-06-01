/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    // better-sqlite3 is a native module; keep it external to the server bundle so
    // Next doesn't try to webpack-bundle the .node binary. (On Next 15 this key
    // moved to the top level as `serverExternalPackages`.)
    serverComponentsExternalPackages: ["better-sqlite3"],
  },
};

export default nextConfig;
