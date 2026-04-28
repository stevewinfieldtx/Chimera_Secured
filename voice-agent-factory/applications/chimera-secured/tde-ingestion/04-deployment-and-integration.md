# Deployment and Integration

## How Chimera Secured Is Deployed

Chimera Secured deploys as a Docker container stack inside or alongside the customer's Microsoft 365 environment. The deployment consists of two containers: a PostgreSQL 16 database that stores CPP metadata and recipient labels, and the CPA service itself which runs the enrollment, scoring, and dashboard. The entire deployment is managed through a single docker-compose command that starts both services, configures the database, and auto-seeds the background corpus on first boot.

Deployment takes about 30 minutes from start to first enrolled user. The MSP clones the repository, fills in four environment variables — an API key and three Azure AD credentials — runs docker compose up, and the system is operational. No additional infrastructure, no cloud subscriptions beyond the existing M365 tenant, no complex networking.

## Azure AD Integration

Chimera Secured connects to Microsoft 365 through the Graph API to read sent email history during enrollment. The MSP creates an Azure AD app registration with Mail.Read application permission and grants admin consent. This gives CPA read-only access to sent mailboxes across the tenant. The three values from the app registration — tenant ID, client ID, and client secret — go into the environment configuration file.

The Graph API connection is used only during enrollment to pull historical sent emails. It is not used during real-time scoring. Scoring operates on emails as they flow through the Exchange transport pipeline, which is a separate integration point.

## Integration With Microsoft 365

Chimera Secured integrates with Microsoft 365 through two modes. Warn mode, which is the recommended starting point for every pilot, uses a Graph subscription on sent items. Emails are scored after delivery, and the system logs verdicts and alerts administrators when suspicious activity is detected. This mode works with any M365 account type and requires no Exchange admin privileges.

Enforce mode uses an Exchange Online transport rule and connector to intercept outbound mail before delivery. The email is held, scored against the sender's CPP, and either allowed through or quarantined based on the verdict. This mode requires Exchange admin access and is deployed only after the pilot has established a reliable false positive rate.

Every deployment starts in warn mode. The MSP earns the right to move to enforce mode by demonstrating accuracy with real-world data.

## What The MSP Manages

The MSP handles the initial deployment, Azure AD configuration, and ongoing management through the CPA dashboard. The dashboard provides enrollment controls, scoring results, profile status monitoring, and a labeling interface where administrators can review and correct how the system classifies recipients into formality tiers. The MSP can enroll new users, check profile health, review scoring activity, and generate voice profiles — all from the browser-based dashboard or via the REST API.

## System Requirements

Chimera Secured requires Docker and Docker Compose installed on the host machine, plus an Azure AD tenant with administrative access for the app registration. The CPA container runs on standard Linux with Python, and the PostgreSQL database stores metadata in a persistent Docker volume. Resource requirements are modest — suitable for a small VM or even a developer workstation during pilot. The system supports up to approximately 50 users on the default SQLite backend, with PostgreSQL recommended for larger deployments.

## API Access

All CPA functionality is available through a REST API secured with an API key. The API supports enrollment from Graph, direct enrollment from provided emails, email scoring, CPP status checks, voice profile generation, and recipient label management. Interactive API documentation is available at the /docs endpoint via Swagger UI. The API key is set in the environment configuration and must be included as an X-API-Key header on all requests except health checks and the dashboard.
