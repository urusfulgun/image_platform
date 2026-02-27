// src/app/services/profile.service.ts
import { Injectable, signal, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { UserProfileResponse, IdToken } from '../models/user.model';
import { tap } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ProfileService {
    private http = inject(HttpClient);

    // Initialize with null
    user = signal<IdToken | null>(null);

    fetchProfile() {
        this.http.get<UserProfileResponse>('/api/me').subscribe({
            next: (res) => this.user.set(res.id_token),
            error: (err) => console.error('Failed to load profile', err)
        });
    }
    logout() {
        // We call the BFF via POST to ensure CSRF protection and 
        // allow the BFF to sign the DPoP revocation request.
        return this.http.post<{ logoutUrl: string }>('/api/logout', {}).pipe(
            tap(response => {
                // Once the BFF has cleared local cookies/sessions, 
                // we redirect to Keycloak to end the SSO session.
                if (response.logoutUrl) {
                    window.location.href = response.logoutUrl;
                }
            })
        );
    }
}
