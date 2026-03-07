using System.Net.Http.Headers;
using System.Net.Http.Json;
using AegisDotNet.Models;

namespace AegisDotNet;

public sealed class AegisClient
{
    private readonly HttpClient _http;
    private readonly Func<string?> _getJwt;

    public AegisClient(HttpClient http, Func<string?> getJwt)
    {
        _http = http;
        _getJwt = getJwt;
    }

    private void ApplyAuthHeader()
    {
        var token = _getJwt();
        _http.DefaultRequestHeaders.Authorization = string.IsNullOrWhiteSpace(token)
            ? null
            : new AuthenticationHeaderValue("Bearer", token);
    }

    public async Task<EventIngestResult> IngestAsync(PlatformIngestRequest request, CancellationToken cancellationToken = default)
    {
        ApplyAuthHeader();
        var response = await _http.PostAsJsonAsync("/api/v1/ingest", request, cancellationToken);
        response.EnsureSuccessStatusCode();
        return (await response.Content.ReadFromJsonAsync<EventIngestResult>(cancellationToken: cancellationToken))!;
    }

    public async Task<PlatformAlertList> AlertsAsync(string? state = null, string? cursor = null, int? limit = null, CancellationToken cancellationToken = default)
    {
        ApplyAuthHeader();
        var query = new List<string>();
        if (!string.IsNullOrWhiteSpace(state)) query.Add($"state={Uri.EscapeDataString(state)}");
        if (!string.IsNullOrWhiteSpace(cursor)) query.Add($"cursor={Uri.EscapeDataString(cursor)}");
        if (limit.HasValue) query.Add($"limit={limit.Value}");
        var suffix = query.Count > 0 ? "?" + string.Join("&", query) : string.Empty;
        var response = await _http.GetAsync($"/api/v1/alerts{suffix}", cancellationToken);
        response.EnsureSuccessStatusCode();
        return (await response.Content.ReadFromJsonAsync<PlatformAlertList>(cancellationToken: cancellationToken))!;
    }

    public async Task<Dictionary<string, object?>> MetricsAsync(string window = "24h", CancellationToken cancellationToken = default)
    {
        ApplyAuthHeader();
        var response = await _http.GetAsync($"/api/v1/metrics?window={Uri.EscapeDataString(window)}", cancellationToken);
        response.EnsureSuccessStatusCode();
        return (await response.Content.ReadFromJsonAsync<Dictionary<string, object?>>(cancellationToken: cancellationToken))!;
    }

    public async Task<PlatformConfig> ConfigAsync(CancellationToken cancellationToken = default)
    {
        ApplyAuthHeader();
        var response = await _http.GetAsync("/api/v1/config", cancellationToken);
        response.EnsureSuccessStatusCode();
        return (await response.Content.ReadFromJsonAsync<PlatformConfig>(cancellationToken: cancellationToken))!;
    }
}
