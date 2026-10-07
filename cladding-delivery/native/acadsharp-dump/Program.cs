using System.Collections;
using System.Reflection;
using System.Text.Json;
using System.Text;
using System.Security.Cryptography;
using ACadSharp;
using ACadSharp.IO;

Console.OutputEncoding = new UTF8Encoding(false);

if (args.Length != 2 || args[0] != "inspect")
{
    Console.Error.WriteLine("usage: ACadSharpDump inspect <drawing.dwg>");
    return 2;
}

var file = Path.GetFullPath(args[1]);
var notifications = new List<object>();
CadDocument doc;
using (var reader = CadReaderFactory.CreateReader(file))
{
    reader.OnNotification += (sender, e) => notifications.Add(new {
        type = e.NotificationType.ToString(),
        message = e.Message
    });
    doc = reader.Read();
}

var counts = new SortedDictionary<string,int>(StringComparer.Ordinal);
var layers = new SortedSet<string>(StringComparer.Ordinal);
foreach (var entity in doc.Entities)
{
    var type = entity.GetType().Name;
    counts[type] = counts.TryGetValue(type, out var n) ? n + 1 : 1;
    var prop = entity.GetType().GetProperty("Layer", BindingFlags.Public | BindingFlags.Instance);
    var layer = prop?.GetValue(entity);
    var name = layer?.GetType().GetProperty("Name")?.GetValue(layer)?.ToString();
    if (!string.IsNullOrWhiteSpace(name)) layers.Add(name!);
}

var payload = new {
    adapter = "acadsharp",
    library = typeof(CadDocument).Assembly.GetName().Version?.ToString(),
    success = true,
    file,
    sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(file))).ToLowerInvariant(),
    canonical_level = "INSPECTION_ONLY",
    production_geometry_ready = false,
    limitation = "Model-space entity inventory only. Nested block and XRef transforms, dimension semantics, unknown objects and production geometry have not been verified.",
    entity_count = doc.Entities.Count(),
    entity_types = counts,
    layers,
    notifications
};
Console.WriteLine(JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }));
return 0;
