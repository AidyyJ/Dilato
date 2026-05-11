import type { Config } from "jest";

// Force React development build so act() is available for testing-library.
(process.env as Record<string, string | undefined>).NODE_ENV = "test";

const config: Config = {
  coverageProvider: "v8",
  coverageThreshold: {
    global: {
      branches: 85,
      functions: 65,
      lines: 90,
      statements: 90,
    },
  },
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  testMatch: ["**/*.test.ts", "**/*.test.tsx"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
    "\\.(css|less|scss|sass)$": "identity-obj-proxy",
  },
  transform: {
    "^.+\\.(ts|tsx)$": [
      "ts-jest",
      {
        tsconfig: {
          jsx: "react-jsx",
        },
      },
    ],
  },
  transformIgnorePatterns: [
    "node_modules/(?!(@testing-library|react|react-dom|next|scheduler)/)",
  ],
};

export default config;
