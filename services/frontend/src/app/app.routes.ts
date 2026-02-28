import { Routes } from '@angular/router';

export const routes: Routes = [
    {
        path: 'profile',
        // Lazy load for better performance
        loadComponent: () => import('./components/profile/profile.component').then(m => m.ProfileComponent)
    },
    {
        path: 'projects',
        loadComponent: () => import('./components/project/project-list.component').then(m => m.ProjectListComponent),
        title: 'My Projects'
    },
    {
        path: 'upload/:projectId',
        loadComponent: () => import('./components/project/project-upload.component').then(m => m.ProjectUploadComponent),
        title: 'Upload Images'
    },
    {
        path: '',
        redirectTo: 'projects',
        pathMatch: 'full'
    },
    {
        path: '**',
        redirectTo: 'profile'
    }
];
