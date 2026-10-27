# Mission

Image Platform is a portfolio project. It shows that I can design and build a secure, event-driven, multi-service system in which the browser never holds a token, and that I can prove the design holds up rather than just claim it.

## Audience

- **Primary: security-minded reviewers.** They judge whether the auth and identity design is correct, and that judgment decides everything else.
- **Technical interviewers.** They clone the repo, read the code and probe the trade-offs.
- **Backend and platform hiring managers.** They look for signals of architecture, ownership and judgment.
- **Recruiters.** They need a clear README and a stack that starts with one command.

## What it proves

1. **Modern auth and security (the headline).**
   - Keycloak sits behind a confidential BFF that uses PKCE and DPoP-bound tokens, held only in server-side Redis sessions.
   - The claim is backed by a threat model, automated security tests (impersonation, DPoP replay, expired tokens, webhook auth) and dependency, SAST and container scans in CI.
   - Known holes are closed before anything is showcased.
2. **Event-driven system design.**
   - Kafka pipelines, Debezium CDC, DLQs, and independent workers that fail safely.
3. **Production engineering discipline.**
   - Tests in every service, CI, `mypy --strict`, migrations, pinned images and centralised logs.
4. **Full-stack delivery.**
   - An Angular 21 SPA, async Python services, Postgres, S3 storage and email, all working end to end.

**Privacy by design.** There are no real users, but GDPR principles still apply:

- **Data minimisation:** store only the user fields that are needed, and keep tokens and PII out of logs.
- **Retention limits:** sessions, raw images, logs and Kafka topics all have defined lifetimes.
- **Data export:** a user can download their projects and images.
- **Right to erasure:** deleting a Keycloak user removes their DB rows and S3 objects.

## Differentiators

- **The browser never holds a token.** A BFF and sender-constrained DPoP tokens replace the usual JWTs in `localStorage`.
- **Users are synced by CDC.** Debezium streams Keycloak users into the service database, with no polling and no shared database.
- **The stack is realistic.** About 20 containers, observability included, start locally with `make up`.
- **Decisions are documented.** Specs, the roadmap and the threat model show how the system evolved and why.

## Non-goals

- Real production hosting: no public deployment, uptime targets, scaling or cloud cost work. A one-command local run is how people experience it.
- Real users or SaaS features: no billing, multi-tenancy or quotas. GDPR principles still apply, as described above.
- Kubernetes or IaC: Docker Compose only, so no Helm, Terraform or k8s manifests.
- Mobile or native clients: the web SPA is the only client.
