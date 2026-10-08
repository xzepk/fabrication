using RhinoAi.Contracts;
using RhinoAi.Core;
using System.Text.Json;

var tests = new List<(string Name, Func<Task> Run)>();
void Test(string name, Func<Task> run) => tests.Add((name, run));
static void Check(bool value, string message = "assertion failed") { if (!value) throw new Exception(message); }
static async Task Throws(string code, Func<Task> action)
{
    try { await action(); } catch (HarnessException e) when (e.Code == code) { return; }
    throw new Exception("Expected error " + code);
}
static (FakeAdapter Adapter, MemoryStore Store, ExecutionCoordinator Engine) Setup()
{
    var adapter = new FakeAdapter(); var store = new MemoryStore(); return (adapter, store, new(adapter, new ImmediateDispatcher(), store));
}
static ChangePlan Add(FakeAdapter a, string id = "BOX-001", Guid? op = null) => PlanValidator.Prepare(new(new(1, Guid.NewGuid(), op ?? Guid.NewGuid(), "box.add", PlanValidator.Expected(a.Capture()), new(new(0, 0, 0), 10, 20, 30), EntityId: id), a.Capture()));
static ChangePlan Translate(FakeAdapter a) => PlanValidator.Prepare(new(new(1, Guid.NewGuid(), Guid.NewGuid(), "object.translate", PlanValidator.Expected(a.Capture()), ObjectId: a.Capture().Entities[0].RhinoId, Translation: new(10, 0, 0)), a.Capture()));
static ChangePlan Restore(FakeAdapter a, Checkpoint cp) => PlanValidator.Prepare(new(new(1, Guid.NewGuid(), Guid.NewGuid(), "checkpoint.restore", PlanValidator.Expected(a.Capture()), CheckpointId: cp.CheckpointId), a.Capture(), cp));

static ChangePlan Plates(FakeAdapter a, int count = 2)
{
    var snapshot = a.Capture();
    var plates = Enumerable.Range(0, count).Select(i => new PlanarPlateSpec($"PLATE-{i + 1:D3}", new(new(i * 1200, 0, 0), 1000, 500, 3), "Aluminum / explicit fixture")).ToArray();
    var provenance = new PlateBatchProvenance(Guid.NewGuid(), snapshot.SnapshotHash, new('A', 64), new('B', 64), "cladding-delivery", "fixture-1", "planar-1", new('C', 64));
    return PlanValidator.Prepare(new(new(Protocol.Version, Guid.NewGuid(), Guid.NewGuid(), "cladding.plates.add", PlanValidator.Expected(snapshot), Plates: plates, Provenance: provenance), snapshot));
}

