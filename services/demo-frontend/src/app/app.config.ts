// src/app/app.config.ts
import { ApplicationConfig, provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZonelessChangeDetection(), // Default in v21
    provideHttpClient(
      withInterceptors([
        (req, next) => {
          // Automatically include cookies for BFF calls
          const authReq = req.clone({ withCredentials: true });
          return next(authReq);
        }
      ])
    ),
  ]
};