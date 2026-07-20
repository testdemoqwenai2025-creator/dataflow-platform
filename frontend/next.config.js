/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: 'http://localhost:8000/api/v1/:path*',
      },
      {
        source: '/api/health',
        destination: 'http://localhost:8000/api/health',
      },
      {
        source: '/api/docs',
        destination: 'http://localhost:8000/api/docs',
      },
    ];
  },
};

module.exports = nextConfig;