Test("preview and reject do not mutate", async () => { var (a, s, e) = Setup(); var p = Add(a); var hash = a.Capture().SnapshotHash; await e.PreviewAsync(p); Check(a.PreviewVisible && a.Capture().SnapshotHash == hash); await e.RejectAsync(p.Request.OperationId); Check(!a.PreviewVisible && a.ApplyCalls == 0 && s.Get(p.Request.OperationId)!.State == OperationState.Cancelled); });
Test("commit has durable before-image and verified result", async () => { var (a,s,e)=Setup();var p=Add(a);await e.PreviewAsync(p);a.BeforeApply=()=>Check(s.Get(p.Request.OperationId) is {State:OperationState.Applying,BeforeCheckpoint:not null});var r=await e.CommitAsync(p.Request.OperationId);Check(r.State==OperationState.Committed&&r.Outcome!.Added.Length==1&&a.ApplyCalls==1&&!a.PreviewVisible); });
Test("lost acknowledgement replay never mutates twice", async () => {var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);var r=await e.CommitAsync(p.Request.OperationId);var replay=await e.CommitAsync(p.Request.OperationId);Check(r==replay&&a.ApplyCalls==1);});
Test("replay after native undo does not redo",async()=>{var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);await e.CommitAsync(p.Request.OperationId);a.Undo();await e.CommitAsync(p.Request.OperationId);Check(a.Capture().Entities.Length==0&&a.ApplyCalls==1);});
Test("cancel while queued for UI prevents mutation",async()=>{var a=new FakeAdapter();var s=new MemoryStore();var dispatcher=new QueuedDispatcher();var e=new ExecutionCoordinator(a,dispatcher,s);var p=Add(a);await e.PreviewAsync(p);dispatcher.HoldAt=4;using var c=new CancellationTokenSource();var task=e.CommitAsync(p.Request.OperationId,c.Token);await dispatcher.Queued.Task;c.Cancel();dispatcher.Release.TrySetResult();try{await task;throw new Exception("no cancel");}catch(OperationCanceledException){}Check(a.ApplyCalls==0&&s.Get(p.Request.OperationId)!.State==OperationState.Cancelled);});
Test("same operation different arguments is conflict",async()=>{var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);await Throws("operation-conflict",()=>e.PreviewAsync(Add(a,"BOX-002",p.Request.OperationId)));});
Test("tampered plan hash is rejected",async()=>{var(a,_,e)=Setup();await Throws("payload-mismatch",()=>e.PreviewAsync(Add(a) with {RequestHash="changed"}));Check(a.ApplyCalls==0);});
Test("manual edit invalidates preview",async()=>{var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);a.Touch();await Throws("stale-context",()=>e.CommitAsync(p.Request.OperationId));Check(a.ApplyCalls==0);});
Test("session change invalidates preview",async()=>{var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);a.Reopen();await Throws("stale-context",()=>e.CommitAsync(p.Request.OperationId));Check(a.ApplyCalls==0);});
Test("document switch invalidates preview",async()=>{var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);a.SwitchDocument();await Throws("stale-context",()=>e.CommitAsync(p.Request.OperationId));});
Test("cancel before apply leaves document unchanged",async()=>{var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);using var c=new CancellationTokenSource();c.Cancel();try{await e.CommitAsync(p.Request.OperationId,c.Token);throw new Exception("no cancel");}catch(OperationCanceledException){}Check(a.ApplyCalls==0);});
Test("cancel after applying boundary returns actual result",async()=>{var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);using var c=new CancellationTokenSource();a.BeforeApply=()=>c.Cancel();var r=await e.CommitAsync(p.Request.OperationId,c.Token);Check(r.State==OperationState.Committed&&a.ApplyCalls==1);});
Test("concurrent same-op commits exactly once",async()=>{var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);var both=await Task.WhenAll(e.CommitAsync(p.Request.OperationId),e.CommitAsync(p.Request.OperationId));Check(a.ApplyCalls==1&&both.All(x=>x.State==OperationState.Committed));});
Test("superseded preview cannot commit",async()=>{var(a,_,e)=Setup();var p1=Add(a);var p2=Add(a,"BOX-002");await e.PreviewAsync(p1);await e.PreviewAsync(p2);await Throws("preview-required",()=>e.CommitAsync(p1.Request.OperationId));await e.CommitAsync(p2.Request.OperationId);await Throws("preview-required",()=>e.CommitAsync(p1.Request.OperationId));Check(a.ApplyCalls==1);});
Test("zero Undo record fails closed",async()=>{var(a,s,e)=Setup();var p=Add(a);await e.PreviewAsync(p);a.ZeroUndo=true;await Throws("recovery-required",()=>e.CommitAsync(p.Request.OperationId));Check(a.Capture().Entities.Length==0&&s.Get(p.Request.OperationId)!.State==OperationState.FailedRecovery);});
Test("partial mutation quarantines further execution",async()=>{var(a,s,e)=Setup();var p=Add(a);await e.PreviewAsync(p);a.PartialFailure=true;await Throws("recovery-required",()=>e.CommitAsync(p.Request.OperationId));Check(s.Get(p.Request.OperationId) is {State:OperationState.FailedRecovery,BeforeCheckpoint:not null});await Throws("recovery-required",()=>e.PreviewAsync(Add(a,"BOX-002")));});
Test("pre-apply journal failure makes no document mutation",async()=>{var(a,s,e)=Setup();var p=Add(a);await e.PreviewAsync(p);s.FailState=OperationState.Applying;try{await e.CommitAsync(p.Request.OperationId);throw new Exception("no IO error");}catch(IOException){}Check(a.ApplyCalls==0);});
Test("lost durable completion does not report success",async()=>{var(a,s,e)=Setup();var p=Add(a);await e.PreviewAsync(p);s.FailState=OperationState.Committed;await Throws("recovery-required",()=>e.CommitAsync(p.Request.OperationId));Check(a.ApplyCalls==1&&s.Get(p.Request.OperationId)!.State==OperationState.FailedRecovery);await Throws("operation-state",()=>e.CommitAsync(p.Request.OperationId));});
Test("host Applying callback outside adapter mutation",async()=>{var(a,s,e)=Setup();var p=Add(a);await e.PreviewAsync(p);bool called=false;await e.CommitAsync(p.Request.OperationId,beforeApply:r=>{Check(a.ApplyCalls==0&&r.BeforeCheckpoint is not null&&s.Get(r.OperationId)!.State==OperationState.Applying);called=true;return Task.CompletedTask;});Check(called);});
Test("host Applying acknowledgement failure does not mutate",async()=>{var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);await Throws("recovery-required",()=>e.CommitAsync(p.Request.OperationId,beforeApply:r=>throw new IOException("lost network")));Check(a.ApplyCalls==0);});
Test("cancel during host acknowledgement prevents mutation",async()=>{var(a,s,e)=Setup();var p=Add(a);await e.PreviewAsync(p);using var c=new CancellationTokenSource();try{await e.CommitAsync(p.Request.OperationId,c.Token,beforeApply:r=>{c.Cancel();return Task.CompletedTask;});throw new Exception("no cancellation");}catch(OperationCanceledException){}Check(a.ApplyCalls==0&&s.Get(p.Request.OperationId)!.State==OperationState.Cancelled);});
Test("stale context after host boundary never mutates",async()=>{var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);await Throws("recovery-required",()=>e.CommitAsync(p.Request.OperationId,beforeApply:r=>{a.Touch();return Task.CompletedTask;}));Check(a.ApplyCalls==0);});
Test("actual effect mismatch does not commit",async()=>{var(a,s,e)=Setup();var p=Add(a);await e.PreviewAsync(p);a.BadOutcome=true;await Throws("recovery-required",()=>e.CommitAsync(p.Request.OperationId));Check(s.Get(p.Request.OperationId)!.State==OperationState.FailedRecovery);});
Test("native undo redo identity reconciles in fake",async()=>{var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);await e.CommitAsync(p.Request.OperationId);var entity=a.Capture().Entities[0];a.Undo();Check(a.Capture().Entities.Length==0);a.Redo();Check(a.Capture().Entities[0]==entity);});
Test("translate records exactly target effect",async()=>{var(a,_,e)=Setup();var p=Add(a);await e.PreviewAsync(p);await e.CommitAsync(p.Request.OperationId);var move=Translate(a);await e.PreviewAsync(move);var result=await e.CommitAsync(move.Request.OperationId);Check(result.Outcome!.Modified.Single()==move.Request.ObjectId);});
Test("checkpoint restore has pre-restore safeguard",async()=>{var(a,s,e)=Setup();var cp=a.CaptureCheckpoint();var p=Add(a);await e.PreviewAsync(p);await e.CommitAsync(p.Request.OperationId);var restore=Restore(a,cp);await e.PreviewAsync(restore);var r=await e.CommitAsync(restore.Request.OperationId);Check(r.BeforeCheckpoint!.Snapshot.Entities.Length==1&&a.Capture().Entities.Length==0&&s.Get(r.OperationId)!.State==OperationState.Committed);});
Test("restore payload hash binds target geometry",async()=>{var(a,_,e)=Setup();var cp=a.CaptureCheckpoint();var r=Restore(a,cp);await e.PreviewAsync(r);var altered=cp with {CreatedAt=cp.CreatedAt.AddSeconds(1)};var p=PlanValidator.Prepare(new(r.Request,a.Capture(),altered));await Throws("operation-conflict",()=>e.PreviewAsync(p));});
Test("restore cross-document checkpoint blocked",async()=>{var(a,_,_)=Setup();var cp=a.CaptureCheckpoint() with {DocumentId=Guid.NewGuid()};await Throws("invalid-restore",()=>Task.FromResult(Restore(a,cp)));});
Test("duplicate engineering IDs block QA",async()=>{var(a,_,_)=Setup();a.AddCollision();await Throws("identity-collision",()=>Task.FromResult(Add(a)));});
Test("unsupported unit and invalid tolerance block",async()=>{var(a,_,_)=Setup();var snap=a.Capture();await Throws("unsupported-units",()=>Task.Run(()=>PlanValidator.ValidateSnapshot(snap with {Units="None"})));await Throws("invalid-tolerance",()=>Task.Run(()=>PlanValidator.ValidateSnapshot(snap with {Tolerance=double.NaN})));});
Test("nonfinite geometry and unsupported tools blocked",async()=>{var(a,_,_)=Setup();var p=Add(a);await Throws("invalid-geometry",()=>Task.Run(()=>PlanValidator.Prepare(new(p.Request with {Box=p.Request.Box! with {Width=double.NaN}},a.Capture()))));await Throws("unsupported-tool",()=>Task.Run(()=>PlanValidator.Prepare(new(p.Request with {ToolId="code.exec"},a.Capture()))));});
Test("unknown JSON fields rejected",()=>{try{JsonSerializer.Deserialize<ToolRequest>("{\"unrestrictedCode\":\"malicious\"}",Protocol.Json);throw new Exception("accepted");}catch(JsonException){}return Task.CompletedTask;});
Test("durable restart replay and new-session protection",async()=>{var dir=Path.Combine(Path.GetTempPath(),"rhino-test-"+Guid.NewGuid().ToString("N"));var a=new FakeAdapter();Guid op;try{using(var s=new JsonOperationStore(dir)){var e=new ExecutionCoordinator(a,new ImmediateDispatcher(),s);var p=Add(a);op=p.Request.OperationId;await e.PreviewAsync(p);await e.CommitAsync(op);}a.Reopen();using(var s=new JsonOperationStore(dir)){var e=new ExecutionCoordinator(a,new ImmediateDispatcher(),s);var r=await e.CommitAsync(op);Check(r.State==OperationState.Committed&&a.ApplyCalls==1);}}finally{Directory.Delete(dir,true);}});
Test("corrupt persisted payload fails closed",async()=>{var dir=Path.Combine(Path.GetTempPath(),"rhino-corrupt-"+Guid.NewGuid().ToString("N"));var a=new FakeAdapter();try{Guid op;using(var s=new JsonOperationStore(dir)){var e=new ExecutionCoordinator(a,new ImmediateDispatcher(),s);var p=Add(a);op=p.Request.OperationId;await e.PreviewAsync(p);await e.CommitAsync(op);}var file=Path.Combine(dir,op.ToString("D")+".json");File.WriteAllText(file,File.ReadAllText(file).Replace("BOX-001","BOX-BAD"));using var read=new JsonOperationStore(dir);try{read.Get(op);throw new Exception("corruption accepted");}catch(InvalidDataException){}}finally{Directory.Delete(dir,true);}});
Test("misplaced valid journal file fails closed",async()=>{var dir=Path.Combine(Path.GetTempPath(),"rhino-misplaced-"+Guid.NewGuid().ToString("N"));var a=new FakeAdapter();try{Guid op;using(var s=new JsonOperationStore(dir)){var e=new ExecutionCoordinator(a,new ImmediateDispatcher(),s);var p=Add(a);op=p.Request.OperationId;await e.PreviewAsync(p);}var wrong=Guid.NewGuid();File.Move(Path.Combine(dir,op.ToString("D")+".json"),Path.Combine(dir,wrong.ToString("D")+".json"));using var read=new JsonOperationStore(dir);try{read.Get(wrong);throw new Exception("misplaced record accepted");}catch(InvalidDataException){}}finally{Directory.Delete(dir,true);}});
Test("crashed Applying record quarantines restart",async()=>{var(a,s,e)=Setup();var p=Add(a);await e.PreviewAsync(p);s.Put(s.Get(p.Request.OperationId)! with {State=OperationState.Applying,BeforeCheckpoint=a.CaptureCheckpoint()});var reopened=new ExecutionCoordinator(a,new ImmediateDispatcher(),s);await Throws("operation-state",()=>reopened.CommitAsync(p.Request.OperationId));await Throws("recovery-required",()=>reopened.PreviewAsync(Add(a,"BOX-002")));Check(a.ApplyCalls==0);});
Test("durable store excludes concurrent writers",()=>{var dir=Path.Combine(Path.GetTempPath(),"rhino-lock-"+Guid.NewGuid().ToString("N"));try{using var one=new JsonOperationStore(dir);try{using var two=new JsonOperationStore(dir);throw new Exception("second writer accepted");}catch(IOException){}}finally{Directory.Delete(dir,true);}return Task.CompletedTask;});

