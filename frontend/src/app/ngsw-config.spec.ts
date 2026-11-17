import { readFileSync } from 'node:fs';

// `ng test` runs in the folder of the project.
const config = JSON.parse(readFileSync('ngsw-config.json', 'utf-8')) as {
  assetGroups: { name: string; resources: { files?: string[]; urls?: string[] } }[];
  dataGroups?: unknown;
  navigationUrls: string[];
};

/**
 * The service worker keeps the app shell and nothing else: the answers of the API hold private
 * training and health data and must never be stored on the device.
 */
describe('the service worker configuration', () => {
  it('has no data groups, so no answer of the API is cached', () => {
    expect(config.dataGroups).toBeUndefined();
  });

  it('caches only static files of the app', () => {
    const patterns = config.assetGroups.flatMap((group) => [
      ...(group.resources.files ?? []),
      ...(group.resources.urls ?? []),
    ]);

    expect(patterns.length).toBeGreaterThan(0);
    for (const pattern of patterns) {
      expect(pattern, pattern).not.toMatch(/api/i);
      expect(pattern, pattern).not.toMatch(/^https?:/);
    }
  });

  it('never answers an address of the API with the start page', () => {
    expect(config.navigationUrls).toContain('!/api/**');
  });
});
