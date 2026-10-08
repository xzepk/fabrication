using System.Globalization;
using System.Runtime.InteropServices;
using Eto.Drawing;
using Eto.Forms;
using Rhino;
using RhinoAi.Contracts;
using RhinoAi.Core;

namespace RhinoAi.Plugin;

[Guid("CC3A29AA-771E-43AC-8FC9-E85C508A41CF")]
public sealed class AssistantPanel : Panel
{
    private readonly TextBox _hostPath = new() { PlaceholderText = "Full path to RhinoAi.Host.exe" };
    private readonly TextBox _endpoint = new() { Text = "http://127.0.0.1:47831/" };
    private readonly PasswordBox _nonce = new();
    private readonly TextBox _entity = new() { Text = "BOX-001" };
    private readonly TextBox _origin = new() { Text = "0, 0, 0" };
    private readonly TextBox _size = new() { Text = "100, 100, 100" };
    private readonly TextBox _translation = new() { Text = "100, 0, 0" };
    private readonly DropDown _checkpoints = new();
    private readonly TextArea _status = new() { ReadOnly = true, Height = 220, Wrap = true };
    private readonly Label _connection = new() { Text = "Host disconnected. Live acceptance: NOT_RUN." };
    private readonly List<Button> _actionButtons = [];
    private Checkpoint[] _availableCheckpoints = [];
    private bool _busy;
    private DocumentSession? _runningSession;
    public AssistantPanel()
    {
        Padding = 10;
        var layout = new DynamicLayout { Spacing = new Size(6, 6), Padding = 4 };
        layout.AddRow(new Label { Text = "Rhino AI Harness · Stage 1 candidate", Font = new Font(SystemFont.Bold, 13) });
        layout.AddRow(new Label { Text = "Preview → explicit acceptance → one owned Undo record" });
        layout.AddRow(_connection);
        layout.AddRow("Host executable", _hostPath);
        layout.AddRow(Button("Browse…", BrowseHost), Button("Start local host", StartHost));
        layout.AddRow("Loopback endpoint", _endpoint);
        layout.AddRow("In-memory nonce", _nonce);
        layout.AddRow(Button("Attach host", AttachHost));
        layout.AddRow(Button("Initialize document", InitializeSession), Button("Inspect context", Inspect));
        layout.AddRow("Engineering ID", _entity);
        layout.AddRow("Origin X, Y, Z", _origin);
        layout.AddRow("Width, depth, height", _size);
        layout.AddRow(Button("Preview box", PreviewBox));
        layout.AddRow("Translation X, Y, Z", _translation);
        layout.AddRow(Button("Preview selected managed box move", PreviewTranslation));
        layout.AddRow(Button("Accept preview & commit", Commit), Button("Cancel preview", Cancel));
        var interrupt = new Button { Text = "Cancel active request" };
        interrupt.Click += (_, _) =>
        {
            try { (_runningSession ?? DocumentSession.Current(false)).CancelRequest(); Log("Cancellation requested. Once synchronous apply starts it must finish or compensate safely."); }
            catch (Exception ex) { Log(ex.Message); }
        };
        layout.AddRow(interrupt);
        layout.AddRow(Button("Save managed checkpoint", SaveCheckpoint), Button("Refresh checkpoints", RefreshCheckpoints));
        layout.AddRow(_checkpoints);
        layout.AddRow(Button("Preview managed restore", PreviewRestore));
        layout.AddRow(Button("Recover last acknowledgement", RecoverAcknowledgement));
        layout.AddRow(_status);
        layout.AddRow(new Label { Text = "No LLM, scripts, production approval, split/join or full-document restore." });
        Content = new Scrollable { Content = layout };
    }
    private Button Button(string text, Func<Task> action)
    {
        var button = new Button { Text = text };
        button.Click += async (_, _) => await Run(action);
        _actionButtons.Add(button);
        return button;
    }
    private async Task Run(Func<Task> action)
    {
        if (_busy) return;
        _busy = true;
        foreach (var button in _actionButtons) button.Enabled = false;
        try { await action(); }
        catch (Exception ex) { Log((ex is HarnessException h ? h.Code + ": " : "Error: ") + ex.Message); }
        finally { _busy = false; foreach (var button in _actionButtons) button.Enabled = true; }
    }
    private Task BrowseHost()
    {
        using var dialog = new OpenFileDialog { Title = "Select the built RhinoAi.Host.exe" };
        dialog.Filters.Add(new FileFilter("Windows executable", ".exe"));
        if (dialog.ShowDialog(this) == DialogResult.Ok) _hostPath.Text = dialog.FileName;
        return Task.CompletedTask;
    }
    private async Task StartHost()
    {
        if (HarnessPlugIn.Host is not null) throw new HarnessException("host-connected", "A host is already connected in this Rhino process.");
        if (!Uri.TryCreate(_endpoint.Text, UriKind.Absolute, out var endpoint)) throw new HarnessException("host-endpoint", "Enter a valid loopback endpoint.");
        var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "RhinoAi", "host");
        HarnessPlugIn.Host = await AgentHostClient.StartAsync(_hostPath.Text, endpoint.Port, dir);
        _connection.Text = "Connected to " + HarnessPlugIn.Host.Endpoint;
        Log("Host started. Authentication nonce lives only in memory and the child process environment.");
    }
    private async Task AttachHost()
    {
        if (HarnessPlugIn.Host is not null) throw new HarnessException("host-connected", "A host is already connected in this Rhino process.");
        var nonce = _nonce.Text; _nonce.Text = string.Empty;
        HarnessPlugIn.Host = await AgentHostClient.AttachAsync(new Uri(_endpoint.Text), nonce);
        _connection.Text = "Connected to " + HarnessPlugIn.Host.Endpoint;
        Log("Attached to the explicit authenticated loopback host.");
    }
    private Task InitializeSession()
    {
        var session = DocumentSession.Current(initialize: true);
        Log("Document identity initialized: " + session.Adapter.Capture().DocumentId + ". Save the 3DM to persist it.");
        return RefreshCheckpoints();
    }
    private Task Inspect()
    {
        var snapshot = DocumentSession.Current(false).Adapter.Capture();
        Log($"Document {snapshot.DocumentId}\nSession {snapshot.SessionId}\nRevision {snapshot.Revision}\nUnits {snapshot.Units}; tolerance {snapshot.Tolerance}; managed objects {snapshot.Entities.Length}\n" +
            string.Join("\n", snapshot.Entities.Select(e => $"{e.EntityId}: {e.RhinoId}")) + "\nQA: " + (snapshot.Issues.Length == 0 ? "pass" : string.Join("\n", snapshot.Issues)));
        return Task.CompletedTask;
    }
    private Task PreviewBox()
    {
        var origin = ParsePoint(_origin.Text);
        var size = ParsePoint(_size.Text);
        return Prepare((snapshot, operationId) => new(Protocol.Version, Guid.NewGuid(), operationId, "box.add", PlanValidator.Expected(snapshot), new(origin, size.X, size.Y, size.Z), EntityId: _entity.Text));
    }
    private Task PreviewTranslation()
    {
        var session = DocumentSession.Current(false);
        var id = session.SelectedManagedObject();
        var translation = ParsePoint(_translation.Text);
        return Prepare((snapshot, operationId) => new(Protocol.Version, Guid.NewGuid(), operationId, "object.translate", PlanValidator.Expected(snapshot), ObjectId: id, Translation: translation));
    }
    private async Task Prepare(Func<DocumentSnapshot, Guid, ToolRequest> createRequest, Checkpoint? restore = null)
    {
        var host = RequiredHost();
        var session = DocumentSession.Current(false);
        _runningSession = session;
        await session.UiGate.WaitAsync();
        try
        {
            if (session.Pending is not null) throw new HarnessException("preview-pending", "Commit or cancel the existing shared preview before preparing another.");
            var ct = session.BeginRequest();
            var snapshot = await session.Dispatcher.InvokeAsync(session.Adapter.Capture, ct);
            var request = createRequest(snapshot, Guid.NewGuid());
            session.LastOperationId = request.OperationId;
            ChangePlan plan;
            try
            {
                plan = await host.PrepareAsync(new(request, snapshot, restore), ct);
                plan = await session.Coordinator.PreviewAsync(plan, ct);
            }
            catch (OperationCanceledException)
            {
                try
                {
                    var local = session.Coordinator.Get(request.OperationId);
                    if (local?.State == OperationState.Prepared) await host.CompleteAsync(await session.Coordinator.RejectAsync(request.OperationId));
                    else
                    {
                        var remote = await host.GetAsync(request.OperationId);
                        if (remote?.State == OperationState.Prepared) await host.CompleteAsync(remote with { State = OperationState.Cancelled, Error = "Cancelled before document mutation.", UpdatedAt = DateTimeOffset.UtcNow });
                    }
                }
                catch (Exception ex) { Log("Preparation cancellation is local; host acknowledgement could not be confirmed. No geometry was changed. " + ex.Message); }
                throw;
            }
            session.Pending = plan;
            session.LastOperationId = request.OperationId;
            Log($"PREVIEW: {plan.Summary}\nOperation {request.OperationId}\n" + string.Join("\n", plan.Warnings) + "\nInspect the blue detached viewport geometry, then accept or cancel.");
        }
        finally { session.EndRequest(); session.UiGate.Release(); _runningSession = null; }
    }
    private async Task Commit()
    {
        var host = RequiredHost();
        var session = DocumentSession.Current(false);
        _runningSession = session;
        await session.UiGate.WaitAsync();
        try
        {
            var ct = session.BeginRequest();
            var plan = session.Pending ?? throw new HarnessException("preview-required", "Prepare a current preview first.");
            if (plan.RestoreTarget is not null && MessageBox.Show(this,
                $"Restore checkpoint {plan.RestoreTarget.CheckpointId}?\n\nThis replaces ALL current managed objects and ALL later human/AI edits to them with {plan.RestoreTarget.Snapshot.Entities.Length} saved objects. Unmanaged objects are preserved. The current managed scope is checkpointed first. Accept this exact scope?",
                "Accept managed-scope restore", MessageBoxButtons.YesNo, MessageBoxType.Warning) != DialogResult.Yes) return;
            if (plan.RestoreTarget is null && MessageBox.Show(this, $"Accept this exact preview?\n\n{plan.Summary}\nOperation: {plan.Request.OperationId}\nDocument: {plan.Before.DocumentId}\n\nThis changes the Rhino document in one owned Undo record.", "Accept preview", MessageBoxButtons.YesNo, MessageBoxType.Question) != DialogResult.Yes) return;
            OperationRecord local;
            try { local = await session.Coordinator.CommitAsync(plan.Request.OperationId, ct, beforeApply: async record => { await host.CompleteAsync(record, ct); }); }
            catch
            {
                var failed = session.Coordinator.Get(plan.Request.OperationId);
                if (failed is { State: OperationState.FailedRecovery or OperationState.Cancelled })
                {
                    if (failed.State == OperationState.Cancelled) session.Pending = null;
                    try { await host.CompleteAsync(failed); } catch { /* Local durable state remains authoritative; no automatic mutation retry. */ }
                }
                throw;
            }
            session.Pending = null;
            Log($"Committed locally and durably: {local.OperationId}. Owned Undo record {local.Outcome!.UndoRecord}. Native Rhino Undo/Redo can now be used.");
            try { await host.CompleteAsync(local); Log("Host acknowledgement recorded."); }
            catch (Exception ex) { Log("Host acknowledgement pending; geometry will not be replayed. Use Recover last acknowledgement. " + ex.Message); }
        }
        finally { session.EndRequest(); session.UiGate.Release(); _runningSession = null; }
    }
    private async Task Cancel()
    {
        var session = DocumentSession.Current(false);
        _runningSession = session;
        await session.UiGate.WaitAsync();
        try
        {
            var plan = session.Pending ?? throw new HarnessException("preview-required", "There is no pending shared preview.");
            var record = await session.Coordinator.RejectAsync(plan.Request.OperationId);
            session.Pending = null;
            if (HarnessPlugIn.Host is not null) await HarnessPlugIn.Host.CompleteAsync(record);
            Log("Preview cancelled. No geometry was changed.");
        }
        finally { session.EndRequest(); session.UiGate.Release(); _runningSession = null; }
    }
    private Task SaveCheckpoint()
    {
        var checkpoint = DocumentSession.Current(false).SaveCheckpoint();
        Log($"Managed checkpoint saved and flushed: {checkpoint.CheckpointId}; {checkpoint.Snapshot.Entities.Length} objects. No source 3DM was overwritten.");
        return RefreshCheckpoints();
    }
    private Task RefreshCheckpoints()
    {
        _availableCheckpoints = DocumentSession.Current(false).ListCheckpoints();
        _checkpoints.Items.Clear();
        foreach (var checkpoint in _availableCheckpoints) _checkpoints.Items.Add($"{checkpoint.CreatedAt:u} · {checkpoint.Snapshot.Entities.Length} objects · {checkpoint.CheckpointId}");
        if (_availableCheckpoints.Length > 0) _checkpoints.SelectedIndex = 0;
        return Task.CompletedTask;
    }
    private Task PreviewRestore()
    {
        if (_checkpoints.SelectedIndex < 0 || _checkpoints.SelectedIndex >= _availableCheckpoints.Length) throw new HarnessException("checkpoint-selection", "Select a saved checkpoint first.");
        var checkpoint = _availableCheckpoints[_checkpoints.SelectedIndex];
        return Prepare((snapshot, operationId) => new(Protocol.Version, Guid.NewGuid(), operationId, "checkpoint.restore", PlanValidator.Expected(snapshot), CheckpointId: checkpoint.CheckpointId), checkpoint);
    }
    private async Task RecoverAcknowledgement()
    {
        var host = RequiredHost();
        var session = DocumentSession.Current(false);
        _runningSession = session;
        await session.UiGate.WaitAsync();
        try
        {
            var id = session.LastOperationId ?? throw new HarnessException("operation-missing", "No local operation to reconcile.");
            var local = session.Coordinator.Get(id) ?? throw new HarnessException("operation-missing", "The local journal does not contain this operation.");
            var remote = await host.GetAsync(id);
            if (remote is null || remote.RequestHash != local.RequestHash) throw new HarnessException("recovery-required", "Host journal is missing or conflicts with local history. No geometry was replayed. Manual journal review is required.");
            if (local.State == OperationState.Committed)
            {
                await host.CompleteAsync(local);
                Log("Durable outcome acknowledged. This does not replay geometry or reverse native Undo/Redo.");
                session.Pending = null;
            }
            else if (local.State == OperationState.Cancelled) { await host.CompleteAsync(local); Log("Cancellation acknowledged."); }
            else Log($"Local state {local.State}; host state {remote.State}. Applying/failed states are quarantined. Inspect saved before-images and the actual document; do not replay this operation. Automatic recovery unlocking is not implemented in Stage 1 candidate.");
        }
        finally { session.EndRequest(); session.UiGate.Release(); _runningSession = null; }
    }
    private static AgentHostClient RequiredHost() => HarnessPlugIn.Host ?? throw new HarnessException("host-disconnected", "Start or attach the local host first.");
    private static Point3 ParsePoint(string value)
    {
        var parts = value.Split(',').Select(x => double.Parse(x.Trim(), CultureInfo.InvariantCulture)).ToArray();
        if (parts.Length != 3 || parts.Any(x => !double.IsFinite(x))) throw new HarnessException("input", "Enter three finite comma-separated numbers, using a dot for decimals.");
        return new(parts[0], parts[1], parts[2]);
    }
    private void Log(string message) { _status.Text = DateTimeOffset.Now.ToString("T") + " " + message + "\n\n" + _status.Text; }
}