Test("plate batch preview cancel remains detached", async () => { var (a,s,e)=Setup();var p=Plates(a);var hash=a.Capture().SnapshotHash;await e.PreviewAsync(p);Check(a.Capture().SnapshotHash==hash);await e.RejectAsync(p.Request.OperationId);Check(a.ApplyCalls==0&&s.Get(p.Request.OperationId)!.State==OperationState.Cancelled);await Throws("operation-state",()=>e.CommitAsync(p.Request.OperationId)); });
Test("plate batch commits every exact entity in one adapter apply", async () => {var(a,_,e)=Setup();var p=Plates(a,3);await e.PreviewAsync(p);var r=await e.CommitAsync(p.Request.OperationId);Check(r.State==OperationState.Committed&&a.ApplyCalls==1&&r.Outcome!.UndoRecord==1&&r.Outcome.Added.Length==3);foreach(var plate in p.Request.Plates!)Check(a.Capture().Entities.Single(x=>x.EntityId==plate.EntityId).GeometryJson==JsonSerializer.Serialize(plate.Box));await e.CommitAsync(p.Request.OperationId);Check(a.ApplyCalls==1);});
Test("plate batch preserves existing managed fingerprints", async () => {var(a,_,e)=Setup();var box=Add(a);await e.PreviewAsync(box);await e.CommitAsync(box.Request.OperationId);var before=a.Capture().Entities.Single();var p=Plates(a);await e.PreviewAsync(p);await e.CommitAsync(p.Request.OperationId);Check(a.Capture().Entities.Single(x=>x.RhinoId==before.RhinoId)==before);});
Test("plate batch native undo redo retains all identities in fake", async () => {var(a,_,e)=Setup();var p=Plates(a);await e.PreviewAsync(p);await e.CommitAsync(p.Request.OperationId);var identities=Protocol.Hash(a.Capture().Entities);a.Undo();Check(a.Capture().Entities.Length==0);a.Redo();Check(Protocol.Hash(a.Capture().Entities)==identities);await e.CommitAsync(p.Request.OperationId);Check(a.ApplyCalls==1);});
Test("plate batch stale snapshot never applies", async () => {var(a,_,e)=Setup();var p=Plates(a);await e.PreviewAsync(p);a.Touch();await Throws("stale-context",()=>e.CommitAsync(p.Request.OperationId));Check(a.ApplyCalls==0);});
Test("plate batch cancellation at host boundary never applies", async () => {var(a,s,e)=Setup();var p=Plates(a);await e.PreviewAsync(p);using var c=new CancellationTokenSource();try{await e.CommitAsync(p.Request.OperationId,c.Token,r=>{c.Cancel();return Task.CompletedTask;});throw new Exception("no cancellation");}catch(OperationCanceledException){}Check(a.ApplyCalls==0&&s.Get(p.Request.OperationId)!.State==OperationState.Cancelled);});
Test("plate batch cancelled queued UI never applies",async()=>{var a=new FakeAdapter();var s=new MemoryStore();var dispatcher=new QueuedDispatcher();var e=new ExecutionCoordinator(a,dispatcher,s);var p=Plates(a);await e.PreviewAsync(p);dispatcher.HoldAt=4;using var c=new CancellationTokenSource();var task=e.CommitAsync(p.Request.OperationId,c.Token);await dispatcher.Queued.Task;c.Cancel();dispatcher.Release.TrySetResult();try{await task;throw new Exception("no cancel");}catch(OperationCanceledException){}Check(a.ApplyCalls==0&&s.Get(p.Request.OperationId)!.State==OperationState.Cancelled);});
Test("plate batch rejects duplicate engineering IDs",async()=>{var(a,_,_)=Setup();var p=Plates(a);var plates=p.Request.Plates!;await Throws("identity-collision",()=>Task.FromResult(PlanValidator.Prepare(new(p.Request with{Plates=[plates[0],plates[0]]},a.Capture()))));});
Test("plate batch rejects absent or mismatched provenance",async()=>{var(a,_,_)=Setup();var p=Plates(a);foreach(var provenance in new[]{null,p.Request.Provenance! with{InputSnapshotHash=new('D',64)},p.Request.Provenance! with{ManifestHash="unbound"},p.Request.Provenance! with{SkillId="other-skill"}})await Throws("invalid-provenance",()=>Task.FromResult(PlanValidator.Prepare(new(p.Request with{Provenance=provenance},a.Capture()))));});
Test("plate batch count bounded at 128",async()=>{var(a,_,_)=Setup();Check(Plates(a,128).Request.Plates!.Length==128);await Throws("plate-limit",()=>Task.FromResult(Plates(a,129)));await Throws("plate-limit",()=>Task.FromResult(Plates(a,0)));});
Test("plate batch requires explicit material and above tolerance thickness",async()=>{var(a,_,_)=Setup();var p=Plates(a);var plate=p.Request.Plates![0];await Throws("invalid-material",()=>Task.FromResult(PlanValidator.Prepare(new(p.Request with{Plates=[plate with{Material=""}]},a.Capture()))));await Throws("below-tolerance",()=>Task.FromResult(PlanValidator.Prepare(new(p.Request with{Plates=[plate with{Box=plate.Box with{Height=0.001}}]},a.Capture()))));});
Test("legacy box requests reject hidden plate arguments",async()=>{var(a,_,_)=Setup();var box=Add(a);var p=Plates(a);await Throws("invalid-arguments",()=>Task.FromResult(PlanValidator.Prepare(new(box.Request with{Plates=p.Request.Plates},a.Capture()))));});
Test("legacy serialized request shape remains unchanged",()=>{var(a,_,_)=Setup();var json=JsonSerializer.Serialize(Add(a).Request,Protocol.Json);Check(!json.Contains("plates")&&!json.Contains("provenance"));var roundtrip=JsonSerializer.Deserialize<ToolRequest>(json,Protocol.Json)!;Check(JsonSerializer.Serialize(roundtrip,Protocol.Json)==json);return Task.CompletedTask;});
Test("plate batch delta rejects duplicate GUIDs and missing entities",async()=>{var(a,_,e)=Setup();var p=Plates(a);await e.PreviewAsync(p);var r=await e.CommitAsync(p.Request.OperationId);var o=r.Outcome!;await Throws("effect-mismatch",()=>Task.Run(()=>ExecutionCoordinator.ValidateOutcome(p,o with{Added=[o.Added[0],o.Added[0]]})));await Throws("effect-mismatch",()=>Task.Run(()=>ExecutionCoordinator.ValidateOutcome(p,o with{Added=[]})));});
Test("plate batch delta rejects renamed or changed existing objects",async()=>{var(a,_,e)=Setup();var b=Add(a);await e.PreviewAsync(b);await e.CommitAsync(b.Request.OperationId);var p=Plates(a);await e.PreviewAsync(p);var r=await e.CommitAsync(p.Request.OperationId);var o=r.Outcome!;var altered=o.After with{Entities=o.After.Entities.Select(x=>x.EntityId=="BOX-001"?x with{Fingerprint="altered"}:x).ToArray()};await Throws("effect-mismatch",()=>Task.Run(()=>ExecutionCoordinator.ValidateOutcome(p,o with{After=altered})));});
Test("plate batch partial failure is quarantined with before image",async()=>{var(a,s,e)=Setup();var p=Plates(a);await e.PreviewAsync(p);a.PartialFailure=true;await Throws("recovery-required",()=>e.CommitAsync(p.Request.OperationId));Check(s.Get(p.Request.OperationId) is{State:OperationState.FailedRecovery,BeforeCheckpoint:not null});await Throws("recovery-required",()=>e.PreviewAsync(Plates(new FakeAdapter())));});
Test("plate batch fake compensation restores before image but stays quarantined",async()=>{var(a,s,e)=Setup();var p=Plates(a);await e.PreviewAsync(p);a.PartialFailure=true;a.CompensateFailure=true;await Throws("recovery-required",()=>e.CommitAsync(p.Request.OperationId));Check(a.Capture().Entities.Length==0&&s.Get(p.Request.OperationId)!.State==OperationState.FailedRecovery);});

