// src/app/components/uploader.component.ts
import { Component, signal, inject, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatIconModule } from '@angular/material/icon';
import { UploadService } from '../services/upload.service';

@Component({
    selector: 'app-uploader',
    standalone: true,
    imports: [CommonModule, MatButtonModule, MatProgressBarModule, MatIconModule],
    template: `
    <div class="upload-container">
      <input type="file" #fileInput (change)="onFileSelected(fileInput.files)" hidden />
      
      <button mat-raised-button color="primary" (click)="fileInput.click()" [disabled]="uploading()">
        <mat-icon>cloud_upload</mat-icon> Select File
      </button>

      @if (fileName()) {
        <p>Selected: {{ fileName() }}</p>
        <mat-progress-bar mode="determinate" [value]="progress()"></mat-progress-bar>
        <button mat-button (click)="startUpload()" [disabled]="uploading() || progress() === 100">
          Start Upload
        </button>
      }
    </div>
  `
})
export class UploaderComponent {
    private uploadService = inject(UploadService);

    selectedFile = signal<File | null>(null);
    fileName = signal<string>('');
    progress = signal<number>(0);
    uploading = signal<boolean>(false);
    projectId = input.required<string>();

    onFileSelected(files: FileList | null) {
        if (files && files.length > 0) {
            this.selectedFile.set(files[0]);
            this.fileName.set(files[0].name);
            this.progress.set(0);
        }
    }

    startUpload() {
        const file = this.selectedFile();
        if (!file) return;

        this.uploading.set(true);

        // 1. Get Link -> 2. Upload
        this.uploadService.getPresignedUrl(this.projectId(), file).subscribe({
            next: ({ upload_url }) => {
                this.uploadService.uploadToPresignedUrl(upload_url, file).subscribe({
                    next: (p) => {
                        this.progress.set(p);
                        this.uploadService.notifyUploadComplete();
                    },
                    complete: () => this.uploading.set(false),
                    error: () => this.uploading.set(false)
                });
            }
        });
    }

    isDragging = signal<boolean>(false);

    onDragOver(event: DragEvent) {
        event.preventDefault();
        event.stopPropagation();
        this.isDragging.set(true);
    }

    onDragLeave(event: DragEvent) {
        event.preventDefault();
        event.stopPropagation();
        this.isDragging.set(false);
    }

    onDrop(event: DragEvent) {
        event.preventDefault();
        event.stopPropagation();
        this.isDragging.set(false);

        if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
            this.onFileSelected(event.dataTransfer.files);
        }
    }
}
