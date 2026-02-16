/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#ffffff',
        steel: '#1e293b',
        mist: '#334155',
        signal: '#3b82f6',
        ocean: '#2563eb',
        mint: '#22c55e'
      },
      boxShadow: {
        card: '0 18px 40px -24px rgba(16,20,24,0.5)'
      },
      fontFamily: {
        display: ['Poppins', 'sans-serif'],
        body: ['Manrope', 'sans-serif']
      }
    }
  },
  plugins: []
}
