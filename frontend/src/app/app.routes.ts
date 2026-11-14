import { Routes } from '@angular/router';
import {
  authGuard,
  guestGuard,
  mfaPendingGuard,
  mfaSetupGuard,
  staffGuard,
} from './core/auth/auth-guards';

export const routes: Routes = [
  {
    path: 'login',
    title: 'Sign in',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login-page').then((m) => m.LoginPage),
  },
  {
    path: 'login/mfa',
    title: 'Two-factor authentication',
    canActivate: [guestGuard, mfaPendingGuard],
    loadComponent: () => import('./features/auth/login-mfa-page').then((m) => m.LoginMfaPage),
  },
  {
    path: 'account/signup',
    title: 'Create account',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/signup-page').then((m) => m.SignupPage),
  },
  {
    path: 'account/password/reset',
    title: 'Reset password',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./features/auth/password-reset-request-page').then((m) => m.PasswordResetRequestPage),
  },
  {
    // Open to everyone, like the verification link: it may be followed in any browser.
    path: 'account/password/reset/key/:key',
    title: 'Choose a new password',
    loadComponent: () =>
      import('./features/auth/password-reset-page').then((m) => m.PasswordResetPage),
  },
  {
    // Open to everyone: the link may be followed signed in or out, in any browser.
    path: 'account/verify-email/:key',
    title: 'Confirm email',
    loadComponent: () => import('./features/auth/verify-email-page').then((m) => m.VerifyEmailPage),
  },
  {
    path: '',
    canActivate: [authGuard],
    canActivateChild: [mfaSetupGuard],
    loadComponent: () => import('./layout/shell').then((m) => m.Shell),
    children: [
      {
        path: '',
        pathMatch: 'full',
        title: 'Dashboard',
        loadComponent: () =>
          import('./features/dashboard/dashboard-page').then((m) => m.DashboardPage),
      },
      {
        path: 'activities',
        title: 'Activities',
        loadComponent: () =>
          import('./features/activities/activities-page').then((m) => m.ActivitiesPage),
      },
      {
        path: 'goals',
        title: 'Goals',
        loadComponent: () => import('./features/goals/goals-page').then((m) => m.GoalsPage),
      },
      {
        path: 'availability',
        title: 'Training time',
        loadComponent: () =>
          import('./features/availability/availability-page').then((m) => m.AvailabilityPage),
      },
      {
        path: 'planning',
        title: 'Week plan',
        loadComponent: () =>
          import('./features/planning/planning-page').then((m) => m.PlanningPage),
      },
      {
        path: 'settings/profile',
        title: 'Athlete profile',
        loadComponent: () => import('./features/athlete/athlete-page').then((m) => m.AthletePage),
      },
      {
        path: 'settings/security',
        title: 'Security',
        loadComponent: () =>
          import('./features/security/security-page').then((m) => m.SecurityPage),
      },
      {
        path: 'settings/connections',
        title: 'Connections',
        loadComponent: () =>
          import('./features/connections/connections-page').then((m) => m.ConnectionsPage),
      },
      {
        path: 'admin/invitations',
        title: 'Invitations',
        canActivate: [staffGuard],
        loadComponent: () =>
          import('./features/admin/invitations-page').then((m) => m.InvitationsPage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
