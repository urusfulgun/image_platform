Considering information above, provide me with Use Cases, detailed planing and explanation of the following platform. Platform's name is "Image platform".
Image platform consists of the next services: Frontend Angular v21 Bun Nginx Reverse Proxy, BFF (Backend for Frontend) BFF Security Pattern proxy service (FastAPI on Python 3.14.2, python-keycloak and granian HTTP server), KeyCloak STS/IdP, AssetService (FastAPI on python 3.14.2, python-keycloak and granian HTTP server), Notification Worker, Image processing worker, Cleanup worker, RustFS S3 (S3 compatible API), Kafka Broker, Mailpit SMTP service, Postgres for AssetService, Postgres for KeyCloak STS/IdP, Debezium (events for shadow user creation in AssetService after user registration in KeyCloak), Redis for session storage (session ID -> session data).
Consider following structure of project's root folder:
- docker contains Dockerfile files and appropriate Dockerfile.dockerignore files.
- init-db contains SQL scripts for db initialization: postgres-image-metadata (related to AssetService).
- persistent_data (must be in .gitignore) contains data of the following:
	- Postgres container postgres-image-metadata and postgres-keycloak (related to KeyCloak).
	- kafka (Kafka broker)
	- rustfs
- secrets contains sersitive initial data for infrastructure (for example certificates and keys). It must be in .gitignore.
- services contains subfolders with appropriate services and workers: frontend, bff-token-handler, AssetService, image-processor, email-notification-service, shared-core.
Note: shared-core contains shared logic for python services (for example Pydantic models, types etc.)
Every python based service must contain also test folder besides of src. All tests must be written in pytest.
Keep in mind following draft.
1. Use Cases
The platform serves two primary personas: the End User (uploading and managing projects) and the System (automating background processing).

UC1: Secure Batch Upload
Actor: Registered User
Goal: Create a project and upload multiple high-resolution images.
Flow: The User authenticates via the BFF. The Angular frontend requests a pre-signed URL from the AssetService (via the BFF). The browser uploads raw images directly to RustFS S3.
UC2: Automated AVIF Conversion
Actor: Image Processing Worker
Goal: Convert all project images to .avif for optimal web delivery.
Flow: Once a batch upload is recorded in Postgres, a PROJECT_READY event is published to Kafka. The Worker picks up the task, performs the CPU-heavy conversion, and saves the result back to S3.
UC3: Lifecycle Notification
Actor: Notification Worker
Goal: Inform the user when their project is ready.
Flow: After the last image in a batch is converted, the Notification Worker triggers an email via Mailpit SMTP, providing a link to the project gallery.

2. Detailed Architecture Planning
Security: The BFF Token Handler Pattern
By using the BFF Security Pattern, your Angular v21 app never sees an OAuth access token.

KeyCloak handles the identity logic.
BFF acts as a confidential client. It exchanges the authorization code for tokens (session ID) and stores them in a server-side session.
The browser only receives a Secure, HttpOnly, SameSite cookie representing the session ID. This prevents malicious scripts from exfiltrating tokens.
Data Pipeline: Kafka & Workers
Kafka Broker: Acts as the central nervous system. It decouples the ingestion (upload) from the heavy processing (conversion).
RustFS S3: A high-performance, S3-compatible storage layer written in Rust. It stores the "Source" (raw) and "Destination" (AVIF) files.
Cleanup Worker: Periodically prunes the PostgreSQL and RustFS storage, removing raw source files after conversion or deleting expired projects to keep costs low.

3. Authentication & Identity Flow
The system uses KeyCloak as the source of truth, but keeps a "Shadow" copy of user data in the main application database for performance and relational integrity.
Handshake: The User Browser (Angular v21) communicates with the BFF via Nginx. The BFF manages the OAuth2 Code Flow with PKCE.
DPoP Binding: To prevent token theft, the BFF generates a DPoP (Demonstrating Proof-of-Possession) key pair. Access tokens issued by KeyCloak are bound to the BFF’s public key.
The "Shadow User" Sync: * When a user is registered in KeyCloak, a message is published to Kafka.
The AssetService consumes this message and creates a Shadow User in the PostgreSQL: APP database.
This allows us to link "Projects" and "Images" to a local user_id without calling KeyCloak for every database query.

4. The Image Processing Pipeline (Asynchronous)
Because converting images to .avif is CPU-intensive, we use a "Fire and Forget" approach from the user's perspective.

Stage 1: Ingestion
The BFF streams the uploaded batch to a "landing" bucket in RustFS S3.
The BFF writes a record to the Postgres DB with status PENDING.
A message is published to Kafka topic: image.raw.uploaded.

Stage 2: Conversion
The Image Processing Worker (the "Consumer") picks up the message.
It downloads the image, converts it to .avif, and uploads the result to the "processed" bucket in RustFS.
It publishes a message to Kafka topic: image.avif.ready.
Stage 3: Notification & Cleanup
The Notification Worker tracks the batch. When the last image in a project is processed, it generates an email.
The email is sent to Mailpit service (which acts as a mock SMTP for your dev/test environment).
The Cleanup Worker runs on a schedule to delete the "original" raw files from RustFS once the .avif conversion is confirmed and stored, saving disk space.

