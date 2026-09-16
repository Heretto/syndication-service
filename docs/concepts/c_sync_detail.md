# Sync Detail {#c_sync_detail .concept}

The Sync Detail page shows the full configuration of a single sync.

To open the Sync Detail page, click a sync name from the Dashboard or the Syncs list. The page is divided into a configuration summary on the left and a run history table on the right.

## Configuration summary {#section_config_summary .section}

The configuration summary shows the values set when the sync was created or last edited, including the sync name at the top of the page, Deployment ID, target connector UUID, assigned credential, publish mode, and schedule. If no automatic schedule is configured, the schedule displays as Manual sync only.

## Action buttons {#section_actions .section}

Four action buttons appear near the top of the page:

**Edit**
:   Opens the sync configuration form so you can change the sync name, schedule, field mapping, or other settings.

**Sync Changes**
:   Triggers an incremental sync run. The service fetches only content that has changed since the last successful run. Use this for routine on-demand publishing.

**Full Resync**
:   Triggers a full resync that walks the entire Heretto Deploy structure and processes every article regardless of modification date. Use this when you suspect content is out of sync or after a long gap in sync activity.

**Delete**
:   Permanently deletes the sync configuration and removes its automatic schedule. This action cannot be undone.

## Recent Syncs {#section_run_history .section}

The Recent Syncs table at the bottom of the page lists recent runs for this sync. Each row shows the run status, the time the run started and completed, and the number of articles changed.

For a description of each run status, see [Sync History](c_sync_history.md).

