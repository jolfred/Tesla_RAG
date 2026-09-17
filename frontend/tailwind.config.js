/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  corePlugins: {
    // Не ломаем VKUI-стили глобальным reset'ом
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        void: '#07060A',
        glass: '#110F18',
        royal: '#7A3EE6',
        royalLight: '#9D65FF',
      },
      fontFamily: {
        display: ['Unbounded', 'Manrope', 'system-ui', 'sans-serif'],
        body: ['Inter', 'Manrope', 'system-ui', 'sans-serif'],
      },
      animation: {
        marquee: 'marquee 42s linear infinite',
        pulseGlow: 'pulseGlow 3.2s ease-in-out infinite',
      },
      keyframes: {
        marquee: {
          from: { transform: 'translateX(0)' },
          to: { transform: 'translateX(-50%)' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: 0.55 },
          '50%': { opacity: 1 },
        },
      },
    },
  },
  plugins: [],
}
