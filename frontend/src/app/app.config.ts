import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideApiClient } from './core/api/api-providers';
import { AuthStore } from './core/auth/auth-store';
import { ThemeStore } from './core/theme/theme-store';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideApiClient(),
    provideAppInitializer(() => inject(ThemeStore).initialize()),
    provideAppInitializer(() => inject(AuthStore).initialize()),
  ],
};
