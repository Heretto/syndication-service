# Syndication Service Overview {#c_overview .concept}

The Syndication Service is a publishing pipeline that moves structured content from Heretto to external knowledge platforms automatically, on a schedule, or on demand.

Organizations that maintain content in Heretto and publish support documentation in Salesforce Knowledge face a recurring challenge: keeping both systems in sync without manual export and import steps or a custom conversion to create Salesforce Knowledge objects. The Syndication Service solves this by acting as a continuous bridge between the two platforms.[1](#fntarg_1)

## How it works { .section}

The service connects three layers:

Source — Heretto Deploy API
:   The service reads content from your Heretto deployment using the Deploy API. It tracks which topics have changed since the last successful run, so only new or updated content is transferred during incremental syncs. A full resync option is also available when you need to push all content regardless of change history.

Pipeline
:   Each topic is converted into a neutral intermediate format before it reaches the target. This step handles HTML sanitization, binary asset transfer, taxonomy extraction, and cross-article link resolution. The pipeline is target-agnostic, so the same source content can be routed to different platforms without modification.

    **Note:**

    Though the pipeline is target agnostic, in its current state the pipeline only currently supports publishing to Salesforce Knowledge.

Target — Salesforce Knowledge
:   Processed topics are created or updated as Salesforce Knowledge articles using the Salesforce REST API. The service handles the article lifecycle: draft creation, image upload, data category assignment, publishing, and archiving of articles that are removed from Heretto.

## The Syndication Service application { .section}

The web application provides a self-service interface for configuring and monitoring content syncs. From the application you can:

-   Create and manage sync configurations that pair a Heretto deployment with a Salesforce org
-   Map Heretto content fields to Salesforce Knowledge article fields
-   Map Heretto taxonomy values to Salesforce data category fields
-   Set a cron-based automatic schedule, or configure a sync to run on manual trigger only
-   Trigger incremental or full resyncs on demand
-   Monitor run history, article counts, and error messages
-   Manage organization members and credentials

Each sync configuration stores its own credentials and field mappings, so multiple Heretto deployments or multiple Salesforce orgs can be managed independently within the same application.

## Salesforce Knowledge integration { .section}

The service publishes content to Salesforce Knowledge using the Salesforce REST API with an OAuth 2.0 client credentials flow. Articles are created or updated independently using a custom external ID field that maps to the Heretto topic UUID, so re-running a sync never creates duplicate articles.

The following Salesforce Knowledge behaviors are supported:

-   **Article upsert** — creates a new draft article or updates an existing one based on the external ID
-   **Image upload** — binary assets are downloaded from Heretto and uploaded as Salesforce Content Versions, then rewritten inline in the article HTML
-   **Data category assignment** — Heretto taxonomy values are mapped to Salesforce data category selections on the article record
-   **Publish** — articles are published and made visible to end users after all content is loaded
-   **Archive** — articles removed from Heretto are unpublished in Salesforce Knowledge on the next sync

**Important:** Salesforce data category groups must be configured in Salesforce Setup before data category mappings take effect. The Syndication Service reads the available groups from your Salesforce org dynamically when you configure a sync.

## DITA content structure { .section}

Typically when a sync runs, a single DITA topic will become a single Salesforce Knowledge article.

One notable and important exception is when the chunk attribute is applied to a parent topic. If you set chunk="to-content" on a parent topic, the parent topic and all children will become a single Salesforce Knowledge article. This enables you to create small, modular topics in Heretto CCMS while still generating longer, standalone Salesforce Knowledge articles.

[1](#fnsrc_1) Heretto Open Projects are not Heretto services or products. They are open source projects that are subject to Heretto's [terms of use](https://herettoopenprojects.ai/terms-of-use/).

