using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using RhinoAi.Contracts;
using RhinoAi.Core;
using RhinoAi.Host;

var results = new List<object>();
var failures = 0;
await Test("no model returns honest NOT_CONFIGURED", async () => {
    using var client = new LocalChatCompletionClient(LocalModelSettings.Parse(null, null));
    Assert((await new BoundedPlanner(client).PlanAsync(Input(), default)).Status == "NOT_CONFIGURED");
});
await Test("remote DNS aliases credentials paths and partial configuration rejected", () => {
    foreach (var endpoint in new[] { "https://api.openai.com/v1/chat/completions", "http://localhost:8080/v1/chat/completions", "http://[::1]:8080/v1/chat/completions", "http://127.1:8080/v1/chat/completions", "http://2130706433:8080/v1/chat/completions", "http://127.0.0.1:80/v1/chat/completions", "http://user:password@127.0.0.1:8080/v1/chat/completions", "http://127.0.0.1:8080/v1/chat/completions?key=x", "http://127.0.0.1:8080/arbitrary", "http://127.0.0.1:8080/v1/chat/completions#secret", null })
        Assert(LocalModelSettings.Parse(endpoint, "local-test").Status == "INVALID_CONFIGURATION");
    Assert(LocalModelSettings.Parse("http://127.0.0.1:8080/v1/chat/completions", null).Status == "INVALID_CONFIGURATION");
    return Task.CompletedTask;
});
await Test("actual synthetic HTTP local model produces grounded box plan without journal or execution", async () => {
    var input = Input(); await using var server = new FakeModel(_ => Reply(Decision(input)));
    var response = await Plan(server, input);
    Assert(response.Status == "tool" && response.Plan?.Request.ToolId == "box.add");
    Assert(response.ContextHash == PlanningProtocol.ContextHash(input.Expected, input.SelectedObjectIds));
    Assert(server.Requests == 1 && !server.LastBody.Contains("GEOMETRY_SECRET") && !server.LastBody.Contains("ATTRIBUTES_SECRET"));
    Assert(!server.LastAuthorization && server.LastBody.Contains("max_completion_tokens") && server.LastBody.Contains("json_object"));
});
await Test("anchored English and Chinese prompt values supported without typed inputs", async () => {
    var input = Input() with { Inputs = null, Prompt = "创建盒体：宽=10; 深=20; 高=30; 原点=(0,0,0); 工程编号=BOX-NEW" };
    await using var server = new FakeModel(_ => Reply(Decision(Input())));
    Assert((await Plan(server, input)).Status == "tool");
});
await Test("selection-backed one-step translation succeeds", async () => {
    var input = Input() with { Inputs = new(Translation: new(10, 0, 0)) };
    await using var server = new FakeModel(_ => Reply(new("tool", Tool: new("object.translate", ObjectId: input.SelectedObjectIds[0], Translation: input.Inputs.Translation))));
    Assert((await Plan(server, input)).Plan?.Request.ObjectId == input.SelectedObjectIds[0]);
});
await Test("missing dimensions origin and identifier clarify rather than invent", async () => {
    foreach (var input in new[] { Input() with { Inputs = null }, Input() with { Inputs = new(EntityId: "BOX-NEW") }, Input() with { Inputs = new(Box: Input().Inputs!.Box) }, Input() with { Inputs = null, Prompt = "width=10; depth=20; height=30; entityId=BOX-NEW" } })
    {
        await using var server = new FakeModel(_ => Reply(Decision(Input())));
        Assert((await Plan(server, input)).Status == "clarification");
    }
});
await Test("ambiguous duplicate dimensions and undeclared units do not become defaults", async () => {
    foreach (var prompt in new[] { "width=10; width=20; depth=20; height=30; origin=(0,0,0); entityId=BOX-NEW", "width=10mm; depth=20; height=30; origin=(0,0,0); entityId=BOX-NEW" })
    {
        await using var server = new FakeModel(_ => Reply(Decision(Input())));
        Assert((await Plan(server, Input() with { Inputs = null, Prompt = prompt })).Status == "clarification");
    }
});
await Test("missing selected target or vector clarifies", async () => {
    var source = Input();
    foreach (var input in new[] { source with { SelectedObjectIds = [], Inputs = new(Translation: new(10,0,0)) }, source with { Inputs = null } })
    {
        await using var server = new FakeModel(_ => Reply(new("tool", Tool: new("object.translate", ObjectId: source.SelectedObjectIds[0], Translation: new(10,0,0)))));
        Assert((await Plan(server, input)).Status == "clarification");
    }
});
await Test("invented target dimensions and vector are rejected", async () => {
    var input = Input();
    foreach (var decision in new[] { Decision(input) with { Tool = Decision(input).Tool! with { Box = input.Inputs!.Box! with { Width = 999 } } }, new PlannerDecision("tool", Tool: new("object.translate", ObjectId: Guid.NewGuid(), Translation: new(10,0,0))), new PlannerDecision("tool", Tool: new("object.translate", ObjectId: input.SelectedObjectIds[0], Translation: new(999,0,0))) })
    {
        await using var server = new FakeModel(_ => Reply(decision));
        await Reject(() => Plan(server, input with { Inputs = input.Inputs! with { Translation = new(10,0,0) } }), "planner-ungrounded");
    }
});
foreach (var pair in new[] { ("malformed", "{oops"), ("missing fields", "{}"), ("unknown fields", "{\"kind\":\"clarification\",\"message\":\"what?\",\"code\":\"run()\"}"), ("duplicate fields", "{\"kind\":\"clarification\",\"kind\":\"tool\",\"message\":\"what?\"}"), ("wrong case", "{\"Kind\":\"clarification\",\"message\":\"what?\"}"), ("multiple decisions", "[{\"kind\":\"clarification\"}]") })
    await Test("strict model decision rejects " + pair.Item1, async () => { await using var server = new FakeModel(_ => RawReply(pair.Item2)); await Reject(() => Plan(server, Input()), "invalid_model_decision"); });
