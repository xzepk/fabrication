using Rhino.Display;
using Rhino.Geometry;

namespace RhinoAi.Plugin;

/// <summary>Only detached geometry is retained. Never adds preview objects to the Rhino object table.</summary>
internal sealed class DetachedPreviewConduit : DisplayConduit, IDisposable
{
    private readonly uint _documentSerial;
    private Brep[] _geometry;
    public DetachedPreviewConduit(uint documentSerial, Brep[] geometry)
    {
        _documentSerial = documentSerial;
        _geometry = geometry;
    }
    protected override void CalculateBoundingBox(CalculateBoundingBoxEventArgs e)
    {
        if (e.RhinoDoc?.RuntimeSerialNumber == _documentSerial )
            foreach (var geometry in _geometry) e.IncludeBoundingBox(geometry.GetBoundingBox(true));
    }
    protected override void PostDrawObjects(DrawEventArgs e)
    {
        if (e.RhinoDoc?.RuntimeSerialNumber == _documentSerial )
            foreach (var geometry in _geometry) e.Display.DrawBrepWires(geometry, System.Drawing.Color.DeepSkyBlue, 1);
    }
    public void Dispose() { Enabled = false; foreach (var geometry in _geometry) geometry.Dispose(); _geometry = []; }
}
