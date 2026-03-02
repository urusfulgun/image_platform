-- 1. Shadow Users Table (Static-ish)
-- Populated via Debezium/Kafka sync from Keycloak
CREATE TABLE users (
    id UUID PRIMARY KEY,
    kc_sub UUID UNIQUE NOT NULL, -- Keycloak Subject ID
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Projects Table (Low volatility)
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Static Metadata Table (Insert-Only)
-- This table contains heavy data. We want ZERO updates here.
CREATE TABLE image_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    original_filename VARCHAR(255) NOT NULL,
    raw_format VARCHAR(255),
    raw_s3_path TEXT NOT NULL,
    processed_format VARCHAR(255),
    processed_s3_path TEXT,
    file_size_bytes BIGINT,
    dimensions_px VARCHAR(20), -- e.g., '1920x1080'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Volatile Status Table (High volatility)
-- This table is designed for HOT (Heap-Only Tuple) updates.
CREATE TABLE image_processing_status (
    image_id UUID PRIMARY KEY REFERENCES image_metadata(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL, -- 'PENDING', 'PROCESSING', 'OPTIMIZED', 'FAILED'
    retry_count INT DEFAULT 0,
    last_error_log TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
) WITH (fillfactor = 80); 
-- Fillfactor 80 leaves 20% of each page empty for row updates.

-- Create an index for the Notification Worker to find completed batches
CREATE INDEX idx_status_lookup ON image_processing_status(status);

ALTER TABLE image_metadata 
    ADD COLUMN IF NOT EXISTS raw_format VARCHAR(255),
    ADD COLUMN IF NOT EXISTS processed_format VARCHAR(255);
