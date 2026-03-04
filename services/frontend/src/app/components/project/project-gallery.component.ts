import { Component, OnInit, inject, signal, input, DestroyRef } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { BreakpointObserver, Breakpoints } from '@angular/cdk/layout';
import { MatGridListModule } from '@angular/material/grid-list';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatButtonModule } from '@angular/material/button';
import { UploadService } from '../../services/upload.service';
import { DownloadService } from '../../services/download.service';
import { MatProgressBarModule } from '@angular/material/progress-bar'; // Optional for progress UI
import { Subject, timer, switchMap, takeUntil, tap, takeWhile, catchError, of, map } from 'rxjs';

@Component({
  selector: 'app-project-gallery',
  standalone: true,
  imports: [CommonModule, MatGridListModule, MatCardModule, MatIconModule, MatChipsModule, MatButtonModule, MatProgressBarModule],
  template: `
    <div class="gallery-view">
      <header>
        <h3>Project Assets</h3>
        <p class="subtitle">ID: {{ projectId() }}</p>
        <div class="header-actions">
        @if (images().length > 0) {
          <button mat-flat-button 
                  color="primary" 
                  [disabled]="downloadService.isDownloading()"
                  (click)="downloadAll()">
            <mat-icon>{{ downloadService.isDownloading() ? 'sync' : 'archive' }}</mat-icon>
            {{ downloadService.isDownloading() ? 'Bundling...' : 'Download All (ZIP)' }}
          </button>
        }
      </div>
      </header>

      @if (downloadService.isDownloading()) {
        <mat-progress-bar mode="indeterminate" class="download-progress"></mat-progress-bar>
      }

      <mat-grid-list [cols]="columnCount()" rowHeight="1:1" gutterSize="16px">
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

                  <div class="actions">
                    @if (img.status === 'OPTIMIZED') {
                      <a mat-icon-button 
                         [href]="img.processed_image_url" 
                         [download]="img.original_filename"
                         target="_blank"
                         color="primary"
                         class="action-btn">
                        <mat-icon>download</mat-icon>
                      </a>
                    }
                    
                    <button mat-icon-button 
                            color="warn" 
                            class="action-btn"
                            (click)="deleteImage(img.id)">
                      <mat-icon>delete_outline</mat-icon>
                    </button>
                  </div>
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
    .gallery-view { padding: 24px; max-width: 1400px; margin: 0 auto; }
    .asset-card { width: 100%; height: 100%; display: flex; flex-direction: column; overflow: hidden; }
    .image-wrapper { position: relative; flex: 1; min-height: 0; width: 100%; background: #2a2a2a; }
    .image-wrapper img { width: 100%; height: 100%; object-fit: cover; transition: opacity 0.3s; }
    .pending img { opacity: 0.3; filter: blur(4px); }
    .status-overlay { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; color: white; gap: 8px; }
    .spin { animation: rotate 2s linear infinite; }
    @keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    .footer-content { padding: 0 8px; font-size: 12px; display: flex; align-items: center; justify-content: space-between; height: 48px; background: white; }
    .filename { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-right: 8px; flex: 1; }
    .actions { display: flex; gap: 4px; align-items: center; }
    .action-btn { flex-shrink: 0; transform: scale(0.8); }

    @media (max-width: 600px) {
      .gallery-view { padding: 12px; }
      .footer-content { height: 40px; font-size: 11px; }
    }
    /* Add to your component styles */
    .gallery-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 24px;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .download-progress {
      margin-bottom: 16px;
      border-radius: 4px;
    }

    .empty-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 60px;
      color: #666;
    }

    .empty-state mat-icon {
      font-size: 48px;
      width: 48px;
      height: 48px;
      margin-bottom: 16px;
    }
  `]
})
export class ProjectGalleryComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly uploadService = inject(UploadService);
  protected readonly downloadService = inject(DownloadService); // Inject our new service
  private readonly destroyRef = inject(DestroyRef);
  private readonly breakpointObserver = inject(BreakpointObserver);

  projectId = input.required<string>();
  images = signal<any[]>([]);
  private stopPolling$ = new Subject<void>();

  columnCount = toSignal(
    this.breakpointObserver
      .observe([Breakpoints.XSmall, Breakpoints.Small, Breakpoints.Medium, Breakpoints.Large])
      .pipe(
        map(result => {
          if (result.breakpoints[Breakpoints.XSmall]) return 1;
          if (result.breakpoints[Breakpoints.Small]) return 2;
          if (result.breakpoints[Breakpoints.Medium]) return 3;
          return 4;
        })
      ),
    { initialValue: 4 }
  );

  constructor() {
    this.uploadService.refreshGallery$
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.startPolling());
  }

  ngOnInit() {
    this.startPolling();
  }

  deleteImage(imageId: string) {
    const url = `http://localhost/api/proxy/projects/${this.projectId()}/images/${imageId}`;

    // Optimistic UI update or simple request handling
    this.http.delete(url)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          // Remove from local signal to provide immediate feedback
          this.images.update(imgs => imgs.filter(i => i.id !== imageId));
        },
        error: (err) => console.error('Delete failed', err)
      });
  }

  startPolling() {
    this.stopPolling$.next();
    timer(0, 3000)
      .pipe(
        switchMap(() => this.fetchImages().pipe(
          catchError(() => of(this.images()))
        )),
        tap(res => this.images.set(res)),
        takeWhile(res => res.some(img => img.status === 'PENDING'), true),
        takeUntil(this.stopPolling$),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe();
  }

  downloadAll() {
    // 1. Prepare assets with POSIX paths
    const assets = this.images()
      .filter(img => img.status === 'OPTIMIZED')
      .map(img => {
      const baseName = img.path || img.original_filename;
      const newExt = img.processed_format.toLowerCase();
      
      // 1. Remove the old extension using regex
      // This matches the last '.' and everything after it, but only at the end of the string
      const nameWithoutExt = baseName.replace(/\.[^/.]+(?=$)/, '');
      
      // 2. Append the new extension
      const finalFilename = `${nameWithoutExt}.${newExt}`;

      return {
        url: img.processed_image_url,
        filename: finalFilename
      };
    });

    if (assets.length > 0) {
      this.downloadService.downloadAllDirectly(assets);
    }
  }

  private fetchImages() {
    const url = `http://localhost/api/proxy/projects/${this.projectId()}/images/preview`;
    return this.http.get<any[]>(url);
  }
}