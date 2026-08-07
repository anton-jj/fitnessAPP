/** @type {import('tailwindcss').Config} */

// A plain black theme: neutral greys, no colour cast, muted accents.
// Nothing here is fully saturated — the data is what should stand out,
// not the chrome around it.
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0a0a0a',
          secondary: '#141414',
          tertiary: '#1c1c1c',
          hover: '#242424',
        },
        // Monochrome accent: on a black UI the emphasis colour is light, and
        // filled buttons carry dark text. Colour is reserved for data.
        accent: {
          DEFAULT: '#e8e8e8',
          hover: '#ffffff',
          muted: '#8a8a8a',
        },
        // Semantic status colors — muted so a warning reads as information,
        // not an alarm.
        success: {
          DEFAULT: '#8faa7d',
          muted: '#5f7353',
        },
        warning: {
          DEFAULT: '#c2a15c',
          muted: '#8a7340',
        },
        danger: {
          DEFAULT: '#c07a72',
          muted: '#8a544e',
        },
        info: {
          DEFAULT: '#7d95ab',
          muted: '#546b7d',
        },
        // Full neutral-grey ramp. Every step is defined so no cool default
        // slate can leak in at an undefined shade.
        slate: {
          100: '#f4f4f4',
          200: '#e0e0e0',
          300: '#bdbdbd',
          400: '#949494',
          500: '#6e6e6e',
          600: '#525252',
          700: '#3a3a3a',
          800: '#282828',
          900: '#1a1a1a',
        },
        sport: {
          running: '#8faa7d',
          cycling: '#7d95ab',
          swimming: '#74a3a8',
          strength: '#c08f56',
          other: '#9b8fa8',
        },
        // Sequential cool -> warm ramp for training zones.
        zone: {
          1: '#8a97a3',
          2: '#8faa7d',
          3: '#c2a15c',
          4: '#c08b60',
          5: '#b8736b',
        },
      },
    },
  },
  plugins: [],
}
