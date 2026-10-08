using System.Text;
using System.Text.Json;
using RhinoAi.Contracts;

namespace RhinoAi.Core;

/// <summary>Validates human-reviewed JSON before typed deserialization can discard ambiguous property values.</summary>
public static class StrictJsonInput
{
    public const int MaxBytes = 1_000_000;
    public const int MaxDepth = 32;

    public static T Deserialize<T>(string json) where T : class
    {
        if (string.IsNullOrWhiteSpace(json)) throw new HarnessException("invalid-json", "Enter a nonempty JSON task.");
        if (json.Length > MaxBytes || Encoding.UTF8.GetByteCount(json) > MaxBytes)
            throw new HarnessException("input-limit", "Task JSON must be no larger than 1 MB of UTF-8 text.");
        using var document = JsonDocument.Parse(json, new JsonDocumentOptions
        {
            MaxDepth = MaxDepth,
            AllowTrailingCommas = false,
            CommentHandling = JsonCommentHandling.Disallow
        });
        RejectAmbiguousProperties(document.RootElement);
        // Protocol.Json rejects unknown fields. Duplicate checks match its case-insensitive property binding.
        return document.RootElement.Deserialize<T>(Protocol.Json)
            ?? throw new HarnessException("invalid-json", "JSON task cannot be null.");
    }

    private static void RejectAmbiguousProperties(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var property in element.EnumerateObject())
            {
                if (!names.Add(property.Name))
                    throw new HarnessException("ambiguous-json", "JSON contains duplicate property names, including case-only differences. Keep exactly one explicit value for each field.");
                RejectAmbiguousProperties(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
            foreach (var item in element.EnumerateArray()) RejectAmbiguousProperties(item);
    }
}
