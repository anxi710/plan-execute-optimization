import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react()],
  base: './',
  publicDir: false,
  build: {
    outDir: fileURLToPath(new URL('../experiments/planner-centered', import.meta.url)),
    // The output directory also contains original experiment evidence.
    emptyOutDir: false,
    assetsDir: 'alfworld/assets',
    rolldownOptions: { input: fileURLToPath(new URL('alfworld.html', import.meta.url)) },
  },
});