foreach (var tool in new[] { "python.exec", "process.start", "checkpoint.restore", "cladding.plates.add", "file.write", "https://example.test" })
    await Test("planner rejects unsupported tool " + tool, async () => { await using var server = new FakeModel(_ => Reply(new("tool", Tool: new(tool)))); await Reject(() => Plan(server, Input()), "planner-tool"); });
await Test("untyped cladding request clarifies missing engineering inputs", async () => { await using var server = new FakeModel(_ => Reply(new("cladding.review"))); Assert((await Plan(server, Input())).Status == "clarification"); });
await Test("typed cladding proposal remains bound REVIEW-only input", async () => {
    var input=Input() with { SelectedObjectIds=[] }; var cladding=Cladding(input); input=input with {Inputs=new(Cladding:cladding)};
    await using var server=new FakeModel(_=>Reply(new("cladding.review")));
    var response=await Plan(server,input); Assert(response.Status=="cladding.review" && response.CladdingRequest==cladding && response.Plan is null);
});
await Test("missing cladding material grade density dimensions and targets clarify", async () => {
    var input=Input() with { SelectedObjectIds=[] }; var cladding=Cladding(input);
    foreach(var candidate in new[] { cladding with { Components=[cladding.Components[0] with { Material="" }] }, cladding with { Components=[cladding.Components[0] with { Grade="" }] }, cladding with { Components=[cladding.Components[0] with { DensityKgM3=0 }] }, cladding with { Components=[cladding.Components[0] with { WidthMM=0 }] }, cladding with { Components=[cladding.Components[0] with { HeightMM=0 }] }, cladding with { Components=[cladding.Components[0] with { ThicknessMM=0 }] }, cladding with { Targets=[] }, cladding with { Targets=["step"] } }) {
        await using var server=new FakeModel(_=>Reply(new("cladding.review"))); var result=await Plan(server,input with { Inputs=new(Cladding:candidate) });
        Assert(result.Status=="clarification" && result.Message.Contains('?') && result.CladdingRequest is null && result.Plan is null);
        try { CladdingReviewValidator.Validate(candidate); throw new Exception("Skill accepted missing data"); } catch(HarnessException) { }
    }
});
await Test("missing selected cladding sources ask user to select",async()=> {
    var input=Input() with { SelectedObjectIds=[] }; var cladding=Cladding(input) with { SourceMode="selected_managed" };
    await using var server=new FakeModel(_=>Reply(new("cladding.review"))); var result=await Plan(server,input with { Inputs=new(Cladding:cladding) });
    Assert(result.Status=="clarification" && result.Message.Contains("Select") && result.CladdingRequest is null);
});
await Test("malformed negative nonfinite unsupported cladding remains rejected",async()=> {
    var input=Input() with { SelectedObjectIds=[] }; var cladding=Cladding(input);
    foreach(var (candidate,code) in new[] { (cladding with { Components=[cladding.Components[0] with { WidthMM=-1 }] },"cladding-geometry"), (cladding with { Components=[cladding.Components[0] with { DensityKgM3=double.NaN }] },"cladding-density"), (cladding with { Components=[cladding.Components[0] with { Material="",WidthMM=-1 }] },"cladding-text"), (cladding with { Components=[cladding.Components[0] with { Material="",Features=["hole"] }] },"cladding-text"), (cladding with { Components=[cladding.Components[0] with { OriginMM=null! }] },"cladding-geometry"), (cladding with { Targets=["cnc"] },"cladding-targets") }) {
        await using var server=new FakeModel(_=>Reply(new("cladding.review"))); await Reject(()=>Plan(server,input with { Inputs=new(Cladding:candidate) }),code);
    }
});
await Test("cladding proposal snapshot and selected sources cannot diverge",async()=> {
    var input=Input() with { SelectedObjectIds=[] }; var cladding=Cladding(input);
    await using var server=new FakeModel(_=>Reply(new("cladding.review")));
    await Reject(()=>Plan(server,input with { Inputs=new(Cladding:cladding with { Expected=cladding.Expected with { Revision=2 } }) }),"stale-context");
    await Reject(()=>Plan(server,input with { Inputs=new(Cladding:cladding with { SelectedEntityIds=["INVENTED"] }) }),"planner-cladding-selection");
});
await Test("box bounds and zero movement still use established PlanValidator",async()=> {
    var input=Input(); var huge=input with { Inputs=new(new(new(0,0,0),10000001,10,10),"BOX-NEW") };
    await using var server=new FakeModel(_=>Reply(Decision(huge))); await Reject(()=>Plan(server,huge),"invalid-geometry");
    var zero=input with { Inputs=new(Translation:new(0,0,0)) };
    await using var translate=new FakeModel(_=>Reply(new("tool",Tool:new("object.translate",ObjectId:input.SelectedObjectIds[0],Translation:new(0,0,0)))));
    await Reject(()=>Plan(translate,zero),"empty-change");
});
await Test("external agent validates same grounded proposal without model", () => {
    var input = Input(); Assert(BoundedPlanner.Validate(input, Decision(input)).Status == "tool");
    Assert(BoundedPlanner.Validate(input, new("clarification", "Which dimensions?" )).Status == "clarification");
    return Task.CompletedTask;
});
await Test("stale snapshot invented selection and request limits fail before network", async () => {
    var input = Input();
    await using var server = new FakeModel(_ => Reply(Decision(input)));
    await Reject(() => Plan(server, input with { Expected = input.Expected with { Revision = 999 } }), "stale-context");
    await Reject(() => Plan(server, input with { SelectedObjectIds = [Guid.NewGuid()] }), "planner-selection");
    await Reject(() => Plan(server, input with { SelectedObjectIds = [input.SelectedObjectIds[0], input.SelectedObjectIds[0]] }), "planner-selection");
    await Reject(() => Plan(server, input with { Prompt = new string('a', 4097) }), "planner-prompt-limit");
    await Reject(() => Plan(server, input with { PlannerVersion = 1 }), "planner-version");
    Assert(server.Requests == 0);
});
await Test("context byte budget enforced before network", async () => {
    var input = Input() with { Prompt = new string('汉',4096) };
    var entities = Enumerable.Range(0,64).Select(i => input.Snapshot.Entities[0] with { RhinoId = Guid.NewGuid(), EntityId = "E" + i + new string('x',100) }).ToArray();
    var snapshot = input.Snapshot with { Entities = entities };
    input = input with { Snapshot = snapshot, Expected = PlanValidator.Expected(snapshot), SelectedObjectIds = [] };
    await using var server = new FakeModel(_ => Reply(Decision(Input())));
    await Reject(() => Plan(server, input), "model_input_limit"); Assert(server.Requests == 0);
});
await Test("redirect response not followed", async () => { await using var server = new FakeModel(_ => new("",302, Redirect: "http://127.0.0.1:1/secret")); await Reject(() => Plan(server,Input()),"model_http"); Assert(server.Requests == 1); });
await Test("oversize Content-Length response rejected", async () => { await using var server = new FakeModel(_ => new(new string('x',65_537))); await Reject(() => Plan(server,Input()),"model_response_limit"); });
await Test("oversize chunked response rejected", async () => { await using var server = new FakeModel(_ => new(new string('x',65_537),Chunked:true)); await Reject(() => Plan(server,Input()),"model_response_limit"); });
await Test("wrong response content type rejected", async () => { await using var server = new FakeModel(_ => new("{}",ContentType:"text/plain")); await Reject(() => Plan(server,Input()),"model_content_type"); });
await Test("encoded response rejected", async () => { await using var server = new FakeModel(_ => new("{}",Encoding:"gzip")); await Reject(() => Plan(server,Input()),"model_content_type"); });
foreach (var mode in new[] { "unknown", "duplicate", "missing", "multi-choice", "length", "tool-calls", "tokens", "wrong-type" })
    await Test("strict completion envelope rejects " + mode, async () => {
        var node = JsonNode.Parse(Reply(Decision(Input())).Body)!;
        switch(mode) {
            case "unknown": node["arbitrary"] = "code"; break;
            case "missing": node.AsObject().Remove("choices"); break;
            case "multi-choice": node["choices"]!.AsArray().Add(node["choices"]![0]!.DeepClone()); break;
            case "length": node["choices"]![0]!["finish_reason"] = "length"; break;
            case "tool-calls": node["choices"]![0]!["message"]!["tool_calls"] = new JsonArray(); break;
            case "tokens": node["usage"] = new JsonObject { ["prompt_tokens"] = 10, ["completion_tokens"] = 1025, ["total_tokens"] = 1035 }; break;
            case "wrong-type": node["choices"]![0]!["index"] = "zero"; break;
        }
        var body = mode == "duplicate" ? node.ToJsonString().Insert(1,"\"choices\":[],") : node.ToJsonString();
        await using var server = new FakeModel(_ => new(body)); await Reject(() => Plan(server,Input()),"invalid_model_response");
    });