Test("review JSON rejects duplicate fields before typed conversion",async()=>{await Throws("ambiguous-json",()=>Task.FromResult(StrictJsonInput.Deserialize<Point3>("{\"x\":1,\"x\":2,\"y\":0,\"z\":0}")));});
Test("review JSON rejects case-insensitive and escaped field collisions",async()=>{await Throws("ambiguous-json",()=>Task.FromResult(StrictJsonInput.Deserialize<Point3>("{\"x\":1,\"X\":2,\"y\":0,\"z\":0}")));await Throws("ambiguous-json",()=>Task.FromResult(StrictJsonInput.Deserialize<Point3>("{\"x\":1,\"\\u0078\":2,\"y\":0,\"z\":0}")));});
Test("review JSON rejects nested duplicate engineering values",async()=>{await Throws("ambiguous-json",()=>Task.FromResult(StrictJsonInput.Deserialize<BoxSpec>("{\"origin\":{\"x\":0,\"X\":1,\"y\":0,\"z\":0},\"width\":10,\"depth\":20,\"height\":3}")));await Throws("ambiguous-json",()=>Task.FromResult(StrictJsonInput.Deserialize<object>("{\"components\":[{\"thicknessMM\":3,\"ThicknessMM\":5}]}")));});
Test("review JSON enforces UTF8 byte budget",async()=>{await Throws("input-limit",()=>Task.FromResult(StrictJsonInput.Deserialize<object>("\""+new string('中',400000)+"\"")));});
Test("review JSON rejects excessive nesting and unknown fields",()=>{foreach(var json in new[]{new string('[',33)+"0"+new string(']',33),"{\"x\":1,\"y\":2,\"z\":3,\"hiddenThickness\":5}"}){try{StrictJsonInput.Deserialize<Point3>(json);throw new Exception("ambiguous/deep/unknown input accepted");}catch(JsonException){}}return Task.CompletedTask;});
Test("review JSON accepts unambiguous explicit input",()=>{var point=StrictJsonInput.Deserialize<Point3>("{\"X\":1,\"y\":2,\"z\":3}");Check(point==new Point3(1,2,3));return Task.CompletedTask;});

