// src/app/components/profile/profile.component.ts
import { Component, inject, OnInit } from '@angular/core';
import { ProfileService } from '../../services/profile.service';

@Component({
    selector: 'app-profile',
    standalone: true,
    template: `
    <div class="profile-container">
      @if (profile(); as user) {
        <div class="profile-card">
          <div class="avatar">
            {{ user.given_name[0] }}{{ user.family_name[0] }}
          </div>
          
          <h2>{{ user.name }}</h2>
          <p class="username">&#64;{{ user.preferred_username }}</p>
          
          <div class="details">
            <div class="item">
              <strong>Email:</strong> {{ user.email }}
              @if (user.email_verified) {
                <span class="verified">✓ Verified</span>
              } @else {
                <span class="unverified">⚠ Unverified</span>
              }
            </div>
          </div>
        </div>
      } @else {
        <div class="loading">Loading profile...</div>
      }
    </div>
  `,
    styles: [`
    .profile-card { padding: 20px; border-radius: 12px; border: 1px solid #ddd; max-width: 400px; }
    .avatar { width: 60px; height: 60px; background: #007bff; color: white; 
              border-radius: 50%; display: flex; align-items: center; 
              justify-content: center; font-size: 1.5rem; margin-bottom: 1rem; }
    .username { color: #666; font-style: italic; }
    .verified { color: green; font-size: 0.8rem; margin-left: 5px; }
    .unverified { color: #dc3545; font-size: 0.8rem; margin-left: 5px; }
  `]
})
export class ProfileComponent implements OnInit {
    private profileService = inject(ProfileService);

    // Expose the signal to the template
    profile = this.profileService.user;

    ngOnInit() {
        this.profileService.fetchProfile();
    }
}