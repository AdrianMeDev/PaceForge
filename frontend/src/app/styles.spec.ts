import { readFileSync } from 'node:fs';

// `ng test` runs in the folder of the project.
const styles = readFileSync('src/styles.css', 'utf-8');

/** The custom properties a block of the stylesheet defines. */
function tokens(block: string): string[] {
  return [...block.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((match) => match[1]).sort();
}

/** The body of the first rule that starts with `selector {`, braces counted. */
function ruleBody(css: string, selector: string, from = 0): string {
  const start = css.indexOf(`${selector} {`, from);
  expect(start, selector).toBeGreaterThanOrEqual(0);
  let depth = 0;
  for (let i = css.indexOf('{', start); i < css.length; i++) {
    depth += css[i] === '{' ? 1 : css[i] === '}' ? -1 : 0;
    if (depth === 0) {
      return css.slice(css.indexOf('{', start) + 1, i);
    }
  }
  throw new Error(`rule ${selector} is not closed`);
}

describe('the stylesheet', () => {
  const light = tokens(ruleBody(styles, ':root'));
  // The dark colours are written twice: for the chosen theme and for a device that is dark.
  const chosenDark = tokens(ruleBody(styles, ":root[data-theme='dark']"));
  const deviceDark = tokens(ruleBody(styles, ":root:not([data-theme='light'])"));

  it('has the new surface, state and elevation tokens', () => {
    for (const name of [
      '--surface-2',
      '--accent-soft',
      '--success',
      '--success-bg',
      '--warning',
      '--warning-bg',
      '--r-sm',
      '--r-md',
      '--r-lg',
      '--elev-1',
      '--elev-2',
    ]) {
      expect(light, name).toContain(name);
    }
  });

  it('defines in the dark theme every colour and elevation of the light one', () => {
    const shared = (name: string) => !name.startsWith('--r-');
    expect(chosenDark).toEqual(light.filter(shared));
  });

  it('gives a device that is dark the same colours as the dark choice', () => {
    expect(deviceDark).toEqual(chosenDark);
    const values = (selector: string) => ruleBody(styles, selector).replace(/\s+/g, ' ').trim();
    expect(values(":root:not([data-theme='light'])")).toBe(values(":root[data-theme='dark']"));
  });

  it('tells the browser which scheme a chosen theme is', () => {
    expect(styles).toMatch(/:root\[data-theme='light'\] \{\s*color-scheme: light;/);
    expect(styles).toMatch(/:root\[data-theme='dark'\] \{\s*color-scheme: dark;/);
  });

  it('maps every colour token for Tailwind', () => {
    const theme = ruleBody(styles, '@theme inline');
    for (const name of light.filter((token) => !token.startsWith('--elev-'))) {
      if (name.startsWith('--r-')) {
        continue;
      }
      expect(theme, name).toContain(`: var(${name});`);
    }
  });
});
