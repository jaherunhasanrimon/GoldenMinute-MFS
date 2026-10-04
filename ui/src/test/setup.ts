import '@testing-library/jest-dom';

const storage: Record<string, string> = {};
const localStorageMock = {
  getItem: (key: string) => storage[key] ?? null,
  setItem: (key: string, value: string) => {
    storage[key] = value;
  },
  removeItem: (key: string) => {
    delete storage[key];
  },
  clear: () => {
    Object.keys(storage).forEach((k) => delete storage[k]);
  },
};

import React from 'react';
import { vi } from 'vitest';

// Mock react-force-graph-2d for jsdom test environment (no HTML5 canvas)
vi.mock('react-force-graph-2d', () => ({
  default: (props: any) =>
    React.createElement(
      'div',
      {
        'data-testid': 'force-graph-mock',
        'data-node-count': props.graphData?.nodes?.length || 0,
      },
      `ForceGraph2D (${props.graphData?.nodes?.length || 0} nodes)`
    ),
}));

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true,
});
