# Field Mapping Format {#r_field_mapping .reference}

The field mapping defines which content fields from Heretto deployment are published to which fields in your target system, such as Salesforce Knowledge.

## Overview {#section_overview .section}

Field mapping is configured in the sync form as a set of rows, each pairing a Heretto source field with the API name of a field in your target system. The source fields available for mapping are fixed; target field API names vary depending on your Salesforce org configuration.

Only fields you explicitly map are included in the data sent to the target system. Unmapped source fields are ignored.

## Available source fields {#section_source_fields .section}

The following source fields can be mapped from Heretto Deploy:

|Field name \(internal\)|Label|Description|
|-----------------------|-----|-----------|
|`title`|Title|The article topic.|
|`short_description`|Short Description|A brief summary or teaser text for the article.|
|`html_body`|Body|The full HTML content of the article. HTML is sanitized to the subset accepted by the target system before publishing.|
|`content_type`|Content Type|The content type value from Heretto standard metadata.|
|`last_modified_iso`|Last Modified|The date and time the article was last modified in Heretto Deploy, in ISO 8601 format.|
|`section_path`|Section Path|The structural path for the article, with each level joined by `>`, for example Getting Started \> Installation. Only populated during a full resync.|
|`sort_order`|Position within Section|The article's numeric position within its parent section in the deployment structure. Useful for maintaining reading order in the target system. Only populated during a full resync.|

## Format {#section_format .section}

Internally, the field mapping is stored as a JSON object. Keys are the internal field names from the table above; values are the API names of the corresponding fields in your target system.

Example mapping for Salesforce Knowledge:

```
{
  "title":             "Title",
  "short_description": "Summary__c",
  "html_body":         "Answer__c"
}
```

**Tip:** Salesforce field API names for custom fields end in `__c`. Standard Knowledge fields such as `Title` do not. Confirm the correct API names in your Salesforce org under Setup \> Object Manager \> Knowledge \> Fields & Relationships.