int failed=0;
foreach(var test in tests){try{await test.Run();Console.WriteLine("PASS "+test.Name);}catch(Exception ex){failed++;Console.WriteLine("FAIL "+test.Name+": "+ex);}}
Console.WriteLine($"RESULT {tests.Count-failed}/{tests.Count} passed. Fake adapter tests do not constitute live Rhino acceptance.");
return failed==0?0:1;

sealed class ImmediateDispatcher:IUiDispatcher { public Task<T> InvokeAsync<T>(Func<T> f,CancellationToken c=default){c.ThrowIfCancellationRequested();return Task.FromResult(f());} }
sealed class QueuedDispatcher:IUiDispatcher
{
    private int calls; public int HoldAt=-1;
    public TaskCompletionSource Queued=new(TaskCreationOptions.RunContinuationsAsynchronously),Release=new(TaskCreationOptions.RunContinuationsAsynchronously);
    public async Task<T> InvokeAsync<T>(Func<T> f,CancellationToken c=default){if(++calls==HoldAt){Queued.TrySetResult();await Release.Task;}c.ThrowIfCancellationRequested();return f();}
}
sealed class MemoryStore:IOperationStore
{
    private readonly Dictionary<Guid,OperationRecord> records=[];
    public OperationState? FailState;
    public OperationRecord? Get(Guid id)=>records.GetValueOrDefault(id);
    public IReadOnlyList<OperationRecord> List()=>records.Values.ToArray();
    public void Put(OperationRecord r){if(r.State==FailState)throw new IOException("injected durable storage failure");records[r.OperationId]=r;}
}
sealed class FakeAdapter:IDocumentAdapter
{
    private DocumentSnapshot doc=new(Guid.NewGuid(),Guid.NewGuid(),0,"Millimeters",0.01,[],[]);
    private DocumentSnapshot? before,after;
    private string? previewHash;
    public int ApplyCalls;public bool PreviewVisible,ZeroUndo,PartialFailure,BadOutcome,CompensateFailure;public Action? BeforeApply;
    public DocumentSnapshot Capture()=>doc;
    public void ShowPreview(ChangePlan p){PlanValidator.Match(p.Request.Expected,doc);PreviewVisible=true;previewHash=p.RequestHash;}
    public void ClearPreview(){PreviewVisible=false;previewHash=null;}
    public Checkpoint CaptureCheckpoint()=>new(Guid.NewGuid(),doc.DocumentId,DateTimeOffset.UtcNow,doc);
    public void Touch()=>doc=doc with{Revision=doc.Revision+1};
    public void Reopen()=>doc=doc with{SessionId=Guid.NewGuid(),Revision=0};
    public void SwitchDocument()=>doc=doc with{DocumentId=Guid.NewGuid()};
    public void Undo(){doc=before! with{SessionId=doc.SessionId,Revision=doc.Revision+1};}
    public void Redo(){doc=after! with{SessionId=doc.SessionId,Revision=doc.Revision+1};}
    public void AddCollision(){var id=Guid.NewGuid();doc=doc with{Entities=[new(id,"DUP","f","{}","{}","Brep",true),new(Guid.NewGuid(),"DUP","g","{}","{}","Brep",true)]};}
    public ApplyOutcome Apply(ChangePlan p)
    {
        if(previewHash!=p.RequestHash)throw new HarnessException("preview-required","Only displayed preview can apply");
        PlanValidator.Match(p.Request.Expected,doc);BeforeApply?.Invoke();ApplyCalls++;if(ZeroUndo)throw new HarnessException("undo-unavailable","BeginUndoRecord returned 0");before=doc;
        Guid[] added=[],modified=[];
        if(p.Request.ToolId=="box.add"){var entity=new EntitySnapshot(Guid.NewGuid(),p.Request.EntityId!,Protocol.Hash(p.Request.Box),JsonSerializer.Serialize(p.Request.Box),"{}","Brep",true);doc=doc with{Entities=[..doc.Entities,entity]};added=[entity.RhinoId];}
        else if(p.Request.ToolId=="cladding.plates.add"){var entities=p.Request.Plates!.Select(plate=>new EntitySnapshot(Guid.NewGuid(),plate.EntityId,Protocol.Hash(new{plate,p.Request.Provenance}),JsonSerializer.Serialize(plate.Box),JsonSerializer.Serialize(p.Request.Provenance),"Brep",true)).ToArray();doc=doc with{Entities=[..doc.Entities,..entities]};added=entities.Select(x=>x.RhinoId).ToArray();}
        else{var old=doc.Entities.Single(x=>x.RhinoId==p.Request.ObjectId);doc=doc with{Entities=doc.Entities.Select(x=>x==old?x with{Fingerprint="moved-"+x.Fingerprint}:x).ToArray()};modified=[old.RhinoId];}
        Touch();after=doc;if(PartialFailure){if(CompensateFailure)doc=before with{Revision=doc.Revision+1};throw new IOException("partial mutation simulated");}return new(doc,BadOutcome?[]:added,modified,[],1,[]);
    }
    public ApplyOutcome Restore(Checkpoint cp,ExpectedContext expected)
    {
        PlanValidator.Match(expected,doc);BeforeApply?.Invoke();ApplyCalls++;if(ZeroUndo)throw new HarnessException("undo-unavailable","BeginUndoRecord returned 0");before=doc;var deleted=doc.Entities.Select(x=>x.RhinoId).ToArray();doc=cp.Snapshot with{SessionId=doc.SessionId,Revision=doc.Revision+1};after=doc;return new(doc,doc.Entities.Select(x=>x.RhinoId).ToArray(),[],deleted,1,[]);
    }
}
