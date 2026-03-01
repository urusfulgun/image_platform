// src/app/pages/project/project-gallery.component.ts
import { Component, OnInit, inject, signal, input } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatGridListModule } from '@angular/material/grid-list';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { UploadService } from '../../services/upload.service';

@Component({
  selector: 'app-project-gallery',
  standalone: true,
  imports: [CommonModule, MatGridListModule, MatCardModule, MatIconModule, MatChipsModule],
  template: `
    <div class="gallery-view">
      <header>
        <h3>Project Assets</h3>
        <p class="subtitle">ID: {{ projectId() }}</p>
      </header>

      <mat-grid-list cols="4" rowHeight="1:1" gutterSize="16px">
        @for (img of images(); track img.id) {
          <mat-grid-tile>
            <mat-card class="asset-card">
              <div class="image-wrapper" [class.pending]="img.status === 'PENDING'">
                <img [src]="img.display_url" [alt]="img.original_filename">
                
                @if (img.status === 'PENDING') {
                  <div class="status-overlay">
                    <mat-icon class="spin">sync</mat-icon>
                    <span>Processing</span>
                  </div>
                }
              </div>
              
              <mat-card-footer>
                <div class="footer-content">
                  <span class="filename">{{ img.original_filename }}</span>
                </div>
              </mat-card-footer>
            </mat-card>
          </mat-grid-tile>
        }
      </mat-grid-list>
      
      @if (images().length === 0) {
        <div class="empty-state">
          <mat-icon>photo_library</mat-icon>
          <p>No images uploaded yet.</p>
        </div>
      }
    </div>
  `,
  styles: [`
    .gallery-view { padding: 24px; }
    .asset-card { width: 100%; height: 100%; overflow: hidden; }
    .image-wrapper { position: relative; height: 100%; width: 100%; background: #2a2a2a; }
    .image-wrapper img { width: 100%; height: 100%; object-fit: cover; transition: opacity 0.3s; }
    .pending img { opacity: 0.3; filter: blur(4px); }
    
    .status-overlay {
      position: absolute; inset: 0; display: flex; flex-direction: column;
      align-items: center; justify-content: center; color: white; gap: 8px;
    }
    .spin { animation: rotate 2s linear infinite; }
    @keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    
    .footer-content { padding: 8px; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  `]
})
export class ProjectGalleryComponent implements OnInit {
  projectId = input.required<string>();
  private http = inject(HttpClient);

  private uploadService = inject(UploadService);
  
  images = signal<any[]>([]);

  constructor() {
    // Listen for refresh signals throughout the component lifecycle
    this.uploadService.refreshGallery$
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        this.loadImages(); // Refresh the list from the Python BFF
      });
  }

  ngOnInit() {
    this.loadImages();
  }

  loadImages() {
    const url = `http://localhost/api/proxy/projects/${this.projectId()}/images/preview`;
    this.http.get<any[]>(url).subscribe(res => this.images.set(res));
  }
}