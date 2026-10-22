/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: 'var(--color-canvas)',
        surface: 'var(--color-surface)',
        raised: 'var(--color-raised)',
        border: 'var(--color-border)',
        'text-primary': 'var(--color-text-primary)',
        'text-secondary': 'var(--color-text-secondary)',
        'text-disabled': 'var(--color-text-disabled)',
        accent: {
          DEFAULT: 'var(--color-accent)',
          hover: 'var(--color-accent-hover)',
          ring: 'var(--color-accent-ring)',
        },
        amber: 'var(--color-amber)',
        risk: {
          critical: 'var(--risk-critical)',
          high: 'var(--risk-high)',
          medium: 'var(--risk-medium)',
          low: 'var(--risk-low)',
          neutral: 'var(--risk-neutral)',
        },
        primary: {
          50: '#e6f5f5',
          100: '#ccebeb',
          200: '#99d7d8',
          300: '#66c3c5',
          400: '#33afb2',
          500: '#1F8A8C',
          600: '#1a7375',
          700: '#145c5e',
          800: '#0f4546',
          900: '#0a2e2f',
          950: '#051717',
        },
        secondary: {
          50: '#f1f4f8',
          100: '#e3e9f1',
          200: '#c7d3e3',
          300: '#abbdd5',
          400: '#8f9fc0',
          500: '#7383a5',
          600: '#5c6984',
          700: '#454f63',
          800: '#2e3542',
          900: '#171b22',
          950: '#0b0d11',
        },
        danger: {
          100: '#fde8e8',
          500: '#E5484D',
          600: '#c73a3f',
          700: '#9c2e32',
        },
        success: {
          100: '#e8f7ef',
          500: '#6FCF97',
          600: '#4cb87a',
          700: '#3a8f5f',
        },
        warning: {
          100: '#fdf3e2',
          500: '#F2994A',
          600: '#d97e30',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
      fontSize: {
        'micro': ['11px', { lineHeight: '1.3' }],
        'data': ['13px', { lineHeight: '1.3' }],
        'label': ['var(--text-xs)', { lineHeight: '1.3' }],
        'body': ['var(--text-base)', { lineHeight: '1.5' }],
        'title': ['var(--text-lg)', { lineHeight: '1.2' }],
        'display': ['var(--text-2xl)', { lineHeight: '1.2' }],
      },
      borderRadius: {
        control: 'var(--radius-md)',
        panel: 'var(--radius-lg)',
        pill: 'var(--radius-full)',
      },
      boxShadow: {
        panel: 'var(--shadow-md)',
        overlay: 'var(--shadow-lg)',
      },
      transitionDuration: {
        fast: 'var(--motion-fast)',
        base: 'var(--motion-base)',
        slow: 'var(--motion-slow)',
      },
      transitionTimingFunction: {
        standard: 'var(--ease-standard)',
        decelerate: 'var(--ease-decelerate)',
      },
      spacing: {
        gutter: 'var(--space-6)',
        section: 'var(--space-8)',
      },
      letterSpacing: {
        micro: '0.04em',
      },
    },
  },
  plugins: [],
}
