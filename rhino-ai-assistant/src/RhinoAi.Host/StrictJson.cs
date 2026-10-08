using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using RhinoAi.Contracts;

namespace RhinoAi.Host;

public static class StrictJson
{
    public static readonly JsonSerializerOptions Options = CreateOptions();
    private static JsonSerializerOptions CreateOptions()
    {
        var resolver = new DefaultJsonTypeInfoResolver();
        resolver.Modifiers.Add(type =>
        {
            if (type.Kind != JsonTypeInfoKind.Object || type.Type.Namespace is not ("RhinoAi.Contracts" or "RhinoAi.Host")) return;
            // .NET 8 otherwise silently fills missing record constructor fields with defaults.
            var constructor = type.Type.GetConstructors().OrderByDescending(x => x.GetParameters().Length).FirstOrDefault();
            if (constructor is null) return;
            var required = constructor.GetParameters().Where(x => !x.HasDefaultValue).Select(x => JsonNamingPolicy.CamelCase.ConvertName(x.Name!)).ToHashSet(StringComparer.Ordinal);
            foreach (var property in type.Properties)
                if (required.Contains(property.Name)) property.IsRequired = true;
        });
        var options = new JsonSerializerOptions(Protocol.Json) { PropertyNameCaseInsensitive = false, MaxDepth = 64, TypeInfoResolver = resolver };
        options.Converters.Clear();
        options.Converters.Add(new JsonStringEnumConverter(allowIntegerValues: false));
        return options;
    }
    public static async Task<T> ReadAsync<T>(HttpRequest request, CancellationToken cancellationToken)
    {
        if (request.ContentLength > HostSettings.MaximumBodyBytes)
            throw new HostHttpException(413, "body_too_large", "Request exceeds the 1 MiB body limit.");
        if (!request.HasJsonContentType())
            throw new HostHttpException(415, "content_type", "Use application/json.");
        if (request.Headers.ContainsKey("Content-Encoding"))
            throw new HostHttpException(415, "content_encoding", "Encoded request bodies are unsupported.");
        using var buffer = new MemoryStream();
        var bytes = new byte[16_384];
        while (true)
        {
            var count = await request.Body.ReadAsync(bytes, cancellationToken);
            if (count == 0) break;
            if (buffer.Length + count > HostSettings.MaximumBodyBytes)
                throw new HostHttpException(413, "body_too_large", "Request exceeds the 1 MiB body limit.");
            buffer.Write(bytes, 0, count);
        }
        using var json = JsonDocument.Parse(buffer.ToArray(), new JsonDocumentOptions { MaxDepth = 64 });
        CheckNoDuplicateProperties(json.RootElement);
        return json.RootElement.Deserialize<T>(Options) ?? throw new JsonException("A JSON object is required.");
    }
    public static T Parse<T>(string text)
    {
        using var json = JsonDocument.Parse(text, new JsonDocumentOptions { MaxDepth = 32 });
        CheckNoDuplicateProperties(json.RootElement);
        return json.RootElement.Deserialize<T>(Options) ?? throw new JsonException("A JSON object is required.");
    }
    public static void CheckNoDuplicateProperties(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in element.EnumerateObject())
            {
                if (!names.Add(property.Name)) throw new JsonException("Duplicate property.");
                CheckNoDuplicateProperties(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
            foreach (var item in element.EnumerateArray()) CheckNoDuplicateProperties(item);
    }
}
public sealed class HostHttpException(int status, string code, string message) : Exception(message)
{
    public int Status { get; } = status;
    public string Code { get; } = code;
}