await Test("hard timeout no retries", async () => { await using var server = new FakeModel(_ => Reply(Decision(Input())) with { DelayMs = 500 }); await Reject(() => Plan(server,Input(),TimeSpan.FromMilliseconds(100)),"model_timeout"); Assert(server.Requests == 1); });
await Test("caller cancellation remains cancellation and makes no retry", async () => {
    await using var server = new FakeModel(_ => Reply(Decision(Input())) with { DelayMs = 500 });
    using var client = new LocalChatCompletionClient(LocalModelSettings.Parse(server.Endpoint,"synthetic-test")); using var ct = new CancellationTokenSource(100);
    try { await new BoundedPlanner(client).PlanAsync(Input(),ct.Token); throw new Exception("No cancellation"); } catch (OperationCanceledException) { }
    Assert(server.Requests == 1);
});
await Test("concurrent local model work rejected instead of queued", async () => {
    await using var server = new FakeModel(_ => Reply(Decision(Input())) with { DelayMs = 200 });
    using var client = new LocalChatCompletionClient(LocalModelSettings.Parse(server.Endpoint,"synthetic-test")); var planner = new BoundedPlanner(client);
    var first = planner.PlanAsync(Input(),default);
    await Reject(() => planner.PlanAsync(Input(),default),"planner_busy"); await first; Assert(server.Requests == 1);
});

