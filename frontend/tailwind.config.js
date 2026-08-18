/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: '#0B0F14',
        surface: '#121821',
        raised: '#1A2230',
        border: '#26303E',
        'text-primary': '#E7EDF3',
        'text-secondary': '#8B99AB',
        'text-disabled': '#4C5768',
        accent: {
          DEFAULT: '#1F8A8C',
          hover: '#26A3A6',
          ring: '#4FD1D4',
        },
        amber: '#D6A94A',
        risk: {
          critical: '#E5484D',
          high: '#F2994A',
          medium: '#F2C94C',
          low: '#6FCF97',
          neutral: '#8B99AB',
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
      },
      letterSpacing: {
        micro: '0.04em',
      },
    },
  },
  plugins: [],
}