4. Database Planning
You have two distinct Postgres instances to maintain strict data isolation:
KeyCloak Postgres: Stores users, hashed passwords, client IDs, and OAuth configurations.
API/Application Postgres:
projects: id, user_id, status (Created, Processing, Completed).
batches: id, project_id, image_id 
images: id, project_id, raw_s3_path, raw_format_name, processed_s3_path, processed_format_name, status, error_log.

5. Summary of Security Benefits
XSS Protection: Since the access_token is never in the browser's LocalStorage or Memory, malicious scripts cannot steal it.
CSRF Protection: Using SameSite=Strict cookies and custom request headers (like X-Requested-With) at the BFF level.
Token Binding (DPoP): Even if the internal network is breached and an Access Token is stolen from Redis, it is useless without the private key held by the BFF.
Security: The BFF Token Handler Pattern
By using the BFF Security Pattern, your Angular v21 app never sees an OAuth access token.
KeyCloak handles the identity logic.
BFF acts as a confidential client. It exchanges the authorization code for tokens and stores them in a server-side session.
The browser only receives a Secure, HttpOnly, SameSite cookie representing the session ID. This prevents malicious scripts from exfiltrating tokens.

6. Data Pipeline: Kafka & Workers
Kafka Broker: Acts as the central nervous system. It decouples the ingestion (upload) from the heavy processing (conversion).
RustFS S3: A high-performance, S3-compatible storage layer written in Rust. It stores the "Source" (raw) and "Destination" (AVIF) files.
Cleanup Worker: Periodically prunes the PostgreSQL and RustFS storage, removing raw source files after conversion or deleting expired projects to keep costs low.
Notification Worker: tracks the notifications in Kafka. When the last image in a project is processed, it generates an email and sends it to the Mailpit.

7. Deployment Strategy
Identity Layer: Deploy KeyCloak and its Postgres DB first. Configure the realm and the BFF as a confidential client.
Core Services: Spin up Kafka and RustFS.
Application Layer: Deploy the BFF and AssetService. The BFF must share the same root domain as the Angular app to allow the secure cookie to work.
Worker Layer: Scale the Image Processing Worker horizontally depending on the CPU load of the AVIF conversions.

/image-platform
├── docker/                  # Dockerfiles for all services (Python 3.14.2 base)
├── init-db/                 # SQL scripts for AssetService schema
├── persistent_data/         # .gitignore (Postgres, Kafka, Redis, RustFS data)
├── secrets/                 # .gitignore (Certs, KeyCloak secrets, DPoP keys)
└── services/
    ├── shared-core/         # Shared Pydantic models (Message schemas, Error types)
    │   ├── src/
    │   └── tests/           # Pytest suite
    ├── frontend/            # Angular v21 + Bun + Nginx
    ├── bff-token-handler/   # FastAPI Security Proxy + Redis Client
    │   ├── src/
    │   └── tests/           # Pytest suite
    ├── asset-service/       # Business Logic + Pytest suite
    │   ├── src/
    │   └── tests/           # Pytest suite
    ├── image-processor/     # CPU-intensive Worker + Pytest
    │   ├── src/
    │   └── tests/           # Pytest suite
    └── email-notification/  # Notification Worker + Pytest
        ├── src/
        └── tests/           # Pytest suite

graph TD
    subgraph Client_Layer [Client & Edge]
        UA([User Browser])
        Nginx[Nginx Reverse Proxy]
        subgraph Frontend_Host [Bun Runtime]
            Angular[Angular v21 Material SPA]
        end
    end

    subgraph Identity_Auth [Identity & STS]
        KC[KeyCloak STS]
        DB_KC[(PostgreSQL: KeyCloak)]
    end

    subgraph Secure_Perimeter [BFF Layer]
        BFF[BFF: Token Handler Pattern]
    end

    subgraph Core_Services [Project Aggregate Domain]
        AS[AssetService: FastAPI / Granian]
        DB_APP[(PostgreSQL: Shadow Users, Projects, Metadata)]
        RFS[(RustFS S3: Raw & Processed)]
    end

    subgraph Async_Pipeline [Kafka Bus & Workers]
        KAF[[Kafka Broker]]
        IP[Image Processor: AVIF/HEIC]
        NS[Notification Service]
        MP[Mailpit: Test SMTP]
        CW[Cleanup Worker: Retention & Scrubber]
    end

    %% Auth Flow
    UA <-->|HTTPS / Secure Cookies| Nginx
    Nginx <--> Angular
    Nginx <--> BFF
    BFF <-->|OAuth2 + PKCE + DPoP| KC
    KC -.->|User Registered| KAF
    KAF -.->|Sync User| AS
    AS -.->|Create Shadow User| DB_APP

    %% Project & Image Flow
    BFF -->|Proxied Req + DPoP| AS
    AS -->|Metadata CRUD & ACLs| DB_APP
    AS -->|Signed Upload/Download URLs| RFS
    UA -.->|Direct S3 Upload| RFS
    
    %% Processing & Cleanup Flow
    AS -->|Batch Created / Item Deleted| KAF
    KAF -->|Process Image| IP
    IP <-->|Read Raw / Write Sizes| RFS
    IP -->|Processing Status| KAF
    KAF -->|Email Report| NS
    NS --> MP

    %% Cleanup Logic
    KAF -->|Cleanup Events| CW
    CW -->|Prune Metadata Events| KAF
    CW <-->|Delete Objects| RFS