// Actual authenticated Host process and HTTP routes, using only the synthetic loopback model.
var moduleRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../"));
var configuration = new DirectoryInfo(AppContext.BaseDirectory).Parent!.Name;
var dotnet = args.Length > 1 ? Path.GetFullPath(args[1]) : Environment.ProcessPath!;
var hostDll = args.Length > 2 ? Path.GetFullPath(args[2]) : Path.Combine(moduleRoot,"src","RhinoAi.Host","bin",configuration,"net8.0","RhinoAi.Host.dll");
var hostRunRoot = Path.Combine(moduleRoot,"artifacts","workbuddy-runs","planning-http-"+DateTime.UtcNow.ToString("yyyyMMddTHHmmssZ")+"-"+Guid.NewGuid().ToString("N")[..8]);
Directory.CreateDirectory(hostRunRoot);
FakeReply hostReply = Reply(Decision(Input()));
await using (var server = new FakeModel(_ => hostReply))
using (var process = await ActualHost.Start(dotnet,hostDll,Path.Combine(hostRunRoot,"configured"),server.Endpoint))
{
    await Test("actual Host health exposes bounded planner and REVIEW",async()=> {
        var text = await process.Client.GetStringAsync("health"); Assert(text.Contains("READY") && text.Contains("REVIEW") && text.Contains("plannerVersion"));
    });
    await Test("actual Host capabilities are authenticated bounded and REVIEW-only",async()=> {
        using var document=JsonDocument.Parse(await process.Client.GetStringAsync("v2/capabilities")); var cap=document.RootElement;
        Assert(cap.GetProperty("plannerVersion").GetInt32()==2 && !cap.GetProperty("manufacturingRelease").GetBoolean());
        Assert(cap.GetProperty("planner").GetProperty("maximumTurns").GetInt32()==1 && cap.GetProperty("planner").GetProperty("maximumSelectedObjects").GetInt32()==16);
        using var client=new HttpClient { BaseAddress=process.Client.BaseAddress }; await HttpStatus(await client.GetAsync("v2/capabilities"),401);
    });
    var input = Input();
    await Test("actual Host local planning returns proposal without journal preparation",async()=> {
        var response=await process.Post("v2/plan",input); await HttpStatus(response,200);
        var output=StrictJson.Parse<PlannerResponse>(await response.Content.ReadAsStringAsync());
        Assert(output.Status=="tool" && output.Plan?.Request.OperationId==input.OperationId);
        await HttpStatus(await process.Client.GetAsync("v1/operations/"+input.OperationId),404);
    });
    await Test("actual Host external validation uses same contract without model call",async()=> {
        var count=server.Requests; await HttpStatus(await process.Post("v2/plan/validate",new PlannerValidationRequest(input,Decision(input))),200); Assert(server.Requests==count);
    });
    await Test("actual Host explicit prepare retains existing preview transaction boundary",async()=> {
        var plan=BoundedPlanner.Validate(input,Decision(input)).Plan!;
        await HttpStatus(await process.Post("v1/prepare",new PrepareRequest(plan.Request,input.Snapshot)),200);
        var record=StrictJson.Parse<OperationRecord>(await process.Client.GetStringAsync("v1/operations/"+input.OperationId));
        Assert(record.State==OperationState.Prepared && record.Outcome is null);
    });
    await Test("actual Host planning strict request fields duplicate keys and selection checked",async()=> {
        var node=JsonSerializer.SerializeToNode(input,Protocol.Json)!; node["arbitraryCode"]="run()";
        await HttpStatus(await process.Raw("v2/plan",node.ToJsonString()),400);
        var raw=JsonSerializer.Serialize(input,Protocol.Json); await HttpStatus(await process.Raw("v2/plan",raw.Insert(1,"\"prompt\":\"duplicate\",")),400);
        await HttpStatus(await process.Post("v2/plan",input with { SelectedObjectIds=[Guid.NewGuid()] }),400);
        await HttpStatus(await process.Raw("v2/plan/validate","{}"),400);
    });
    await Test("actual Host strict model response failure is typed and leaves no journal",async()=> {
        hostReply=RawReply("{\"kind\":\"tool\",\"tool\":{\"toolId\":\"python.exec\"}}");
        var candidate=Input(); var response=await process.Post("v2/plan",candidate); await HttpStatus(response,400);
        Assert((await response.Content.ReadAsStringAsync()).Contains("planner-tool"));
        await HttpStatus(await process.Client.GetAsync("v1/operations/"+candidate.OperationId),404);
        hostReply=Reply(Decision(Input()));
    });
    await Test("actual Host rejects Origin and missing authorization on new planner routes",async()=> {
        using var client=new HttpClient { BaseAddress=process.Client.BaseAddress };
        await HttpStatus(await client.PostAsync("v2/plan",new StringContent("{}",Encoding.UTF8,"application/json")),401);
        using var req=new HttpRequestMessage(HttpMethod.Post,"v2/plan") {Content=new StringContent("{}",Encoding.UTF8,"application/json")}; req.Headers.Add("Origin","https://example.test");
        await HttpStatus(await process.Client.SendAsync(req),403);
    });
    await Test("actual Host logs exclude prompt model response bearer and geometry",()=> {
        Assert(!process.Output.Contains(input.Prompt) && !process.Output.Contains("GEOMETRY_SECRET") && !process.Output.Contains(process.Nonce) && !process.Output.Contains("python.exec")); return Task.CompletedTask;
    });
}
using (var process = await ActualHost.Start(dotnet,hostDll,Path.Combine(hostRunRoot,"unconfigured"),null))
{
    await Test("actual Host absent model returns NOT_CONFIGURED and structured tools remain usable",async()=> {
        var input=Input(); var output=await process.Post("v2/plan",input); await HttpStatus(output,200); Assert((await output.Content.ReadAsStringAsync()).Contains("NOT_CONFIGURED"));
        await HttpStatus(await process.Client.GetAsync("v2/capabilities"),200);
        await HttpStatus(await process.Post("v2/plan/validate",new PlannerValidationRequest(input,Decision(input))),200);
        var plan=BoundedPlanner.Validate(input,Decision(input)).Plan!;
        await HttpStatus(await process.Post("v1/prepare",new PrepareRequest(plan.Request,input.Snapshot)),200);
    });
}
using (var process = await ActualHost.Start(dotnet,hostDll,Path.Combine(hostRunRoot,"invalid-config"),"https://api.openai.com/v1/chat/completions"))
{
    await Test("actual Host rejects remote model configuration without breaking existing tools",async()=> {
        var input=Input(); var output=await process.Post("v2/plan",input); await HttpStatus(output,200); Assert((await output.Content.ReadAsStringAsync()).Contains("INVALID_CONFIGURATION"));
        await HttpStatus(await process.Post("v2/plan/validate",new PlannerValidationRequest(input,Decision(input))),200);
    });
}
Console.WriteLine($"SYNTHETIC LOCAL MODEL TESTS: {results.Count - failures}/{results.Count} passed; real model quality NOT_RUN; Windows/Rhino NOT_RUN.");
if (args.Length > 0) { Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[0]))!); await File.WriteAllTextAsync(args[0], JsonSerializer.Serialize(new { source = "synthetic-loopback-http-model", realModel = "NOT_RUN", windowsRhino = "NOT_RUN", results }, Protocol.Json)); }
return failures == 0 ? 0 : 1;

