// src/main.ts
import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { AppComponent } from './app/app'; // <--- Change "App" to "AppComponent"

bootstrapApplication(AppComponent, appConfig) // <--- Use the correct class here
  .catch((err) => console.error(err));
