# Sync History {#c_run_history .concept}

The Sync History page shows the results of all syncs across all sync-configurations in your organization, allowing you to monitor publishing activity and investigate errors.

Click **Sync History** in the navigation menu to open the Sync History page. Each row in the table represents one sync and shows:

-   A status badge indicating the outcome of the sync
-   The name of the Sync
-   The date and time the sync started, displayed in your local timezone
-   The number of articles changed during the sync, when available
-   The number of articles removed during the sync, when available

    See [How removed content is handled during a sync](c_deleting-topics-from-a-deployment.md) for details on how removed content is handled.

-   Warning messages, when one or more articles could not be fully processed

    For example, if a stale article could not be archived in Salesforce during a full resync, a warning is recorded here. The sync still completes successfully — warnings indicate items that require manual follow-up in Salesforce Knowledge.

-   The number of cross-reference links fixed during the sync, when available


## Run statuses {#section_run_statuses .section}

Each run is assigned one of the following statuses:

Pending
:   The sync has been queued and is waiting to start.

Running
:   The sync is actively processing content. Do not trigger another sync for this connection until the previous one completes.

Completed
:   The sync finished successfully. All changed content was processed and published to the target system.

Failed
:   The sync encountered a problem that prevented it from completing. An error message is recorded with the sync. Check your Sync configuration and credentials, then trigger the sync again.

Error
:   An unexpected error occurred during the sync. An error message is recorded with the sync. If the problem persists after retrying, contact your system administrator.

## Changed count {#section_changed_count .section}

The changed count reflects the number of articles that were created or updated in the target system during the sync. A count of zero on a completed sync is normal when no content has changed in Heretto CCMS since the previous sync.

**Tip:** A full resync reflects the total number of articles processed, not the number of newly changed articles.