async Task Test(string name, Func<Task> test) { try { await test(); results.Add(new { name, status="PASS" }); Console.WriteLine("PASS " + name); } catch(Exception ex) { failures++; results.Add(new { name,status="FAIL",error=ex.Message }); Console.WriteLine("FAIL " + name + ": " + ex.Message); } }
static async Task HttpStatus(HttpResponseMessage response,int status) { if((int)response.StatusCode!=status) throw new Exception($"Expected HTTP {status}, got {(int)response.StatusCode}: {await response.Content.ReadAsStringAsync()}"); }
static void Assert(bool condition) { if(!condition) throw new Exception("Assertion failed"); }
static async Task Reject(Func<Task<PlannerResponse>> action,string code) { try { await action(); } catch(HostHttpException ex) when(ex.Code==code) { return; } catch(HarnessException ex) when(ex.Code==code) { return; } throw new Exception("Expected " + code); }
static PlannerRequest Input() {
    var entity = new EntitySnapshot(Guid.Parse("40000000-0000-0000-0000-000000000001"),"BOX-OLD","verified","GEOMETRY_SECRET","ATTRIBUTES_SECRET","box",true);
    var s = new DocumentSnapshot(Guid.Parse("10000000-0000-0000-0000-000000000001"),Guid.Parse("20000000-0000-0000-0000-000000000001"),0,"Millimeters",0.01,[entity],[]);
    return new(2,Guid.NewGuid(),Guid.NewGuid(),"Create a box using my explicit inputs.",PlanValidator.Expected(s),s,[entity.RhinoId],new(new(new(0,0,0),10,20,30),"BOX-NEW"));
}
static CladdingReviewRequest Cladding(PlannerRequest input) => new(Protocol.Version,Guid.NewGuid(),input.Expected,input.Snapshot,"explicit_design",[],[],[new("PLATE-NEW","Explicit plate",new(0,0,0),100,50,3,"Aluminum","3003",2730,1,[])],["step","drawings","bom","nesting"]);
static PlannerDecision Decision(PlannerRequest input) => new("tool",Tool:new("box.add",input.Inputs!.Box,input.Inputs.EntityId));
static FakeReply Reply(PlannerDecision decision) => RawReply(JsonSerializer.Serialize(decision,Protocol.Json));
static FakeReply RawReply(string content) => new(JsonSerializer.Serialize(new { id="synthetic", @object="chat.completion", created=0, model="synthetic-test", choices=new[] { new { index=0,message=new {role="assistant",content},finish_reason="stop" } } }));
static async Task<PlannerResponse> Plan(FakeModel server,PlannerRequest input,TimeSpan? timeout=null) { using var client = new LocalChatCompletionClient(LocalModelSettings.Parse(server.Endpoint,"synthetic-test") with { Timeout = timeout ?? TimeSpan.FromSeconds(2) }); return await new BoundedPlanner(client).PlanAsync(input,default); }
sealed record FakeReply(string Body,int Status=200,string ContentType="application/json",bool Chunked=false,string? Redirect=null,string? Encoding=null,int DelayMs=0);
sealed class FakeModel : IAsyncDisposable {
    private readonly HttpListener _listener = new(); private readonly CancellationTokenSource _stop = new(); private readonly Task _loop;
    public string Endpoint {get;} public int Requests {get;private set;} public string LastBody {get;private set;}=""; public bool LastAuthorization {get;private set;}
    public FakeModel(Func<string,FakeReply> respond) {
        var tcp = new TcpListener(IPAddress.Loopback,0); tcp.Start(); var port=((IPEndPoint)tcp.LocalEndpoint).Port; tcp.Stop();
        Endpoint=$"http://127.0.0.1:{port}/v1/chat/completions"; _listener.Prefixes.Add($"http://127.0.0.1:{port}/"); _listener.Start();
        _loop=Task.Run(async()=> { while(!_stop.IsCancellationRequested) { HttpListenerContext ctx; try {ctx=await _listener.GetContextAsync().WaitAsync(_stop.Token);} catch(Exception e) when(e is HttpListenerException or OperationCanceledException or ObjectDisposedException) {break;}
            try { Requests++; using var reader=new StreamReader(ctx.Request.InputStream); LastBody=await reader.ReadToEndAsync(_stop.Token); LastAuthorization=ctx.Request.Headers["Authorization"] is not null; var reply=respond(LastBody); if(reply.DelayMs>0) await Task.Delay(reply.DelayMs,_stop.Token); ctx.Response.StatusCode=reply.Status; ctx.Response.ContentType=reply.ContentType; if(reply.Redirect is not null)ctx.Response.RedirectLocation=reply.Redirect; if(reply.Encoding is not null)ctx.Response.Headers["Content-Encoding"]=reply.Encoding; var bytes=System.Text.Encoding.UTF8.GetBytes(reply.Body); if(reply.Chunked)ctx.Response.SendChunked=true;else ctx.Response.ContentLength64=bytes.Length; await ctx.Response.OutputStream.WriteAsync(bytes,_stop.Token);ctx.Response.Close(); }
            catch(Exception e) when(e is HttpListenerException or OperationCanceledException or ObjectDisposedException or IOException) {ctx.Response.Abort();}
        }});
    }
    public async ValueTask DisposeAsync() { _stop.Cancel();_listener.Close(); await _loop; _stop.Dispose(); }
}

