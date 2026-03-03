import { Component, OnInit, inject, signal, input, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatGridListModule } from '@angular/material/grid-list';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatButtonModule } from '@angular/material/button';
import { UploadService } from '../../services/upload.service';
import { Subject, timer, switchMap, takeUntil, tap, takeWhile, catchError, of } from 'rxjs';

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
    .asset-card { width: 100%; height: 100%; display: flex; flex-direction: column; overflow: hidden; }
    .image-wrapper { position: relative; flex: 1; min-height: 0; width: 100%; background: #2a2a2a; }
    .image-wrapper img { width: 100%; height: 100%; object-fit: cover; transition: opacity 0.3s; }
    .pending img { opacity: 0.3; filter: blur(4px); }
    .status-overlay { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; color: white; gap: 8px; }
    .spin { animation: rotate 2s linear infinite; }
    @keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    .footer-content { padding: 0 8px; font-size: 12px; display: flex; align-items: center; justify-content: space-between; height: 48px; background: white; }
    .filename { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-right: 8px; flex: 1; }
    .download-btn { flex-shrink: 0; transform: scale(0.8); }
  `]
})
export class ProjectGalleryComponent implements OnInit {
  // 1. Move all injections to the top level (Injection Context)
  private readonly http = inject(HttpClient);
  private readonly uploadService = inject(UploadService);
  private readonly destroyRef = inject(DestroyRef);

  projectId = input.required<string>();
  images = signal<any[]>([]);
  
  // Subject used to cancel the existing poll if a new one is triggered
  private stopPolling$ = new Subject<void>();

  constructor() {
    // Listen for manual refreshes from the upload service
    this.uploadService.refreshGallery$
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.startPolling());
  }

  ngOnInit() {
    this.startPolling();
  }

  /**
   * Refreshes the gallery every 3 seconds as long as any image is 'PENDING'
   */
  startPolling() {
    // Stop any timer currently running
    this.stopPolling$.next();

    timer(0, 3000)
      .pipe(
        switchMap(() => this.fetchImages().pipe(
          catchError(() => of(this.images())) // On error, keep existing images and try again
        )),
        tap(res => this.images.set(res)),
        // 2. Logic: Continue polling while at least one image is PENDING.
        // The 'true' parameter ensures the final "all OPTIMIZED" emission updates the UI.
        takeWhile(res => res.some(img => img.status === 'PENDING'), true),
        takeUntil(this.stopPolling$),
        // Pass destroyRef since we are potentially subscribing outside the constructor
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe();
  }

  private fetchImages() {
    const url = `http://localhost/api/proxy/projects/${this.projectId()}/images/preview`;
    return this.http.get<any[]>(url);
  }
}