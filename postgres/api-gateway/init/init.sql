-- 1. Identity Layer: Shadow Users (Unchanged)
CREATE TABLE shadow_users (
    user_id UUID PRIMARY KEY,
    keycloak_sub VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. Aggregate Root: Projects (Unchanged)
CREATE TABLE projects (
    project_id UUID PRIMARY KEY,
    owner_id UUID NOT NULL REFERENCES shadow_users(user_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    naming_template VARCHAR(500),
    target_resolutions JSONB NOT NULL DEFAULT '["normal"]',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. ACL: Shared Read Access (Unchanged)
CREATE TABLE project_access_control (
    access_id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    grantee_user_id UUID NOT NULL REFERENCES shadow_users(user_id) ON DELETE CASCADE,
    access_level VARCHAR(50) NOT NULL DEFAULT 'READ_ONLY',
    granted_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, grantee_user_id)
);

-- 4. Batches: Replaced batch_status ENUM
CREATE TABLE batch_statuses (
    status_id TEXT PRIMARY KEY -- 'PENDING', 'PROCESSING', etc.
);

INSERT INTO batch_statuses (status_id) VALUES ('PENDING'), ('PROCESSING'), ('COMPLETED'), ('FAILED');

CREATE TABLE batches (
    batch_id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'PENDING' REFERENCES batch_statuses(status_id) ON UPDATE CASCADE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 5. Image Metadata: Replaced image_status ENUM
CREATE TABLE image_statuses (
    status_id TEXT PRIMARY KEY -- 'UPLOADED', 'CONVERTED', 'ERROR'
);

INSERT INTO image_statuses (status_id) VALUES ('UPLOADED'), ('CONVERTED'), ('ERROR');

CREATE TABLE image_metadata (
    image_id UUID PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES batches(batch_id) ON DELETE CASCADE,
    owner_id UUID NOT NULL REFERENCES shadow_users(user_id),
    original_filename VARCHAR(500) NOT NULL,
    display_name VARCHAR(500) NOT NULL,
    file_extension VARCHAR(10) NOT NULL,
    status TEXT NOT NULL DEFAULT 'UPLOADED' REFERENCES image_statuses(status_id) ON UPDATE CASCADE,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 6. Conversion Variants: Replaced resolution_type ENUM
CREATE TABLE resolution_types (
    res_id TEXT PRIMARY KEY -- 'NORMAL', 'PREVIEW', 'THUMBNAIL'
);

INSERT INTO resolution_types (res_id) VALUES ('NORMAL'), ('PREVIEW'), ('THUMBNAIL');

CREATE TABLE image_variants (
    variant_id UUID PRIMARY KEY,
    parent_image_id UUID NOT NULL REFERENCES image_metadata(image_id) ON DELETE CASCADE,
    res_type TEXT NOT NULL REFERENCES resolution_types(res_id) ON UPDATE CASCADE,
    s3_path TEXT NOT NULL,
    file_size_bytes BIGINT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 7. Performance Indexes (Unchanged)
CREATE INDEX idx_projects_owner ON projects(owner_id);
CREATE INDEX idx_batches_project ON batches(project_id);
CREATE INDEX idx_image_metadata_batch ON image_metadata(batch_id);
CREATE INDEX idx_image_variants_parent ON image_variants(parent_image_id);
CREATE INDEX idx_acl_grantee ON project_access_control(grantee_user_id);