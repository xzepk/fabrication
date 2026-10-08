using System.Text.Json;
using Rhino;
using RhinoAi.Contracts;
using RhinoAi.Core;

namespace RhinoAi.Plugin;

/// <summary>A single shared execution queue/journal for both floating and docked views of the same live document.</summary>
internal sealed class DocumentSession : IDisposable
{
    private static readonly Dictionary<uint, DocumentSession> Sessions = [];
    public RhinoDocumentAdapter Adapter { get; }
    public RhinoUiDispatcher Dispatcher { get; } = new();
    public ExecutionCoordinator Coordinator { get; }
    public JsonOperationStore Store { get; }
    public string DirectoryPath { get; }
    public ChangePlan? Pending { get; set; }
    public Guid? LastOperationId { get; set; }
    public SemaphoreSlim UiGate { get; } = new(1, 1);
    private readonly CancellationTokenSource _lifetime = new();
    private CancellationTokenSource? _activeCancellation;
    public bool IsClosed { get; private set; }
    public CancellationToken BeginRequest()
    {
        if (IsClosed) throw new HarnessException("document-closed", "The document session is closed.");
        _activeCancellation?.Dispose();
        _activeCancellation = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
        return _activeCancellation.Token;
    }
    public void EndRequest() { _activeCancellation?.Dispose(); _activeCancellation = null; }
    public void CancelRequest() => _activeCancellation?.Cancel();
    private DocumentSession(RhinoDocumentAdapter adapter, DocumentSnapshot snapshot)
    {
        Adapter = adapter;
        DirectoryPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "RhinoAi", "executor", snapshot.DocumentId.ToString("D"));
        Store = new JsonOperationStore(Path.Combine(DirectoryPath, "operations"));
        Coordinator = new ExecutionCoordinator(adapter, Dispatcher, Store);
        LastOperationId = Store.List().OrderByDescending(x => x.UpdatedAt).FirstOrDefault()?.OperationId;
    }
    public static DocumentSession Current(bool initialize)
    {
        RhinoUiDispatcher.RequireUiThread();
        var doc = RhinoDoc.ActiveDoc ?? throw new HarnessException("no-document", "Open a Rhino document first.");
        if (Sessions.TryGetValue(doc.RuntimeSerialNumber, out var existing)) return existing;
        var adapter = new RhinoDocumentAdapter(doc);
        try
        {
            if (initialize) adapter.InitializeDocument();
            var session = new DocumentSession(adapter, adapter.Capture());
            Sessions.Add(doc.RuntimeSerialNumber, session);
            return session;
        }
        catch { adapter.Dispose(); throw; }
    }
    public Checkpoint SaveCheckpoint()
    {
        RhinoUiDispatcher.RequireUiThread();
        var checkpoint = Adapter.CaptureCheckpoint();
        if (checkpoint.Snapshot.Issues.Length != 0) throw new HarnessException("checkpoint-qa", string.Join("\n", checkpoint.Snapshot.Issues));
        var dir = Path.Combine(DirectoryPath, "checkpoints"); Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, checkpoint.CheckpointId.ToString("D") + ".json");
        using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(checkpoint, Protocol.Json);
        stream.Write(bytes); stream.Flush(true);
        return checkpoint;
    }
    public Checkpoint[] ListCheckpoints()
    {
        var dir = Path.Combine(DirectoryPath, "checkpoints");
        return Directory.Exists(dir) ? Directory.GetFiles(dir, "*.json").Select(path => JsonSerializer.Deserialize<Checkpoint>(File.ReadAllText(path), Protocol.Json) ?? throw new IOException("Invalid checkpoint file.")).OrderByDescending(x => x.CreatedAt).ToArray() : [];
    }
    public Guid? SelectedManagedObject()
    {
        RhinoUiDispatcher.RequireUiThread();
        var doc = RhinoDoc.FromRuntimeSerialNumber(Adapter.RuntimeSerial) ?? throw new HarnessException("document-closed", "Document closed.");
        var selected = doc.Objects.GetSelectedObjects(false, false).ToArray();
        if (selected.Length != 1 || string.IsNullOrWhiteSpace(selected[0].Attributes.GetUserString(Protocol.EntityKey)))
            throw new HarnessException("selection", "Select exactly one managed box in Rhino before previewing translation.");
        return selected[0].Id;
    }
    public void Dispose() { Adapter.Dispose(); Store.Dispose(); _activeCancellation?.Dispose(); _lifetime.Dispose(); UiGate.Dispose(); }
    private async Task CloseWhenIdleAsync()
    {
        IsClosed = true; _lifetime.Cancel();
        await UiGate.WaitAsync();
        await Dispatcher.InvokeAsync(() => { Dispose(); return 0; });
    }
    public static void Close(uint serial)
    {
        if (Sessions.Remove(serial, out var session)) _ = session.CloseWhenIdleAsync();
    }
    public static void CloseAll() { foreach (var session in Sessions.Values) _ = session.CloseWhenIdleAsync(); Sessions.Clear(); }
}
