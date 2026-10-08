using System.Reflection;
using System.Runtime.InteropServices;
using Eto.Drawing;
using Eto.Forms;
using Rhino;
using Rhino.Commands;
using Rhino.PlugIns;
using Rhino.UI;

[assembly: AssemblyTitle("Rhino AI Agent Harness")]
[assembly: Guid("E78408A2-56F2-44D2-A2A2-E9AC24A8B6A9")]

namespace RhinoAi.Plugin;

public sealed class HarnessPlugIn : PlugIn
{
    internal static AgentHostClient? Host { get; set; }
    private static Form? _floating;
    protected override LoadReturnCode OnLoad(ref string errorMessage)
    {
        if (!OperatingSystem.IsWindows() || Environment.Version.Major != 8 || RhinoApp.Version.Major != 8 || RhinoApp.Version.Minor < 20)
        { errorMessage = "This candidate requires Windows Rhino 8.20 or later using .NET 8. Other combinations have not been qualified."; return LoadReturnCode.ErrorShowDialog; }
        Panels.RegisterPanel(this, typeof(AssistantPanel), "Rhino AI Harness", (System.Drawing.Icon?)null);
        RhinoDoc.CloseDocument += OnCloseDocument;
        RhinoDoc.BeginOpenDocument += OnBeginOpenDocument;
        return LoadReturnCode.Success;
    }
    private static void OnBeginOpenDocument(object? sender, DocumentOpenEventArgs e) { if (!e.Merge && !e.Reference) DocumentSession.Close(e.Document.RuntimeSerialNumber); }
    private static void OnCloseDocument(object? sender, DocumentEventArgs e) => DocumentSession.Close(e.Document.RuntimeSerialNumber);
    internal static void ShowFloating()
    {
        if (_floating is not null) { _floating.BringToFront(); return; }
        _floating = new Form { Title = "Rhino AI Harness · Stage 1 candidate", ClientSize = new Size(540, 850), Content = new AssistantPanel() };
        _floating.Closed += (_, _) => _floating = null;
        _floating.Show();
    }
    protected override void OnShutdown()
    {
        RhinoDoc.CloseDocument -= OnCloseDocument;
        RhinoDoc.BeginOpenDocument -= OnBeginOpenDocument;
        _floating?.Close(); DocumentSession.CloseAll(); Host?.Dispose(); Host = null;
        base.OnShutdown();
    }
}

public sealed class RhinoAiPanelCommand : Rhino.Commands.Command
{
    public override string EnglishName => "RhinoAiPanel";
    protected override Result RunCommand(RhinoDoc doc, RunMode mode) { Panels.OpenPanel(typeof(AssistantPanel)); return Result.Success; }
}
public sealed class RhinoAiFloatCommand : Rhino.Commands.Command
{
    public override string EnglishName => "RhinoAiFloat";
    protected override Result RunCommand(RhinoDoc doc, RunMode mode) { HarnessPlugIn.ShowFloating(); return Result.Success; }
}
