# image_platform
```text
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
```

Image storage and processing project.
```mermaid
graph TD
    %% Global Styles
    classDef client fill:#e1f5fe,stroke:#01579b,stroke-width:2px,color:#000;
    classDef auth fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000;
    classDef bff fill:#f3e5f5,stroke:#4a148c,stroke-width:2px,color:#000;
    classDef core fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px,color:#000;
    classDef async fill:#fffde7,stroke:#f57f17,stroke-width:2px,color:#000;
    classDef storage fill:#eceff1,stroke:#455a64,stroke-width:2px,color:#000;

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

    %% Apply Classes
    class UA,Nginx,Angular client;
    class KC,DB_KC auth;
    class BFF bff;
    class AS,DB_APP core;
    class RFS storage;
    class KAF,IP,NS,MP,CW async;

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
```