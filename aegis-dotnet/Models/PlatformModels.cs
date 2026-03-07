namespace AegisDotNet.Models;

public sealed record StandardizedTransaction(
    string transaction_id,
    string tenant_id,
    string source,
    double amount,
    string currency,
    DateTimeOffset timestamp,
    string? counterparty_id,
    Dictionary<string, object?> metadata_json
);

public sealed record PlatformIngestRequest(
    string? connector,
    string? source,
    Dictionary<string, object?>? payload,
    StandardizedTransaction? transaction,
    string? event_type,
    string? idempotency_key,
    DateTimeOffset? occurred_at
);

public sealed record EventIngestResult(string event_id, string status, bool queued);

public sealed record PlatformAlertList(List<Dictionary<string, object?>> items, string? next_cursor, int total_estimate);

public sealed record PlatformConfig(
    string tenant_id,
    double? anomaly_threshold,
    List<string> enabled_connectors,
    string? model_version,
    Dictionary<string, object?> rule_overrides_json,
    List<string> connector_modules_loaded
);
