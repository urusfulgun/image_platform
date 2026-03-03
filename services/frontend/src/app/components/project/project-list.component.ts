import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { RouterLink } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-project-list',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    RouterLink,
    MatIconModule
  ],
  template: `
    <div class="view-wrapper">
      @if (projects().length === 0) {
        <mat-card class="upload-card">
          <mat-card-content class="empty-state">
            <mat-icon color="primary" style="font-size: 48px; width: 48px; height: 48px;">folder_open</mat-icon>
            <h3>No Projects Found</h3>
            <p>Create a project to start uploading images to RustFS.</p>
            <button mat-raised-button color="primary" (click)="createProject()">
              Create First Project
            </button>
          </mat-card-content>
        </mat-card>
      } @else {
        <mat-card class="upload-card">
          <mat-card-content class="empty-state">
            <mat-icon color="primary" style="font-size: 48px; width: 48px; height: 48px;">folder_open</mat-icon>
            <h3>{{projects().length}} Projects Found</h3>
            <p>Create a project to start uploading images to RustFS.</p>
            <button mat-raised-button color="primary" (click)="createProject()">
              Create Project
            </button>
          </mat-card-content>
        </mat-card>
        <div class="project-grid">
          @for (p of projects(); track p.id) {
            <mat-card class="project-card">
              <mat-card-header>
                <mat-card-title>{{ p.name }}</mat-card-title>
              <mat-card-subtitle>Created in Python 3.14</mat-card-subtitle>
            </mat-card-header>
            <mat-card-actions>
              <button mat-flat-button color="primary" [routerLink]="['/upload', p.id]">
                Upload Images
              </button>
            </mat-card-actions>
          </mat-card>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .empty-state { text-align: center; padding: 40px; }
    .project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
  `]
})
export class ProjectListComponent implements OnInit {
  private http = inject(HttpClient);
  projects = signal<any[]>([]);

  ngOnInit() { this.load(); }

  load() {
    this.http.get<any[]>('/api/proxy/projects/').subscribe(res => this.projects.set(res));
  }

  createProject() {
    const name = prompt('Project Name:');
    if (name) {
      this.http.post('/api/proxy/projects/', { name }).subscribe(() => this.load());
    }
  }
}