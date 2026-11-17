import {
  ApplicationConfig,
  inject,
  isDevMode,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideServiceWorker } from '@angular/service-worker';
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
    // Only in a production build, and only for the app shell: `ngsw-config.json` caches no answer of
    // the API, which holds private training and health data.
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
