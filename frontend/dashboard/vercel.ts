import { routes, deploymentEnv, type VercelConfig } from '@vercel/config/v1';

export const config: VercelConfig = {
  framework: 'vite',
  buildCommand: 'npm run build',
  outputDirectory: 'dist',
  installCommand: 'npm ci',

  rewrites: [
    routes.rewrite(
      '/api/(.*)',
      `${deploymentEnv('BACKEND_API_ORIGIN')}/$1`,
    ),
    routes.rewrite('/(.*)', '/index.html'),
  ],

  headers: [
    routes.cacheControl('/assets/(.*)', {
      public: true,
      maxAge: '1year',
      immutable: true,
    }),
    routes.header('/sw.js', [
      { key: 'Cache-Control', value: 'no-cache' },
    ]),
    routes.header('/manifest.webmanifest', [
      { key: 'Cache-Control', value: 'no-cache' },
    ]),
    routes.header('/(.*)', [
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
      {
        key: 'Permissions-Policy',
        value: 'camera=(), microphone=(), geolocation=()',
      },
    ]),
  ],
};
