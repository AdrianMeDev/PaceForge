import { IconName } from '../shared/icon';

export interface NavItem {
  label: string;
  path: string;
  icon: IconName;
  /** Only the dashboard: `/` is the start of every address. */
  exact?: boolean;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
  /** Only administrators see the group. */
  staffOnly?: boolean;
}

/** The pages of the signed-in app, in the order every kind of navigation shows them. */
export const NAV_GROUPS: readonly NavGroup[] = [
  {
    label: 'Training',
    items: [
      { label: 'Dashboard', path: '/', icon: 'home', exact: true },
      { label: 'Week plan', path: '/planning', icon: 'calendar-check' },
      { label: 'Week review', path: '/review', icon: 'check' },
      { label: 'Activities', path: '/activities', icon: 'activity' },
    ],
  },
  {
    label: 'Planning',
    items: [
      { label: 'Season', path: '/season', icon: 'calendar' },
      { label: 'Goals', path: '/goals', icon: 'target' },
      { label: 'Training time', path: '/availability', icon: 'clock' },
      { label: 'Coach', path: '/coach', icon: 'message' },
    ],
  },
  {
    label: 'Settings',
    items: [
      { label: 'Profile', path: '/settings/profile', icon: 'user' },
      { label: 'Connections', path: '/settings/connections', icon: 'link' },
      { label: 'Security', path: '/settings/security', icon: 'shield' },
    ],
  },
  {
    label: 'Admin',
    staffOnly: true,
    items: [{ label: 'Invitations', path: '/admin/invitations', icon: 'mail' }],
  },
];

/** The groups this user may see. */
export function visibleGroups(isStaff: boolean): NavGroup[] {
  return NAV_GROUPS.filter((group) => isStaff || !group.staffOnly);
}

/** The group of the tab bar on small screens: the pages used every day. */
export const TAB_GROUP = 'Training';

export function tabItems(): NavItem[] {
  return NAV_GROUPS.find((group) => group.label === TAB_GROUP)?.items ?? [];
}

/** The groups behind "More" on small screens. */
export function moreGroups(isStaff: boolean): NavGroup[] {
  return visibleGroups(isStaff).filter((group) => group.label !== TAB_GROUP);
}
