using System.Net.WebSockets;
using System.Text;

namespace AegisDotNet;

public sealed class WebSocketClient
{
    private readonly Func<string?> _getJwt;
    private readonly Uri _baseUri;
    private readonly string[] _channels;

    public WebSocketClient(Uri baseUri, Func<string?> getJwt, params string[] channels)
    {
        _baseUri = baseUri;
        _getJwt = getJwt;
        _channels = channels.Length == 0 ? new[] { "alerts" } : channels;
    }

    public async Task ConnectWithReconnectAsync(Func<string, Task> onMessage, CancellationToken cancellationToken)
    {
        var delay = TimeSpan.FromMilliseconds(500);
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                using var socket = new ClientWebSocket();
                var token = _getJwt();
                if (string.IsNullOrWhiteSpace(token))
                {
                    throw new InvalidOperationException("JWT token is required for websocket connection");
                }

                var builder = new UriBuilder(_baseUri);
                var query = $"token={Uri.EscapeDataString(token)}&channels={Uri.EscapeDataString(string.Join(',', _channels))}";
                builder.Query = query;

                await socket.ConnectAsync(builder.Uri, cancellationToken);
                delay = TimeSpan.FromMilliseconds(500);

                var buffer = new byte[8192];
                while (socket.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested)
                {
                    var result = await socket.ReceiveAsync(buffer, cancellationToken);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        break;
                    }

                    var content = Encoding.UTF8.GetString(buffer, 0, result.Count);
                    await onMessage(content);
                }
            }
            catch when (!cancellationToken.IsCancellationRequested)
            {
                await Task.Delay(delay, cancellationToken);
                delay = TimeSpan.FromMilliseconds(Math.Min(delay.TotalMilliseconds * 2, 30_000));
            }
        }
    }
}
