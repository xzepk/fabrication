using System.Globalization;
using System.Text.RegularExpressions;
using RhinoAi.Contracts;

namespace RhinoAi.Host;

/// <summary>Conservative optional prompt syntax; no semantic guessing or unit conversions. Explicit typed inputs take priority.</summary>
public static partial class PlannerPromptFacts
{
    private const string Number = @"[-+]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)";
    public static PlannerInputs Resolve(PlannerRequest request)
    {
        var input = request.Inputs ?? new PlannerInputs();
        var box = input.Box;
        if (box is null)
        {
            var w = Scalar(request.Prompt, "width|宽度|宽");
            var d = Scalar(request.Prompt, "depth|深度|深");
            var h = Scalar(request.Prompt, "height|高度|高");
            var origin = Vector(request.Prompt, "origin|原点");
            if (w is not null && d is not null && h is not null && origin is not null) box = new(origin, w.Value, d.Value, h.Value);
        }
        var ids = Regex.Matches(request.Prompt, @"(?:^|[\s;,；:：])(?:entityId|工程编号)\s*[:=：]\s*([A-Za-z0-9][A-Za-z0-9._:-]{0,127})(?=$|[\s;,；])", RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(100));
        return input with { Box = box, EntityId = input.EntityId ?? (ids.Count == 1 ? ids[0].Groups[1].Value : null), Translation = input.Translation ?? Vector(request.Prompt, "translation|平移") };
    }
    private static double? Scalar(string prompt, string names)
    {
        var matches = Regex.Matches(prompt, $@"(?:^|[\s;,；:：])(?:{names})\s*[:=：]\s*({Number})(?=$|[\s;,；])", RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(100));
        return matches.Count == 1 && double.TryParse(matches[0].Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out var value) && double.IsFinite(value) ? value : null;
    }
    private static Point3? Vector(string prompt, string names)
    {
        var matches = Regex.Matches(prompt, $@"(?:^|[\s;；:：])(?:{names})\s*[:=：]\s*\(\s*({Number})\s*,\s*({Number})\s*,\s*({Number})\s*\)(?=$|[\s;；])", RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(100));
        if (matches.Count != 1) return null;
        var values = matches[0].Groups.Values.Skip(1).Select(g => double.Parse(g.Value, CultureInfo.InvariantCulture)).ToArray();
        return values.All(double.IsFinite) ? new(values[0], values[1], values[2]) : null;
    }
}
