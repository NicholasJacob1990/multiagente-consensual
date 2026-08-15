import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    testTimeout: 15000,
    setupFiles: ['./tests/helpers/setup.js'],
    include: ['tests/**/*.test.js'],
  },
});
