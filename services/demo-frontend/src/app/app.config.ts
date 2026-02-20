// src/app/app.config.ts
import { ApplicationConfig, provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { routes } from './app.routes';
import { authInterceptor } from './interceptors/auth.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZonelessChangeDetection(), // Default in v21
    provideRouter(routes),
    provideHttpClient(
      withInterceptors([
        (req, next) => {
          // Automatically include cookies for BFF calls
          const authReq = req.clone({ withCredentials: true });
          return next(authReq);
        },
        authInterceptor
      ])
    ),
  ]
};