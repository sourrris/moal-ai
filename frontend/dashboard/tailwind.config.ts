import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: '#ffffff',
        'surface-muted': '#f5f5f5',
        ink: '#09090b',
        'ink-muted': '#52525b',
        stroke: '#e4e4e7',
        accent: '#18181b',
        success: '#16a34a',
        warning: '#b45309',
        critical: '#dc2626',
        info: '#2563eb'
      },
      borderRadius: {
        pill: '9999px',
        card: '24px'
      },
      boxShadow: {
        soft: '0 6px 20px rgba(9, 9, 11, 0.06)',
        panel: '0 14px 36px rgba(9, 9, 11, 0.08)'
      },
      fontFamily: {
        sans: ['Manrope', 'Plus Jakarta Sans', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace']
      },
      keyframes: {
        'ambient-drift': {
          '0%, 100%': { transform: 'translate3d(0, 0, 0)', opacity: '0.5' },
          '50%': { transform: 'translate3d(0, -2%, 0)', opacity: '0.72' }
        },
        'soft-fade': {
          from: { opacity: '0' },
          to: { opacity: '1' }
        }
      },
      animation: {
        'ambient-drift': 'ambient-drift 16s ease-in-out infinite',
        'soft-fade': 'soft-fade 220ms ease-out'
      }
    }
  },
  plugins: []
};

export default config;
