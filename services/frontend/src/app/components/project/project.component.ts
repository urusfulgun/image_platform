// src/app/pages/project-list.component.ts
import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { RouterLink } from '@angular/router';
import { ProjectService } from '../../services/project.service';
import { MatIconModule } from '@angular/material/icon';

@Component({
    standalone: true,
    imports: [
        CommonModule,
        MatButtonModule,
        MatCardModule,
        RouterLink,
        MatIconModule
    ],
    template: `
    <div class="main-container">
      @if (projectService.projects().length === 0) {
        <mat-card class="upload-card">
          <mat-card-header><mat-card-title>No Projects Yet</mat-card-title></mat-card-header>
          <mat-card-content>
            <p>Create your first project to start uploading images to RustFS.</p>
            <button mat-raised-button color="primary" (click)="createProject()">
              Create Project
            </button>
          </mat-card-content>
        </mat-card>
      } @else {
        <div class="project-grid">
          @for (project of projectService.projects(); track project.id) {
            <mat-card class="project-item">
              <mat-card-header><mat-card-title>{{ project.name }}</mat-card-title></mat-card-header>
              <mat-card-actions>
                <button mat-button color="accent" [routerLink]="['/upload', project.id]">
                  Upload Images
                </button>
              </mat-card-actions>
            </mat-card>
          }
          <button mat-fab color="primary" (click)="createProject()" class="fab-bottom">
            <mat-icon>add</mat-icon>
          </button>
        </div>
      }
    </div>
  `
})
export class ProjectListComponent implements OnInit {
    projectService = inject(ProjectService);

    ngOnInit() { this.projectService.loadProjects().subscribe(); }

    createProject() {
        const name = prompt('Project Name:');
        if (name) this.projectService.createProject(name).subscribe();
    }
}