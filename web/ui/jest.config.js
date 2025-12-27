/**
 * Jest configuration for Water Treatment Controller HMI
 *
 * This configuration enables:
 * - React component testing with Testing Library
 * - TypeScript support
 * - Next.js compatibility
 * - Fast, offline execution (no network dependencies)
 */

const nextJest = require('next/jest');

const createJestConfig = nextJest({
  // Provide the path to your Next.js app to load next.config.js and .env files
  dir: './',
});

/** @type {import('jest').Config} */
const customJestConfig = {
  // Setup files to run after jest is initialized
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],

  // Test environment for React components
  testEnvironment: 'jsdom',

  // Module path aliases matching tsconfig paths
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },

  // Test file patterns
  testMatch: [
    '**/__tests__/**/*.test.[jt]s?(x)',
    '**/?(*.)+(spec|test).[jt]s?(x)',
  ],

  // Coverage configuration
  collectCoverageFrom: [
    'src/**/*.{js,jsx,ts,tsx}',
    '!src/**/*.d.ts',
    '!src/**/index.{js,ts}',
  ],

  // Ignore patterns
  testPathIgnorePatterns: ['<rootDir>/node_modules/', '<rootDir>/.next/'],
};

module.exports = createJestConfig(customJestConfig);