sealed class ActualHost : IDisposable {
    private readonly Process _process; private readonly StringBuilder _output = new();
    public HttpClient Client {get;} public string Nonce {get;}
    public string Output {get {lock(_output)return _output.ToString();}}
    private ActualHost(Process process,int port,string nonce) { _process=process;Nonce=nonce;Client=new HttpClient(new SocketsHttpHandler {AllowAutoRedirect=false,UseProxy=false}) {BaseAddress=new Uri($"http://127.0.0.1:{port}/"),Timeout=TimeSpan.FromSeconds(30)};Client.DefaultRequestHeaders.Authorization=new("Bearer",nonce); }
    public static async Task<ActualHost> Start(string dotnet,string dll,string state,string? endpoint) {
        var tcp=new TcpListener(IPAddress.Loopback,0);tcp.Start();var port=((IPEndPoint)tcp.LocalEndpoint).Port;tcp.Stop();
        var nonce=Convert.ToHexString(System.Security.Cryptography.RandomNumberGenerator.GetBytes(32));
        var info=new ProcessStartInfo(dotnet) {RedirectStandardOutput=true,RedirectStandardError=true,UseShellExecute=false,CreateNoWindow=true};info.ArgumentList.Add(dll);
        info.Environment["RHINOAI_SESSION_NONCE"]=nonce;info.Environment["RHINOAI_PORT"]=port.ToString(System.Globalization.CultureInfo.InvariantCulture);info.Environment["RHINOAI_STATE_DIR"]=state;
        foreach(var key in new[]{"RHINOAI_MODEL_ENDPOINT","RHINOAI_MODEL","RHINOAI_CLADDING_PYTHON","RHINOAI_CLADDING_SKILL_ROOT","RHINOAI_CLADDING_ADAPTER_ROOT"})info.Environment.Remove(key);
        if(endpoint is not null) {info.Environment["RHINOAI_MODEL_ENDPOINT"]=endpoint;info.Environment["RHINOAI_MODEL"]="synthetic-test";}
        var process=Process.Start(info) ?? throw new Exception("Host could not start");var host=new ActualHost(process,port,nonce);
        process.OutputDataReceived+=(_,e)=>{if(e.Data is not null)lock(host._output)host._output.AppendLine(e.Data);};process.ErrorDataReceived+=(_,e)=>{if(e.Data is not null)lock(host._output)host._output.AppendLine(e.Data);};process.BeginOutputReadLine();process.BeginErrorReadLine();
        try {for(var i=0;i<100;i++) {if(process.HasExited)throw new Exception("Host exited: "+host.Output);try {var response=await host.Client.GetAsync("health");if(response.IsSuccessStatusCode)return host;}catch(HttpRequestException){}await Task.Delay(50);}throw new Exception("Host startup timeout");}catch {host.Dispose();throw;}
    }
    public Task<HttpResponseMessage> Post<T>(string path,T value)=>Raw(path,JsonSerializer.Serialize(value,Protocol.Json));
    public Task<HttpResponseMessage> Raw(string path,string json)=>Client.PostAsync(path,new StringContent(json,Encoding.UTF8,"application/json"));
    public void Dispose() {Client.Dispose();try{if(!_process.HasExited)_process.Kill(entireProcessTree:true);_process.WaitForExit(3000);}catch(InvalidOperationException){}_process.Dispose();}
}
