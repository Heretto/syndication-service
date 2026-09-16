# Trigger an Incremental Sync {#t_trigger_sync .task}

Trigger a sync immediately to publish content that has changed in Heretto CCMS since the last successful run, without waiting for the next scheduled run.

You need to publish your Deployment in Heretto CCMS prior to running a sync for the syndication service to pick up the latest content changes from Deploy API.

An incremental sync run fetches only the content that has changed since the previous successful run. This is the most efficient way to keep your target system up to date and is safe to trigger at any time.

If you need to reprocess all content regardless of change date, use [Force a Full Resync](t_force_full_resync.md) instead.

1.  In the navigation menu, click **Syncs**.

2.  Click the name of the sync you want to run.

    The Sync Detail page opens.

3.  Click **Sync Changes**.

    A new run is queued. The run history table updates to show the new run with a status of Pending, which changes to Running once the run starts. Refresh the page to see the latest status.


When the run finishes, its status changes to Completed and the changed count reflects the number of articles that were created or updated in the target system. If the status is Failed or Error, review the error message recorded with the run.

**Important:** Do not trigger a new run while a run for the same sync is already in Running status. Wait for the current run to finish first.

