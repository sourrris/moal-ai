import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#f5f5f5',
        'canvas-warm': '#f5f2ef',
        surface: '#ffffff',
        'surface-muted': '#f6f6f6',
        ink: '#000000',
        'ink-muted': '#4e4e4e',
        'ink-soft': '#777169',
        stroke: '#e5e5e5',
        'stroke-subtle': 'rgba(0, 0, 0, 0.05)',
        accent: '#000000',
        success: '#2f7f56',
        warning: '#8a6539',
        critical: '#9c4139',
        info: '#5f7489',
        grid: '#7fffff'
      },
      borderRadius: {
        pill: '9999px',
        warm: '30px',
        card: '24px',
        panel: '18px'
      },
      boxShadow: {
        outline:
          'rgba(0, 0, 0, 0.075) 0 0 0 0.5px inset, rgba(0, 0, 0, 0.06) 0 0 0 1px, rgba(0, 0, 0, 0.04) 0 1px 2px, rgba(0, 0, 0, 0.04) 0 2px 4px',
        surface:
          'rgba(0, 0, 0, 0.075) 0 0 0 0.5px inset, rgba(0, 0, 0, 0.06) 0 0 0 1px, rgba(0, 0, 0, 0.04) 0 4px 4px',
        soft: 'rgba(0, 0, 0, 0.04) 0 4px 4px',
        field: 'rgba(0, 0, 0, 0.08) 0 0 0 0.5px, rgba(0, 0, 0, 0.1) 0 0 0 1px inset',
        warm: 'rgba(78, 50, 23, 0.04) 0 6px 16px',
        pill: 'rgba(0, 0, 0, 0.4) 0 0 1px, rgba(0, 0, 0, 0.04) 0 4px 4px',
        panel: 'rgba(0, 0, 0, 0.06) 0 16px 40px'
      },
      fontFamily: {
        sans: ['"Universal Sans"', 'Geist', 'Inter', 'Segoe UI', 'sans-serif'],
        display: ['"Universal Sans"', 'Geist', 'Inter', 'Segoe UI', 'sans-serif'],
        mono: ['"Geist Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace']
      },
      keyframes: {
        'ambient-float': {
          '0%, 100%': { transform: 'translate3d(0, 0, 0) scale(1)' },
          '50%': { transform: 'translate3d(0, -3%, 0) scale(1.04)' }
        },
        'ambient-float-reverse': {
          '0%, 100%': { transform: 'translate3d(0, 0, 0) scale(1)' },
          '50%': { transform: 'translate3d(0, 3%, 0) scale(0.98)' }
        },
        'soft-fade': {
          from: { opacity: '0' },
          to: { opacity: '1' }
        },
        'soft-rise': {
          from: { opacity: '0', transform: 'translate3d(0, 14px, 0)' },
          to: { opacity: '1', transform: 'translate3d(0, 0, 0)' }
        }
      },
      animation: {
        'ambient-float': 'ambient-float 18s ease-in-out infinite',
        'ambient-float-reverse': 'ambient-float-reverse 22s ease-in-out infinite',
        'soft-fade': 'soft-fade 220ms ease-out',
        'soft-rise': 'soft-rise 500ms ease-out'
      }
    }
  },
  plugins: []
};

export default config;
