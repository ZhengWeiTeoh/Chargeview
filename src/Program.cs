using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace ChargeviewNative
{
    static class Program
    {
        [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr value);
        [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
        [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern uint RegisterWindowMessage(string text);
        [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h,uint msg,IntPtr w,IntPtr l);
        const uint Broadcast=0xffff;
        [STAThread] static int Main(string[] args)
        {
            try
            {
                if (args.Contains("--self-test")) return SelfTest.Run();
                if (args.Contains("--startup") && !Startup.Enabled()) return 0;
                uint show=RegisterWindowMessage("ChargeviewNative.Show");
                if(args.Contains("--stop"))
                {
                    EventWaitHandle signal;
                    if(EventWaitHandle.TryOpenExisting(@"Local\ChargeviewNative.StopSignal",out signal))
                        using(signal) signal.Set();
                    return 0;
                }
                using (var mutex=new Mutex(false,@"Local\ChargeviewNative.Singleton"))
                {
                    bool owned;
                    try {owned=mutex.WaitOne(0);} catch(AbandonedMutexException){owned=true;}
                    if (!owned)
                    {
                        if (!args.Contains("--startup") && !args.Contains("--tray"))
                        {
                            EventWaitHandle signal;
                            if(EventWaitHandle.TryOpenExisting(@"Local\ChargeviewNative.ShowSignal",out signal))
                                using(signal)signal.Set();
                        }
                        return 0;
                    }
                    try
                    {
                        try {SetProcessDpiAwarenessContext(new IntPtr(-4));} catch(EntryPointNotFoundException){SetProcessDPIAware();}
                        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
                        Application.Run(new MainWindow(show,args.Contains("--tray") || args.Contains("--startup")));
                    }
                    finally {mutex.ReleaseMutex();}
                }
                return 0;
            }
            catch(Exception error) {MessageBox.Show(error.Message,"Chargeview Native",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}
        }
    }

    sealed class MainWindow : Form
    {
        readonly NotifyIcon tray=new NotifyIcon();
        readonly CancellationTokenSource stop=new CancellationTokenSource();
        readonly EventWaitHandle exitSignal=new EventWaitHandle(false,EventResetMode.AutoReset,@"Local\ChargeviewNative.StopSignal");
        readonly EventWaitHandle showSignal=new EventWaitHandle(false,EventResetMode.AutoReset,@"Local\ChargeviewNative.ShowSignal");
        readonly System.Windows.Forms.Timer timer=new System.Windows.Forms.Timer();
        readonly uint showMessage;
        readonly uint stopMessage;
        readonly bool hidden;
        readonly Preferences preferences=Preferences.Load();
        readonly Battery[] readings={new Battery("Rapoo VT3 V2","Rapoo HID telemetry"),new Battery("WOBKEY Crush80","Windows Bluetooth LE")};
        readonly PopupSurface view=new PopupSurface();
        Form menu;
        Fade animation;
        Icon ownedIcon;
        Task refreshTask;
        bool loading,exiting,showingSettings,firstVisibility=true;
        int profileTicks;
        Screen displayScreen=Screen.PrimaryScreen;

        public MainWindow(uint message,bool startHidden)
        {
            showMessage=message;hidden=startHidden;
            stopMessage=RegisterWindowMessage("ChargeviewNative.Stop");
            Text="Chargeview Native";BackColor=Artwork.Color("#171429");ForeColor=Color.White;
            FormBorderStyle=FormBorderStyle.None;MaximizeBox=false;MinimizeBox=false;ShowInTaskbar=false;
            AutoScaleMode=AutoScaleMode.None;KeyPreview=true;
            Controls.Add(view);view.Dock=DockStyle.Fill;view.Readings=readings;view.Interval=preferences.Interval;
            PositionPanel();
            animation=new Fade(this);
            view.Command=HandleCommand;
            KeyDown+=(s,e)=>{if(e.KeyCode==Keys.Escape)animation.To(0,Hide);};
            tray.Text="Chargeview Native";
            tray.MouseUp+=(s,e)=>{if(e.Button==MouseButtons.Left)OpenPanel();else if(e.Button==MouseButtons.Right)OpenMenu();};
            UpdateView();tray.Visible=true;
            timer.Interval=1000;timer.Tick+=(s,e)=>
            {
                if(exitSignal.WaitOne(0)){Exit();return;}
                if(showSignal.WaitOne(0))OpenPanel();
                profileTicks++;
                if(profileTicks%preferences.Interval==0) RefreshBattery();
                else if(Visible && !showingSettings && profileTicks%2==0) RefreshSetup();
            };timer.Start();
            Shown+=(s,e)=>{PositionPanel();RefreshBattery();};
            FormClosing+=(s,e)=>{if(!exiting){e.Cancel=true;animation.To(0,Hide);}};
        }
        protected override void SetVisibleCore(bool value)
        {
            if(firstVisibility && value)
            {
                firstVisibility=false;
                if(hidden)
                {
                    if(!IsHandleCreated)CreateHandle();
                    BeginInvoke(new Action(()=>RefreshBattery()));
                    value=false;
                }
            }
            base.SetVisibleCore(value);
        }
        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            if(view!=null)PopupPlacement.Round(this,view.ScaleFactor,18);
        }
        protected override void OnVisibleChanged(EventArgs e)
        {
            base.OnVisibleChanged(e);
            if(!Visible && view!=null)view.ReleaseArtwork();
        }
        protected override void WndProc(ref Message message)
        {
            if(message.Msg==0x02E0)
            {
                if(!view.Placing)
                {
                    var bounds=((PopupPlacement.NativeRect)Marshal.PtrToStructure(message.LParam,typeof(PopupPlacement.NativeRect))).Rectangle;
                    displayScreen=Screen.FromRectangle(bounds);
                    PositionPanel((message.WParam.ToInt64()&0xffff)/96f);
                }
                message.Result=IntPtr.Zero;return;
            }
            if(message.Msg==showMessage)OpenPanel();
            if(message.Msg==stopMessage){Exit();return;}
            int kind=message.Msg;
            base.WndProc(ref message);
            if((kind==0x007E || kind==0x001A) && IsHandleCreated && !exiting)
                BeginInvoke(new Action(()=>{
                    if(exiting)return;
                    displayScreen=Screen.PrimaryScreen;PositionPanel();UpdateView();
                }));
        }
        [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern uint RegisterWindowMessage(string text);
        void Open(string target){try{Process.Start(new ProcessStartInfo(target){UseShellExecute=true});}catch(Exception error){MessageBox.Show(this,error.Message);}}
        void HandleCommand(string command)
        {
            if(command=="close"){animation.To(0,Hide);return;}
            if(command=="refresh"){RefreshBattery();return;}
            if(command=="settings"){ToggleSettings(!showingSettings);return;}
            if(command=="back"){ToggleSettings(false);return;}
            if(command=="hub"){Open("https://hub.rapoo.com/home");return;}
            if(command=="tray"){Open("ms-settings:taskbar");return;}
            if(command=="diagnostics"){new Diagnostics().Show(this);return;}
            if(command=="startup")
            {
                try{Startup.Set(!Startup.Enabled());}
                catch(Exception error){MessageBox.Show(this,error.Message,"Startup");}
                view.StartupEnabled=Startup.Enabled();view.Invalidate();return;
            }
            if(command.StartsWith("interval:"))
            {
                int value;
                if(int.TryParse(command.Substring(9),out value) && new[]{30,60,120,300,600}.Contains(value))
                {preferences.Interval=value;view.Interval=value;Save();view.Invalidate();}
            }
        }
        void ToggleSettings(bool show)
        {
            showingSettings=show;view.Mode=show?1:0;view.Interval=preferences.Interval;
            if(show)view.StartupEnabled=Startup.Enabled();
            PositionPanel();view.Invalidate();if(!show)RefreshSetup();
        }
        void OpenPanel()
        {
            if(menu!=null)menu.Close();
            displayScreen=Screen.FromPoint(Cursor.Position);
            ToggleSettings(false);
            bool fresh=!Visible;if(fresh)Opacity=0;
            Show();PositionPanel();Activate();animation.To(1);RefreshBattery();
        }
        void OpenMenu()
        {
            if(menu!=null)menu.Close();
            var surface=new PopupSurface{Mode=2,Readings=readings,BackColor=Artwork.Color("#131217")};
            var popup=new PopupMenu(surface,Cursor.Position);
            menu=popup;
            var fade=new Fade(popup);
            surface.Command=command=>{
                fade.To(0,()=>{
                    popup.Close();
                    if(command=="exit"){Exit();return;}
                    if(command=="refresh"){RefreshBattery();return;}
                    if(command=="devices" || command=="settings"){OpenPanel();if(command=="settings")ToggleSettings(true);}
                });
            };
            popup.KeyDown+=(s,e)=>{if(e.KeyCode==Keys.Escape)fade.To(0,popup.Close);};
            popup.Deactivate+=(s,e)=>{if(!popup.IsDisposed)fade.To(0,popup.Close);};
            popup.FormClosed+=(s,e)=>{if(menu==popup)menu=null;};
            popup.Show();popup.Activate();fade.To(1);
        }
        void PositionPanel(float? scale=null)
        {
            PopupPlacement.Place(this,view,showingSettings?new Size(365,262):new Size(556,412),displayScreen,null,scale);
        }
        void Save(){try{preferences.Save();}catch(Exception error){if(Environment.GetCommandLineArgs().Contains("--debug"))Trace.WriteLine(error);}}
        async void RefreshSetup()
        {
            if(loading || exiting) return;
            loading=true;
            var mouse=readings[0].Copy();
            try
            {
                await Task.Run(()=>{
                    var devices=Hardware.Enumerate();
                    var status=devices.FirstOrDefault(d=>d.Path.ToLowerInvariant().Contains("vid_24ae") && d.Path.ToLowerInvariant().Contains("col09"));
                    if(status!=null)Hardware.ReadSetup(devices,status,mouse,stop.Token);
                });
                if(!exiting){readings[0].DpiX=mouse.DpiX;readings[0].DpiY=mouse.DpiY;readings[0].Slot=mouse.Slot;readings[0].Rate=mouse.Rate;UpdateView();}
            }
            catch(Exception){}
            finally{loading=false;}
        }
        async void RefreshBattery()
        {
            if(loading || exiting) return;
            loading=true;
            var mouse=readings[0].Copy();mouse.Stale=true;
            var keyboard=readings[1].Copy();
            try
            {
                refreshTask=Task.Run(async ()=>{
                    var bluetooth=BluetoothBattery.Read(keyboard);
                    Hardware.Mouse(Hardware.Enumerate(),mouse,stop.Token);
                    try {await bluetooth;}
                    catch(Exception){keyboard.Level=-1;keyboard.Status="Connection unavailable";keyboard.Estimate="";}
                });
                await refreshTask;
                if(exiting)return;
                readings[0]=mouse;readings[1]=keyboard;
                preferences.Observe(mouse);preferences.Observe(keyboard);Save();UpdateView();
            }
            catch(Exception){if(!exiting){readings[1].Level=-1;readings[1].Status="Connection unavailable";readings[1].Estimate="";UpdateView();}}
            finally{loading=false;}
        }
        void UpdateView()
        {
            view.Readings=readings;view.Invalidate();
            if(menu!=null && !menu.IsDisposed)
            {
                var surface=menu.Controls.OfType<PopupSurface>().FirstOrDefault();
                if(surface!=null){surface.Readings=readings;surface.Invalidate();}
            }
            Icon next=DrawTray(readings);
            tray.Icon=next;if(ownedIcon!=null)ownedIcon.Dispose();ownedIcon=next;
            string text=String.Join("\n",readings.Select(b=>b.Name+": "+(b.Level<0?b.Status:b.Level+"% · "+(b.Stale?"Last known":b.Estimate))));
            tray.Text="Chargeview Native";TrayTooltip.Set(tray,text);
        }
        public static Color BatteryColor(Battery b)
        {return Artwork.Color(b.Charging?"#67c6ff":b.Level<0?"#a6b4c7":b.Level>=60?"#71e2ab":b.Level>=30?"#ffcf70":"#ff8590");}
        [DllImport("user32.dll")] static extern bool DestroyIcon(IntPtr icon);
        [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr FindWindow(string name,string caption);
        [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr window);
        [DllImport("user32.dll")] static extern int GetSystemMetricsForDpi(int index,uint dpi);
        static Icon DrawTray(Battery[] states)
        {
            int size=SystemInformation.SmallIconSize.Width;
            try
            {
                IntPtr taskbar=FindWindow("Shell_TrayWnd",null);
                uint dpi=taskbar==IntPtr.Zero?96:GetDpiForWindow(taskbar);
                int requested=GetSystemMetricsForDpi(49,dpi);
                if(requested>0)size=requested;
            }
            catch(EntryPointNotFoundException){}
            using(var bitmap=Artwork.Tray(states,Math.Max(16,size)))
            {
                IntPtr handle=bitmap.GetHicon();
                try{return (Icon)Icon.FromHandle(handle).Clone();}finally{DestroyIcon(handle);}
            }
        }
        void Exit(){if(exiting)return;exiting=true;if(menu!=null)menu.Close();stop.Cancel();timer.Stop();tray.Visible=false;tray.Dispose();if(ownedIcon!=null)ownedIcon.Dispose();Close();}
        protected override void Dispose(bool disposing)
        {
            if(disposing){timer.Dispose();exitSignal.Dispose();showSignal.Dispose();tray.Dispose();}
            base.Dispose(disposing);
        }
    }

    static class DeviceCard
    {
        internal static GraphicsPath Rounded(Rectangle r,int radius)
        {
            int d=radius*2;var p=new GraphicsPath();p.AddArc(r.X,r.Y,d,d,180,90);p.AddArc(r.Right-d,r.Y,d,d,270,90);p.AddArc(r.Right-d,r.Bottom-d,d,d,0,90);p.AddArc(r.X,r.Bottom-d,d,d,90,90);p.CloseFigure();return p;
        }
    }
}
