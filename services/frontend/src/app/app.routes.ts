import { Routes } from '@angular/router';

export const routes: Routes = [
    {
        path: 'profile',
        // Lazy load for better performance
        loadComponent: () => import('./components/profile/profile.component').then(m => m.ProfileComponent)
    },
    {
        path: '',
        redirectTo: 'profile',
        pathMatch: 'full'
    },
    {
        path: '**',
        redirectTo: 'profile'
    }
];
