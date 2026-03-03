import { Component, OnInit, inject, signal, input } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatGridListModule } from '@angular/material/grid-list';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatButtonModule } from '@angular/material/button';
import { UploadService } from '../../services/upload.service';

@Component({
  selector: 'app-project-gallery',
  standalone: true,
  imports: [CommonModule, MatGridListModule, MatCardModule, MatIconModule, MatChipsModule, MatButtonModule],
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
                  <span class="filename" [title]="img.original_filename">
                    {{ img.original_filename }}
                  </span>

                  @if (img.status === 'OPTIMIZED') {
                    <a mat-icon-button 
                       [href]="img.processed_image_url" 
                       [download]="img.original_filename"
                       target="_blank"
                       color="primary"
                       class="download-btn">
                      <mat-icon>download</mat-icon>
                    </a>
                  }
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
    
    /* FIX: Force card to be a flex container and occupy full tile height */
    .asset-card { 
      width: 100%; 
      height: 100%; 
      display: flex; 
      flex-direction: column; 
      overflow: hidden; 
    }

    /* FIX: image-wrapper grows to fill space, but doesn't push footer out */
    .image-wrapper { 
      position: relative; 
      flex: 1; 
      min-height: 0; /* Important for flex-grow in some browsers */
      width: 100%; 
      background: #2a2a2a; 
    }

    .image-wrapper img { width: 100%; height: 100%; object-fit: cover; transition: opacity 0.3s; }
    .pending img { opacity: 0.3; filter: blur(4px); }
    
    .status-overlay {
      position: absolute; inset: 0; display: flex; flex-direction: column;
      align-items: center; justify-content: center; color: white; gap: 8px;
    }
    .spin { animation: rotate 2s linear infinite; }
    @keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    
    .footer-content { 
      padding: 0 8px; 
      font-size: 12px; 
      display: flex; 
      align-items: center; 
      justify-content: space-between; 
      height: 48px; 
      background: white; /* Ensures button is always visible over dark wrapper */
    }

    .filename { 
      white-space: nowrap; 
      overflow: hidden; 
      text-overflow: ellipsis; 
      margin-right: 8px;
      flex: 1; /* Allows text to take available space */
    }

    .download-btn {
      flex-shrink: 0; /* Prevents the button from being squeezed */
      transform: scale(0.8);
    }
  `]
})
export class ProjectGalleryComponent implements OnInit {
  projectId = input.required<string>();
  private http = inject(HttpClient);
  private uploadService = inject(UploadService);
  images = signal<any[]>([]);

  constructor() {
    this.uploadService.refreshGallery$
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.loadImages());
  }

  ngOnInit() { this.loadImages(); }

  loadImages() {
    const url = `http://localhost/api/proxy/projects/${this.projectId()}/images/preview`;
    this.http.get<any[]>(url).subscribe(res => this.images.set(res));
  }
}