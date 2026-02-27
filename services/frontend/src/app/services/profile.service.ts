// src/app/services/profile.service.ts
import { Injectable, signal, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { UserProfileResponse, IdToken } from '../models/user.model';

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
}
