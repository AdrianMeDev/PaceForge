import { readFileSync } from 'node:fs';

// `ng test` runs in the folder of the project.
const angular = JSON.parse(readFileSync('angular.json', 'utf-8')) as {
  projects: {
    paceforge: {
      architect: {
        build: {
          configurations: {
            production: {
              optimization: {
                scripts: boolean;
                styles: { minify: boolean; inlineCritical: boolean };
              };
            };
          };
        };
      };
    };
  };
};
const page = readFileSync('src/index.html', 'utf-8');
const caddyfile = readFileSync('../deploy/Caddyfile', 'utf-8');

/** The directives of the Content-Security-Policy header in the Caddyfile, by name. */
function policy(): Map<string, string[]> {
  const header = /Content-Security-Policy\s+"([^"]*)"/.exec(caddyfile)?.[1] ?? '';
  expect(header, 'Content-Security-Policy header').not.toBe('');
  return new Map(
    header
      .split(';')
      .map((directive) => directive.trim().split(/\s+/))
      .map(([name, ...sources]) => [name, sources]),
  );
}

describe('the content security policy', () => {
  it('builds the production app without inlined critical CSS, so no inline script is needed', () => {
    const optimization =
      angular.projects.paceforge.architect.build.configurations.production.optimization;
    expect(optimization.styles.inlineCritical).toBe(false);
    expect(optimization.scripts).toBe(true);
    expect(optimization.styles.minify).toBe(true);
  });

  it('serves a page without inline scripts, event handler attributes or plugin elements', () => {
    for (const [, body] of page.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) {
      expect(body.trim()).toBe('');
    }
    expect(page).not.toMatch(/\son[a-z]+\s*=/i);
    expect(page).not.toMatch(/<(object|embed)\b/i);
  });

  it('allows scripts only from the own origin and no plugins at all', () => {
    const directives = policy();
    expect(directives.get('default-src')).toEqual(["'self'"]);
    expect(directives.get('script-src')).toEqual(["'self'"]);
    expect(directives.get('object-src')).toEqual(["'none'"]);
  });

  it('forbids framing, changes of the base address and forms that post elsewhere', () => {
    const directives = policy();
    expect(directives.get('frame-ancestors')).toEqual(["'none'"]);
    expect(directives.get('base-uri')).toEqual(["'self'"]);
    expect(directives.get('form-action')).toEqual(["'self'"]);
  });
});
