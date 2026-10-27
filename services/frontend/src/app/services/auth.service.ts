// src/app/services/auth.service.ts
// src/app/services/auth.service.ts
import { Injectable, inject, signal } from '@angular/core'; // Added 'inject' here
import { HttpClient } from '@angular/common/http';

@Injectable({
    providedIn: 'root'
})
export class AuthService {
    private http = inject(HttpClient);
    user = signal<any>(null);

    checkAuth() {
        this.http.get('http://image-platform:8000/me', { withCredentials: true })
            .subscribe({
                next: (data) => this.user.set(data),
                error: () => this.user.set(null)
            });
    }
}
