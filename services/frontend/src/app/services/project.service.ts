// src/app/services/project.service.ts
import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { tap } from 'rxjs';

export interface Project {
  id: string;
  name: string;
}

@Injectable({ providedIn: 'root' })
export class ProjectService {
  private http = inject(HttpClient);
  private API_URL = 'http://localhost:80/api/proxy/projects'; // BFF URL

  projects = signal<Project[]>([]);

  loadProjects() {
    return this.http.get<Project[]>(this.API_URL).pipe(
      tap(data => this.projects.set(data))
    );
  }

  createProject(name: string) {
    return this.http.post<Project>(this.API_URL, { name }).pipe(
      tap(newProj => this.projects.update(p => [...p, newProj]))
    );
  }
}