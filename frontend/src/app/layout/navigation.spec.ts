import { ICON_NAMES } from '../shared/icon';
import { routes } from '../app.routes';
import { NAV_GROUPS, moreGroups, tabItems, visibleGroups } from './navigation';

describe('navigation', () => {
  const paths = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.path));

  it('lists every page of the shell exactly once, and nothing else', () => {
    const shell = routes.find((route) => route.path === '' && route.children !== undefined);
    const routed = (shell?.children ?? []).map((route) => `/${route.path}`.replace(/^\/$/, '/'));

    expect([...paths].sort()).toEqual([...routed].sort());
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('uses icons that exist', () => {
    for (const group of NAV_GROUPS) {
      for (const item of group.items) {
        expect(ICON_NAMES, item.label).toContain(item.icon);
      }
    }
  });

  it('gives every page one label', () => {
    const labels = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.label));

    expect(new Set(labels).size).toBe(labels.length);
    expect(labels.every((label) => label.trim() !== '')).toBe(true);
  });

  it('marks only the dashboard as exact', () => {
    const exact = NAV_GROUPS.flatMap((group) => group.items).filter((item) => item.exact);

    expect(exact.map((item) => item.path)).toEqual(['/']);
  });

  it('shows members the groups of the everyday work, administrators Admin too', () => {
    expect(visibleGroups(false).map((group) => group.label)).toEqual([
      'Training',
      'Planning',
      'Settings',
    ]);
    expect(visibleGroups(true).map((group) => group.label)).toEqual([
      'Training',
      'Planning',
      'Settings',
      'Admin',
    ]);
  });

  it('puts the four everyday pages in the tab bar', () => {
    expect(tabItems().map((item) => item.label)).toEqual([
      'Dashboard',
      'Week plan',
      'Week review',
      'Activities',
    ]);
  });

  it('leaves the rest to "More", with Admin only for administrators', () => {
    expect(moreGroups(false).map((group) => group.label)).toEqual(['Planning', 'Settings']);
    expect(moreGroups(true).map((group) => group.label)).toEqual(['Planning', 'Settings', 'Admin']);
  });

  it('reaches every page from the tab bar or from "More"', () => {
    const reachable = [...tabItems(), ...moreGroups(true).flatMap((group) => group.items)];

    expect(reachable.map((item) => item.path).sort()).toEqual([...paths].sort());
  });
});
