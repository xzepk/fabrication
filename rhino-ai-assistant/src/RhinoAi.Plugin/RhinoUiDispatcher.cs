using Rhino;
using RhinoAi.Contracts;

namespace RhinoAi.Plugin;

public sealed class RhinoUiDispatcher : IUiDispatcher
{
    public Task<T> InvokeAsync<T>(Func<T> action, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(action);
        if (cancellationToken.IsCancellationRequested) return Task.FromCanceled<T>(cancellationToken);
        if (!RhinoApp.InvokeRequired)
        {
            try { return Task.FromResult(action()); }
            catch (Exception ex) { return Task.FromException<T>(ex); }
        }
        var completion = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        RhinoApp.InvokeOnUiThread((Action)(() =>
        {
            // Cancellation is honored before entry only. Synchronous Rhino mutation must finish/recover.
            if (cancellationToken.IsCancellationRequested) { completion.TrySetCanceled(cancellationToken); return; }
            try { completion.TrySetResult(action()); }
            catch (Exception ex) { completion.TrySetException(ex); }
        }));
        return completion.Task;
    }
    public static void RequireUiThread()
    {
        if (RhinoApp.InvokeRequired) throw new HarnessException("ui-thread", "Live Rhino document access requires the Rhino UI thread.");
    }
}
