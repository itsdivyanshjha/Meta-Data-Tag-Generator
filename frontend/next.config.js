/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone', // Enable standalone output for Docker
  images: {
    unoptimized: true // Disable image optimization for simpler deployment
  },
  env: {
    BACKEND_URL: process.env.BACKEND_URL || 'http://localhost:8000'
  },
  async rewrites() {
    return [
      {
        source: '/api/backend/:path*',
        destination: `${process.env.BACKEND_URL || 'http://localhost:8000'}/:path*`
      }
    ]
  }
}

module.exports = nextConfig

