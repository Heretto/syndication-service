# Edit a Sync {#t_edit_sync .task}

Update the configuration of an existing sync, for example to change its name, schedule, field mapping, or credentials.

1.  In the navigation menu, click **Syncs**.

2.  Click the name of the sync you want to edit.

    The Sync Detail page opens.

3.  Click **Edit**.

    The Edit Sync form opens with the current values pre-filled.

4.  In the **Name** field under **Basic Information**, enter a descriptive name for the sync, for example Salesforce Knowledge Sync.

5.  Under **Source & Target**, select an adapter from the **Source Adapter** list.

    The adapter defines the source system the sync reads content from. Heretto Deploy is currently the only supported adapter.

6.  Select a connector from the **Target Connector** list.

    The connector defines the target system the sync publishes content to, for example Salesforce Knowledge.

7.  Under **Source — Heretto Deploy**, enter the Deployment ID for the content in Heretto in the **Deployment ID** field.

    The Deployment ID is a UUID that identifies the specific deployment configured in Heretto CCMS from which content will be read. You can find it in your Heretto CCMS Deployment admin UI.

8.  Under **Target Connection**, select a saved credential from the credential list.

    If no credential exists yet, click **New credential** to expand the inline credential form. Enter the required values for your target connector and click **Save Credential**. The new credential will be selected automatically.

9.  Under **Schedule**, configure how often the sync runs automatically.

    |Option|Description|
    |------|-----------|
    |**Automatic schedule**|Leave the **Manual sync only — no automatic schedule** checkbox unchecked and use the schedule builder to set a recurring schedule, such as daily at 9 AM.|
    |**Manual sync only**|Select **Manual sync only — no automatic schedule** to disable automatic runs. The sync will run only when you trigger it manually from the Sync Detail page.|

10. Under **Field Mapping**, map each Heretto source field you want to publish to its corresponding field API name in the target system.

    1.  Click **Add Field** to add a mapping row.

    2.  In the left dropdown, select a source field from Heretto Deploy.

    3.  In the right input, enter the API name of the target field in your connector, for example Answer\_\_c.

    4.  Repeat for each field you want to map.

    See [Field Mapping Format](../reference/r_field_mapping.md) for the list of available source fields and format details.

11. Optional: Under **Data Category Mapping**, map Heretto taxonomy names to Salesforce data category group API names.

    1.  Click **Add Category** to add a mapping row.

    2.  In the left field, enter the name of the Heretto taxonomy group, for example Audiences.

    3.  In the right dropdown, select the corresponding Salesforce data category group. The list is populated from your Salesforce organization.

    4.  Repeat for each taxonomy group you want to map.

    This section appears only when the target connector is Salesforce. Data category groups must exist in Salesforce Setup before they appear in the dropdown.

    If your Heretto content uses audience taxonomy values \(for example, Internal and External\), map that taxonomy group here to control article visibility in Salesforce. This is the supported way to implement audience-specific content filtering — Salesforce applies category-based visibility at query time rather than requiring separate sync configurations per audience.

    See [Data Category Mapping Format](../reference/r_data_category_mapping.md) for format details and a full explanation of the audience filtering approach.

12. Click **Save Changes**.

    The updated configuration is saved and you are returned to the Sync Detail page. If you changed the schedule, the new schedule takes effect immediately.


