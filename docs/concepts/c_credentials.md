# Credentials {#c_credentials .concept}

Credentials store the authentication details the syndication service needs to connect to an external system such as Salesforce Knowledge. Each sync configuration references one credential.

Credentials are created and managed in the **Credentials** section of the application, or inline when creating or editing a sync. A single credential can be shared across multiple syncs that connect to the same target system.

## Salesforce authentication modes {#section_salesforce_auth_modes .section}

The Salesforce Knowledge connector supports two authentication modes. Choose the mode that matches how your Salesforce org is configured.

OAuth 2.0 Client Credentials Flow \(recommended\)
:   The service authenticates using a Salesforce External Client App configured with the Client Credentials Flow. Tokens are acquired and refreshed automatically — you do not need to update the credential when a token expires.

    To use this mode, provide a **Client ID** and **Client Secret** from a Salesforce External Client App. Leave the **Access Token** field empty.

    To find or create these values in Salesforce: go to **Setup** \> **App Manager**, open your External Client App, and copy the Consumer Key \(Client ID\) and Consumer Secret \(Client Secret\). The app must have the **Client Credentials Flow** enabled and a Run As user assigned.

Static Access Token
:   The service authenticates using a long-lived access token you provide. This mode is simpler to set up but requires you to update the credential manually whenever the token expires.

    To use this mode, provide an **Access Token** value. Leave **Client ID** and **Client Secret** empty.

    You can generate a token in Salesforce using the OAuth 2.0 authorization code flow via Workbench or a connected app. Tokens typically expire after a set session timeout.

## Credential fields {#section_credential_fields .section}

The following fields are required when creating a Salesforce Knowledge credential:

|Field|Required|Description|
|-----|--------|-----------|
|Instance URL|Always|The base URL of your Salesforce org, for example https://myorg.my.salesforce.com. Do not include a trailing slash.|
|API Version|Always|The Salesforce REST API version to use, for example 65.0. Defaults to the current supported version. Update this when your org is upgraded to a newer API version.|
|Knowledge Type|Always|The API name of your Knowledge Article Version object, for example Knowledge\_\_kav. Custom Knowledge objects use the pattern ObjectName\_\_kav. Confirm the name in Salesforce under **Setup** \> **Object Manager** \> **Knowledge**.|
|External ID Field|Always|The API name of the custom field on your Knowledge object that stores the Heretto article UUID, for example Heretto\_UUID\_\_c. This field must exist on the Knowledge object and be of type Text. It is used to match Heretto articles to Salesforce records across syncs.|
|Client ID|OAuth only|The Consumer Key from a Salesforce External Client App with Client Credentials Flow enabled.|
|Client Secret|OAuth only|The Consumer Secret from the same External Client App.|
|Access Token|Static token only|A valid Salesforce access token. Leave empty when using OAuth 2.0 Client Credentials Flow.|

