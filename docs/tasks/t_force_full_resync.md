# Force a Full Resync {#t_force_full_resync .task}

Trigger a full resync to reprocess all content in the Heretto deployment, regardless of when each article was last modified.

You need to publish your Deployment in Heretto CCMS prior to running a sync for the syndication service to pick up the latest content changes from Deploy API.

A full resync walks the complete structure of your Heretto deployment and updates the articles in Salesforce. The next scheduled or manual incremental sync will continue from the same cursor position as before the full resync.

Use a full resync when:

-   New topics exist in Heretto deployment that weren't captured in the last sync.
-   You suspect the target system is missing articles or has content that is out of date.
-   You have made changes to the field mapping or data category mapping and want those changes applied to all articles, not just newly changed ones.
-   You have removed topics from a deployment and want those removals reflected in Salesforce Knowledge. A full resync detects articles that no longer have a matching source topic and archives or removes them automatically. See [How removed content is handled during a sync](../concepts/c_deleting-topics-from-a-deployment.md).

**Important:** A full resync processes every topic in your deployment and may take significantly longer than an incremental sync, depending on the size of your deployment map.

1.  In the navigation menu, click **Syncs**.

2.  Click the name of the sync you want to resync.

    The Sync Detail page opens.

3.  Click **Full Resync**.

    A confirmation prompt appears. Confirm that you want to proceed.

    A full resync is queued. The history table updates to show the new sync with a status of Running. Refresh the page to see the latest status as the run progresses.


When the sync finishes, its status changes to Completed and the changed count reflects the total number of articles processed. Subsequent incremental syncs will pick up changes from the same point as before the resync.

