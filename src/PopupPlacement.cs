using System;
using System.Drawing;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace ChargeviewNative
{
    static class PopupPlacement
    {
        [StructLayout(LayoutKind.Sequential)]
        internal struct NativeRect
        {
            public int Left,Top,Right,Bottom;
            public Rectangle Rectangle {get{return Rectangle.FromLTRB(Left,Top,Right,Bottom);}}
        }
        [DllImport("user32.dll")]static extern uint GetDpiForWindow(IntPtr window);

        internal static float FitScale(Size logical,Rectangle area,float requested)
        {
            float availableWidth=Math.Max(1,area.Width-24);
            float availableHeight=Math.Max(1,area.Height-24);
            return Math.Max(.1f,Math.Min(requested,Math.Min(availableWidth/logical.Width,availableHeight/logical.Height)));
        }
        internal static Rectangle Bounds(Size logical,Rectangle area,float scale,Point? anchor)
        {
            int width=(int)Math.Round(logical.Width*scale),height=(int)Math.Round(logical.Height*scale);
            int margin=(int)Math.Round(12*scale);
            int x=anchor.HasValue?anchor.Value.X-width/2:area.Right-width-margin;
            int y=anchor.HasValue?anchor.Value.Y-height-(int)Math.Round(5*scale):area.Bottom-height-margin;
            return new Rectangle(Math.Max(area.Left,Math.Min(x,area.Right-width)),
                Math.Max(area.Top,Math.Min(y,area.Bottom-height)),width,height);
        }
        internal static Screen RefreshScreen(Screen screen)
        {
            return Screen.AllScreens.FirstOrDefault(candidate=>screen!=null && candidate.DeviceName==screen.DeviceName) ?? Screen.PrimaryScreen;
        }
        internal static void Place(Form window,PopupSurface surface,Size logical,Screen target,Point? anchor,float? requested=null)
        {
            if(surface.Placing)return;
            surface.Placing=true;
            try
            {
                Screen screen=RefreshScreen(target);
                if(screen==null)return;
                Rectangle area=screen.WorkingArea;
                if(Screen.FromHandle(window.Handle).DeviceName!=screen.DeviceName)
                    window.Location=new Point(area.Left+12,area.Top+12);
                float dpi;
                if(requested.HasValue)dpi=requested.Value;
                else
                {
                    try{dpi=GetDpiForWindow(window.Handle)/96f;}
                    catch(EntryPointNotFoundException){using(var graphics=window.CreateGraphics())dpi=graphics.DpiX/96f;}
                }
                if(dpi<=0)dpi=1;
                float scale=FitScale(logical,area,dpi);
                if(Math.Abs(surface.ScaleFactor-scale)>.0001f)
                {
                    surface.ScaleFactor=scale;
                    surface.ReleaseArtwork();
                }
                window.Bounds=Bounds(logical,area,scale,anchor);
                Round(window,surface.ScaleFactor,surface.Mode==2?14:18);
                surface.Invalidate();
            }
            finally{surface.Placing=false;}
        }
        internal static void Round(Form form,float scale,int radius)
        {
            if(form.Width<=0 || form.Height<=0)return;
            using(var shape=DeviceCard.Rounded(new Rectangle(0,0,form.Width,form.Height),(int)Math.Round(radius*scale)))
            {
                Region old=form.Region;form.Region=new Region(shape);
                if(old!=null)old.Dispose();
            }
        }
    }

    sealed class PopupMenu : Form
    {
        readonly PopupSurface surface;
        readonly Point anchor;
        public PopupMenu(PopupSurface content,Point location)
        {
            surface=content;anchor=location;
            Text="Chargeview menu";FormBorderStyle=FormBorderStyle.None;ShowInTaskbar=false;TopMost=true;
            StartPosition=FormStartPosition.Manual;AutoScaleMode=AutoScaleMode.None;
            BackColor=Artwork.Color("#131217");Opacity=0;KeyPreview=true;
            Controls.Add(surface);surface.Dock=DockStyle.Fill;
            Place(Screen.FromPoint(anchor));
        }
        void Place(Screen screen,float? scale=null)
        {PopupPlacement.Place(this,surface,new Size(291,168),screen,anchor,scale);}
        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            if(surface!=null)PopupPlacement.Round(this,surface.ScaleFactor,14);
        }
        protected override void WndProc(ref Message message)
        {
            if(message.Msg==0x02E0 && surface!=null)
            {
                if(!surface.Placing)
                {
                    var bounds=((PopupPlacement.NativeRect)Marshal.PtrToStructure(message.LParam,typeof(PopupPlacement.NativeRect))).Rectangle;
                    Place(Screen.FromRectangle(bounds),(message.WParam.ToInt64()&0xffff)/96f);
                }
                message.Result=IntPtr.Zero;return;
            }
            int kind=message.Msg;
            base.WndProc(ref message);
            if((kind==0x007E || kind==0x001A) && surface!=null && IsHandleCreated && !IsDisposed)
                BeginInvoke(new Action(()=>{if(!IsDisposed)Place(Screen.PrimaryScreen);}));
        }
    }
}
