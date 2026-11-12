import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './core/auth/auth-guards';

export const routes: Routes = [
  {
    path: 'login',
    title: 'Sign in',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login-page').then((m) => m.LoginPage),
  },
  {
    path: 'account/signup',
    title: 'Create account',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/signup-page').then((m) => m.SignupPage),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./layout/shell').then((m) => m.Shell),
    children: [
      {
        path: '',
        pathMatch: 'full',
        title: 'Dashboard',
        loadComponent: () =>
          import('./features/dashboard/dashboard-page').then((m) => m.DashboardPage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
