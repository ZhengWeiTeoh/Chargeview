using System;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace ChargeviewNative
{
    static class TrayTooltip
    {
        [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Data
        {
            public int Size; public IntPtr Window; public uint Id,Flags,Message; public IntPtr Icon;
            [MarshalAs(UnmanagedType.ByValTStr,SizeConst=128)]public string Tip;
            public uint State,StateMask;
            [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)]public string Info;
            public uint Timeout;
            [MarshalAs(UnmanagedType.ByValTStr,SizeConst=64)]public string Title;
            public uint InfoFlags;public Guid Guid; public IntPtr Balloon;
        }
        [DllImport("shell32.dll",CharSet=CharSet.Unicode)]static extern bool Shell_NotifyIcon(uint action,ref Data data);
        public static void Set(NotifyIcon icon,string text)
        {
            var fields=BindingFlags.NonPublic|BindingFlags.Instance;
            var windowField=typeof(NotifyIcon).GetField("window",fields);
            var idField=typeof(NotifyIcon).GetField("id",fields);
            if(windowField==null || idField==null) return;
            var window=windowField.GetValue(icon) as NativeWindow;
            if(window==null)return;
            var data=new Data{Size=Marshal.SizeOf(typeof(Data)),Window=window.Handle,Id=Convert.ToUInt32(idField.GetValue(icon)),Flags=4,Tip=text.Length>127?text.Substring(0,127):text};
            Shell_NotifyIcon(1,ref data);
        }
    }
}
