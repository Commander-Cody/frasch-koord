// The stylesheets under src/, read as text: jsdom loads no CSS, so the tests
// that hold the stylesheets to a rule (layout.test.ts, theme.test.ts) read
// their declarations instead.

/** Every stylesheet under src/, by path from here, comments left out. */
export const STYLESHEETS: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>('../**/*.css', { query: '?raw', import: 'default', eager: true }),
  ).map(([file, css]) => [file, css.replace(/\/\*[\s\S]*?\*\//g, '')]),
);

export interface Declaration {
  file: string;
  property: string;
  value: string;
}

/** Every declaration in those stylesheets, custom properties included. */
export function declarations(): Declaration[] {
  return Object.entries(STYLESHEETS).flatMap(([file, css]) =>
    [...css.matchAll(/([\w-]+)\s*:\s*([^;{}]+)(?=[;}])/g)].map(([, property, value]) => ({
      file,
      property,
      value: value.trim(),
    })),
  );
}
