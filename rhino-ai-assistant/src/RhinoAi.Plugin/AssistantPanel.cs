using System.Globalization;
using System.Diagnostics;
using System.Text.Json;
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
    private readonly TextArea _prompt = new() { Height = 90, Wrap = true };
    private readonly DropDown _platePlane = new();
    private readonly CheckBox _reviewInputs = new() { Text = "I reviewed each plate’s plane, origin, dimensions, new ID, material, grade and density (REVIEW only)." };
    private readonly TextArea _claddingJson = new() { Height = 210, Wrap = false };
    private readonly Label _reviewStatus = new() { Text = "No cladding review. Production release: NOT_RELEASED." };
    private readonly TextBox _outputDirectory = new() { ReadOnly = true };
    private PlannerResponse? _planned;
    private Guid[] _plannedSelection = [];
    private CladdingReviewResult? _review;
    private Guid[] _reviewSelection = [];
    private readonly DropDown _checkpoints = new();
    private readonly TextArea _status = new() { ReadOnly = true, Height = 220, Wrap = true };
    private readonly Label _connection = new() { Text = "Host disconnected. Live acceptance: NOT_RUN." };
    private readonly List<Button> _actionButtons = [];
    private Checkpoint[] _availableCheckpoints = [];
    private bool _busy;
    private DocumentSession? _runningSession;
    private DocumentSession? _observedSession;
    public AssistantPanel()
    {
        Padding = 10;
        var layout = new DynamicLayout { Spacing = new Size(6, 6), Padding = 4 };
        layout.AddRow(new Label { Text = "Rhino AI · Stage 2 REVIEW candidate", Font = new Font(SystemFont.Bold, 13) });
        layout.AddRow(new Label { Text = "Preview → explicit acceptance → one owned Undo record" });
        layout.AddRow(_connection);
        layout.AddRow("Host executable", _hostPath);
        layout.AddRow(Button("Browse…", BrowseHost), Button("Start local host", StartHost));
        layout.AddRow("Loopback endpoint", _endpoint);
        layout.AddRow("In-memory nonce", _nonce);
        layout.AddRow(Button("Attach host", AttachHost));
        layout.AddRow(Button("Initialize document", InitializeSession), Button("Inspect context", Inspect));
        layout.AddRow(new Label { Text = "Local bounded planner · no provider credentials required" });
        layout.AddRow(new Label { Text = "Describe one supported box/move task. Missing dimensions are clarified, never guessed." });
        layout.AddRow(_prompt);
        layout.AddRow(Button("Plan", Plan), Button("Preview planned action", PreviewPlanned));
        layout.AddRow(new Label { Text = "Cladding review · rectangular unbent, unperforated plates only · millimetres" });
        _platePlane.Items.Add("Infer only a unique smallest thickness axis");
        _platePlane.Items.Add("XY · Z is thickness"); _platePlane.Items.Add("XZ · Y is thickness"); _platePlane.Items.Add("YZ · X is thickness");
        _platePlane.SelectedIndex = 0;
        layout.AddRow("Selected plate orientation", _platePlane);
        layout.AddRow(Button("New blank plate task", NewPlateTask), Button("Capture selected managed box task", CapturePlateTask));
        layout.AddRow(Button("Load task JSON…", LoadPlateTask));
        layout.AddRow(new Label { Text = "Editable task JSON: explicit dimensions, material, grade and density required. No fabrication defaults." });
        layout.AddRow(_claddingJson);
        layout.AddRow(_reviewInputs);
        layout.AddRow(Button("Generate cladding REVIEW", GenerateCladdingReview), Button("Preview reviewed plates", PreviewReviewedPlates));
        layout.AddRow(_reviewStatus);
        layout.AddRow("Output folder", _outputDirectory);
        layout.AddRow(Button("Open output folder", OpenOutputDirectory));
        layout.AddRow(new Label { Text = "Direct structured box tools (document units)" });
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
        layout.AddRow(new Label { Text = "Bounded local planning and independent cladding review. No production approval, arbitrary scripts, bends, cutouts or full-document restore." });
        Content = new Scrollable { Content = layout };
        _prompt.TextChanged += (_, _) => _planned = null;
        _claddingJson.TextChanged += (_, _) =>
        {
            _reviewInputs.Checked = false; _planned = null; _review = null; _outputDirectory.Text = string.Empty;
            _reviewStatus.Text = "Task edited. Generate a new REVIEW before preview. Production release: NOT_RELEASED.";
        };
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
        _prompt.ReadOnly = true; _claddingJson.ReadOnly = true; _reviewInputs.Enabled = false; _platePlane.Enabled = false;
        try { await action(); }
        catch (Exception ex) { Log((ex is HarnessException h ? h.Code + ": " : "Error: ") + ex.Message); }
        finally { _busy = false; _prompt.ReadOnly = false; _claddingJson.ReadOnly = false; _reviewInputs.Enabled = true; _platePlane.Enabled = true; foreach (var button in _actionButtons) button.Enabled = true; }
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
    private async Task Plan()
    {
        var host = RequiredHost();
        var session = DocumentSession.Current(false);
        ObserveSession(session);
        _runningSession = session;
        _planned = null;
        await session.UiGate.WaitAsync();
        try
        {
            var ct = session.BeginRequest();
            var captured = await session.Dispatcher.InvokeAsync(() => (Snapshot: session.Adapter.Capture(), Selection: session.SelectedManagedObjects()), ct);
            CladdingReviewRequest? cladding = null;
            if (!string.IsNullOrWhiteSpace(_claddingJson.Text))
                cladding = await session.Dispatcher.InvokeAsync(() => CreateCladdingRequest(session, captured.Snapshot, captured.Selection), ct);
            var request = new PlannerRequest(PlanningProtocol.Version, Guid.NewGuid(), Guid.NewGuid(), _prompt.Text,
                PlanValidator.Expected(captured.Snapshot), captured.Snapshot, captured.Selection, cladding is null ? null : new(Cladding: cladding));
            var inputHash = Protocol.Hash(new { Prompt = _prompt.Text, Task = _claddingJson.Text });
            var response = await host.PlanAsync(request, ct);
            if (inputHash != Protocol.Hash(new { Prompt = _prompt.Text, Task = _claddingJson.Text })) throw new HarnessException("stale-input", "Prompt/task changed during planning. Plan again.");
            await VerifyCapturedContext(session, request.Expected, captured.Selection, ct);
            ct.ThrowIfCancellationRequested();
            if (response.PlannerVersion != PlanningProtocol.Version || response.ContextHash != PlanningProtocol.ContextHash(request.Expected, captured.Selection))
                throw new HarnessException("planner-context", "Planner returned a result for a different context. No preview or mutation was performed.");
            _planned = response; _plannedSelection = captured.Selection;
            Log($"PLAN [{response.Status}]: {response.Message}" +
                (response.Plan is null ? "" : $"\n{response.Plan.Summary}\nClick Preview planned action to inspect geometry. This plan has not changed the document.") +
                (response.CladdingRequest is null ? "" : "\nClick Generate cladding REVIEW to run the independent Skill with the explicit task inputs."));
        }
        finally { session.EndRequest(); session.UiGate.Release(); _runningSession = null; }
    }

    private Task PreviewPlanned()
    {
        var response = _planned ?? throw new HarnessException("plan-required", "Click Plan first. Editing the prompt or task clears its result.");
        var plan = response.Plan ?? throw new HarnessException("clarification-required", response.Message);
        var session = DocumentSession.Current(false);
        ObserveSession(session);
        return Prepare((snapshot, _) =>
        {
            PlanValidator.Match(plan.Request.Expected, snapshot);
            RequireSelection(session, _plannedSelection);
            return plan.Request;
        }, expectedSelection: _plannedSelection);
    }

    // This compact editor deliberately excludes document/selection identity: those are captured on the UI thread.
    private sealed record PlateTaskInput(string SourceMode, PlateComponent[] Components, string[] Targets, PlateStock? Stock = null, CladdingSourceEvidence? Evidence = null);
    private static PlateTaskInput BlankPlateTask() => new("explicit_design",
        [new("PLATE-001", "Plate 001", new(0, 0, 0), 0, 0, 0, "", "", 0, 1, [])],
        ["step", "drawings", "bom", "nesting"]);
    private Task NewPlateTask()
    {
        _claddingJson.Text = JsonSerializer.Serialize(BlankPlateTask(), Protocol.Json);
        Log("Blank task created. Enter all dimensions, material, grade and density. Origin is explicit in JSON; no production values have been assumed. Clear Rhino selection for explicit_design.");
        return Task.CompletedTask;
    }
    private async Task CapturePlateTask()
    {
        var session = DocumentSession.Current(false);
        ObserveSession(session);
        var task = await session.Dispatcher.InvokeAsync(() =>
        {
            var snapshot = session.Adapter.Capture();
            if (snapshot.Units != "Millimeters") throw new HarnessException("cladding-units", "Cladding review requires a millimetre document; no implicit unit conversion is performed.");
            var selected = session.SelectedManagedObjects();
            if (selected.Length is < 1 or > PlanValidator.MaxPlateBatch) throw new HarnessException("selection", "Select 1–128 managed rectangular boxes to capture source geometry.");
            var components = selected.Select(id =>
            {
                var source = snapshot.Entities.Single(e => e.RhinoId == id);
                var box = session.Adapter.CaptureManagedBox(id);
                var plane = SelectedPlane(box, snapshot.Tolerance);
                var (width, height, thickness) = plane switch
                {
                    "XY" => (box.Width, box.Depth, box.Height),
                    "XZ" => (box.Width, box.Height, box.Depth),
                    "YZ" => (box.Depth, box.Height, box.Width),
                    _ => throw new HarnessException("plate-plane", "Unsupported plate orientation.")
                };
                var outputId = source.EntityId.Length <= 122 ? source.EntityId + ".PLATE" : source.EntityId[..104] + "." + Protocol.Hash(source.EntityId)[..16] + ".PLATE";
                return new PlateComponent(outputId, source.EntityId, box.Origin,
                    width, height, thickness, "", "", 0, 1, [source.EntityId], Plane: plane);
            }).ToArray();
            return new PlateTaskInput("selected_managed", components, ["step", "drawings", "bom", "nesting"]);
        });
        _claddingJson.Text = JsonSerializer.Serialize(task, Protocol.Json);
        Log("Captured exact supported managed-box source dimensions and IDs. Plane values are proposals; review each one explicitly in JSON. Enter NEW plate IDs, material, grade and density; review every dimension before generating outputs. Source objects remain untouched.");
    }
    private string SelectedPlane(BoxSpec box, double tolerance)
    {
        if (_platePlane.SelectedIndex is >= 1 and <= 3) return new[] { "XY", "XZ", "YZ" }[_platePlane.SelectedIndex - 1];
        var dimensions = new[] { (Value: box.Height, Plane: "XY"), (Value: box.Depth, Plane: "XZ"), (Value: box.Width, Plane: "YZ") }.OrderBy(x => x.Value).ToArray();
        if (dimensions[1].Value - dimensions[0].Value <= tolerance)
            throw new HarnessException("plate-plane", "Thickness axis is ambiguous. Select XY, XZ or YZ explicitly before capturing this source.");
        return dimensions[0].Plane;
    }
    private Task LoadPlateTask()
    {
        using var dialog = new OpenFileDialog { Title = "Load explicit cladding task JSON" };
        dialog.Filters.Add(new FileFilter("JSON task", ".json"));
        if (dialog.ShowDialog(this) != DialogResult.Ok) return Task.CompletedTask;
        var file = new FileInfo(dialog.FileName);
        if (file.Length > 1_000_000) throw new HarnessException("input-limit", "Task JSON must be smaller than 1 MB.");
        var value = File.ReadAllText(file.FullName);
        _ = StrictJsonInput.Deserialize<PlateTaskInput>(value);
        _claddingJson.Text = value;
        Log("Task JSON loaded for review. No document or engineering inputs were adopted automatically.");
        return Task.CompletedTask;
    }
    private CladdingReviewRequest CreateCladdingRequest(DocumentSession session, DocumentSnapshot snapshot, Guid[] selected)
    {
        if (snapshot.Units != "Millimeters") throw new HarnessException("cladding-units", "Cladding review requires explicit millimetre document units.");
        var input = StrictJsonInput.Deserialize<PlateTaskInput>(_claddingJson.Text);
        var sources = selected.Select(id =>
        {
            var entity = snapshot.Entities.Single(e => e.RhinoId == id);
            return new SelectedPlateSource(entity.EntityId, entity.Fingerprint, session.Adapter.CaptureManagedBox(id));
        }).ToArray();
        return new(Protocol.Version, Guid.NewGuid(), PlanValidator.Expected(snapshot), snapshot, input.SourceMode,
            sources.Select(s => s.EntityId).ToArray(), sources, input.Components, input.Targets, input.Stock, input.Evidence);
    }
    private async Task GenerateCladdingReview()
    {
        if (_reviewInputs.Checked != true) throw new HarnessException("input-review", "Review each plate’s explicit inputs and proposed orientation in the JSON, then check the input-review box. This does not approve production.");
        var host = RequiredHost();
        var session = DocumentSession.Current(false);
        ObserveSession(session);
        _runningSession = session; _review = null; _outputDirectory.Text = string.Empty;
        await session.UiGate.WaitAsync();
        try
        {
            var ct = session.BeginRequest();
            var captured = await session.Dispatcher.InvokeAsync(() =>
            {
                var snapshot = session.Adapter.Capture(); var selection = session.SelectedManagedObjects();
                return (Request: CreateCladdingRequest(session, snapshot, selection), Selection: selection);
            }, ct);
            _reviewStatus.Text = "Generating REVIEW. No model changes. Cancel active request to discard adoption.";
            var inputHash = Protocol.Hash(_claddingJson.Text);
            var result = await host.ReviewCladdingAsync(captured.Request, ct);
            if (inputHash != Protocol.Hash(_claddingJson.Text)) throw new HarnessException("stale-input", "Task changed during review. Generate a fresh REVIEW.");
            await VerifyCapturedContext(session, captured.Request.Expected, captured.Selection, ct);
            ct.ThrowIfCancellationRequested();
            if (result.Manifest.JobId != captured.Request.JobId || result.Manifest.RequestHash != Protocol.Hash(captured.Request) || Protocol.Hash(result.Request) != Protocol.Hash(captured.Request) || result.Manifest.InputSnapshotHash != captured.Request.Snapshot.SnapshotHash ||
                result.Manifest.Status != "REVIEW" || result.Manifest.ManufacturingRelease || result.Manifest.ReleaseDecision != "NOT_RELEASED")
                throw new HarnessException("review-integrity", "Host returned unexpected review identity or release status.");
            _review = result; _reviewSelection = captured.Selection;
            _outputDirectory.Text = result.OutputDirectory;
            _reviewStatus.Text = $"REVIEW · {result.Manifest.PreviewPlates.Length} plates · nesting {result.Manifest.NestingStatus} · NOT_RELEASED";
            Log($"Cladding REVIEW {result.Manifest.JobId}\nOutput: {result.OutputDirectory}\nManifest SHA256: {result.ManifestHash}\n" +
                string.Join("\n", result.Manifest.Artifacts.Select(a => $"{a.Kind}: {a.Path} ({a.Bytes} bytes; SHA256 {a.Sha256})")) +
                "\n" + string.Join("\n", result.Manifest.Warnings) + "\nReview files, then click Preview reviewed plates. Production release remains NOT_RELEASED.");
        }
        catch { _reviewStatus.Text = "Review was not adopted. No model changes; any completed Host files remain REVIEW only."; throw; }
        finally { session.EndRequest(); session.UiGate.Release(); _runningSession = null; }
    }
    private Task PreviewReviewedPlates()
    {
        var review = _review ?? throw new HarnessException("review-required", "Generate a current cladding REVIEW first.");
        var manifest = review.Manifest;
        var session = DocumentSession.Current(false);
        ObserveSession(session);
        return Prepare((snapshot, operationId) =>
        {
            PlanValidator.Match(review.Request.Expected, snapshot);
            RequireSelection(session, _reviewSelection);
            var plates = manifest.PreviewPlates.Select(p => new PlanarPlateSpec(p.EntityId, p.Box, p.Material)).ToArray();
            var provenance = new PlateBatchProvenance(manifest.JobId, manifest.InputSnapshotHash, manifest.JobHash, review.ManifestHash,
                "cladding-delivery", manifest.SkillVersion, manifest.RuleVersion, manifest.SkillSourceHash);
            return new(Protocol.Version, manifest.JobId, operationId, "cladding.plates.add", PlanValidator.Expected(snapshot), Plates: plates, Provenance: provenance);
        }, expectedSelection: _reviewSelection);
    }
    private Task OpenOutputDirectory()
    {
        var path = _review?.OutputDirectory;
        if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path) || !Directory.Exists(path))
            throw new HarnessException("output-directory", "No accessible completed local REVIEW folder is available.");
        Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
        return Task.CompletedTask;
    }
    private static Task<int> VerifyCapturedContext(DocumentSession session, ExpectedContext expected, Guid[] selection, CancellationToken ct) =>
        session.Dispatcher.InvokeAsync(() => { PlanValidator.Match(expected, session.Adapter.Capture()); RequireSelection(session, selection); return 0; }, ct);
    private static void RequireSelection(DocumentSession session, Guid[] selection)
    {
        if (!session.SelectedManagedObjects().SequenceEqual(selection)) throw new HarnessException("stale-selection", "Selection changed while planning/reviewing. Capture and review the current selection again.");
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
        ObserveSession(session);
        var id = session.SelectedManagedObject();
        var translation = ParsePoint(_translation.Text);
        return Prepare((snapshot, operationId) => new(Protocol.Version, Guid.NewGuid(), operationId, "object.translate", PlanValidator.Expected(snapshot), ObjectId: id, Translation: translation));
    }
    private async Task Prepare(Func<DocumentSnapshot, Guid, ToolRequest> createRequest, Checkpoint? restore = null, Guid[]? expectedSelection = null)
    {
        var host = RequiredHost();
        var session = DocumentSession.Current(false);
        ObserveSession(session);
        _runningSession = session;
        await session.UiGate.WaitAsync();
        try
        {
            if (session.Pending is not null) throw new HarnessException("preview-pending", "Commit or cancel the existing shared preview before preparing another.");
            var ct = session.BeginRequest();
            var snapshot = await session.Dispatcher.InvokeAsync(session.Adapter.Capture, ct);
            var request = await session.Dispatcher.InvokeAsync(() => createRequest(snapshot, Guid.NewGuid()), ct);
            session.LastOperationId = request.OperationId;
            ChangePlan plan;
            try
            {
                plan = await host.PrepareAsync(new(request, snapshot, restore), ct);
                if (expectedSelection is not null) await VerifyCapturedContext(session, request.Expected, expectedSelection, ct);
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
            session.PendingSelection = expectedSelection?.ToArray();
            session.LastOperationId = request.OperationId;
            Log($"PREVIEW: {plan.Summary}\nOperation {request.OperationId}\n" + string.Join("\n", plan.Warnings) + "\nInspect the blue detached viewport geometry, then accept or cancel.");
        }
        finally { session.EndRequest(); session.UiGate.Release(); _runningSession = null; }
    }
    private async Task Commit()
    {
        var host = RequiredHost();
        var session = DocumentSession.Current(false);
        ObserveSession(session);
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
            if (session.PendingSelection is not null) await VerifyCapturedContext(session, plan.Request.Expected, session.PendingSelection, ct);
            OperationRecord local;
            try { local = await session.Coordinator.CommitAsync(plan.Request.OperationId, ct, beforeApply: async record =>
            {
                await host.CompleteAsync(record, ct);
                if (session.PendingSelection is not null) await VerifyCapturedContext(session, plan.Request.Expected, session.PendingSelection, ct);
            }); }
            catch
            {
                var failed = session.Coordinator.Get(plan.Request.OperationId);
                if (failed is { State: OperationState.FailedRecovery or OperationState.Cancelled })
                {
                    if (failed.State == OperationState.Cancelled) { session.Pending = null; session.PendingSelection = null; }
                    try { await host.CompleteAsync(failed); } catch { /* Local durable state remains authoritative; no automatic mutation retry. */ }
                }
                throw;
            }
            session.Pending = null; session.PendingSelection = null;
            Log($"Committed locally and durably: {local.OperationId}. Owned Undo record {local.Outcome!.UndoRecord}. Native Rhino Undo/Redo can now be used.");
            try { await host.CompleteAsync(local); Log("Host acknowledgement recorded."); }
            catch (Exception ex) { Log("Host acknowledgement pending; geometry will not be replayed. Use Recover last acknowledgement. " + ex.Message); }
        }
        finally { session.EndRequest(); session.UiGate.Release(); _runningSession = null; }
    }
    private async Task Cancel()
    {
        var session = DocumentSession.Current(false);
        ObserveSession(session);
        _runningSession = session;
        await session.UiGate.WaitAsync();
        try
        {
            var plan = session.Pending ?? throw new HarnessException("preview-required", "There is no pending shared preview.");
            var record = await session.Coordinator.RejectAsync(plan.Request.OperationId);
            session.Pending = null; session.PendingSelection = null;
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
        ObserveSession(session);
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
                session.Pending = null; session.PendingSelection = null;
            }
            else if (local.State == OperationState.Cancelled) { await host.CompleteAsync(local); Log("Cancellation acknowledged."); }
            else Log($"Local state {local.State}; host state {remote.State}. Applying/failed states are quarantined. Inspect saved before-images and the actual document; do not replay this operation. Automatic recovery unlocking is not implemented in Stage 1 candidate.");
        }
        finally { session.EndRequest(); session.UiGate.Release(); _runningSession = null; }
    }
    private void ObserveSession(DocumentSession session)
    {
        if (ReferenceEquals(_observedSession, session)) return;
        if (_observedSession is not null) _observedSession.Adapter.Invalidated -= ContextInvalidated;
        _observedSession = session;
        session.Adapter.Invalidated += ContextInvalidated;
    }
    private void ContextInvalidated(object? sender, EventArgs e)
    {
        _planned = null;
        if (_review is not null)
            _reviewStatus.Text = "HISTORICAL REVIEW: model/context changed. Generate a fresh review before adoption. Existing output files remain REVIEW / NOT_RELEASED.";
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
