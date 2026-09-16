# How removed content is handled during a sync {#concept-6752 .concept}

When a topic is removed from a Heretto deployment and a full resync is run, the syndication service compares the current deployment structure against previously synced articles and archives or flags any articles that no longer have a corresponding source topic.

The syndication service tracks every article it creates in Salesforce Knowledge. During a full resync, it walks the current deployment structure and compares the result against that record. Any article whose source topic is no longer present is considered stale.

What happens to a stale article depends on its publish status in Salesforce Knowledge:

Published \(Online\) articles
:   The service moves the article to **Archived** status using the Salesforce Knowledge archive action. Archived articles are no longer visible to end users but remain in Salesforce so a Knowledge administrator can review, re-purpose, or permanently delete them.

Draft articles
:   The service attempts to delete the draft. If the deletion fails due to insufficient permissions, the draft is left in place and a warning is recorded in the sync run history. A Salesforce administrator can then delete the orphaned draft manually.

**Important:** Stale article detection only runs during a **Full Resync**. Incremental syncs use a change cursor from the Heretto Deploy API and rely on the API to report removed topics directly.

**Note:** Before removed content is detected, the deployment must be published in Heretto CCMS so the syndication service can read the updated structure.

