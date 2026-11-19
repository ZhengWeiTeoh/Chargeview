using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32.SafeHandles;

namespace ChargeviewNative
{
    sealed class HidDevice
    {
        public string Path, Name;
        public ushort Page, Usage, Input, Output, Feature;
        public override string ToString() { return String.Format("{0}  page {1:X4} / usage {2:X4}  in {3} out {4} feature {5}", Name, Page, Usage, Input, Output, Feature); }
    }

    static class Hardware
    {
        const uint Read = 0x80000000, Write = 0x40000000, Overlapped = 0x40000000;
        [StructLayout(LayoutKind.Sequential)] struct Interface { public int Size; public Guid Class; public int Flags; public UIntPtr Reserved; }
        [StructLayout(LayoutKind.Sequential)] struct Caps
        {
            public ushort Usage, Page, Input, Output, Feature;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst=17)] public ushort[] Reserved;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst=10)] public ushort[] Counts;
        }
        [StructLayout(LayoutKind.Sequential)] struct NativeOverlapped { public UIntPtr Internal, InternalHigh; public uint Offset, OffsetHigh; public IntPtr Event; }
        [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr SetupDiGetClassDevs(ref Guid g, string e, IntPtr parent, uint flags);
        [DllImport("setupapi.dll", SetLastError=true)] static extern bool SetupDiEnumDeviceInterfaces(IntPtr set, IntPtr data, ref Guid g, uint index, ref Interface entry);
        [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool SetupDiGetDeviceInterfaceDetail(IntPtr set, ref Interface entry, IntPtr detail, uint size, out uint needed, IntPtr info);
        [DllImport("setupapi.dll")] static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern SafeFileHandle CreateFile(string path, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
        [DllImport("hid.dll")] static extern bool HidD_GetPreparsedData(SafeFileHandle h, out IntPtr data);
        [DllImport("hid.dll")] static extern bool HidD_FreePreparsedData(IntPtr data);
        [DllImport("hid.dll")] static extern int HidP_GetCaps(IntPtr data, out Caps caps);
        [DllImport("hid.dll", CharSet=CharSet.Unicode)] static extern bool HidD_GetProductString(SafeFileHandle h, IntPtr text, uint length);
        [DllImport("hid.dll")] static extern bool HidD_GetFeature(SafeFileHandle h, byte[] data, int length);
        [DllImport("hid.dll")] static extern bool HidD_SetOutputReport(SafeFileHandle h, byte[] data, int length);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool ReadFile(SafeFileHandle h, IntPtr data, uint size, out uint read, IntPtr request);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetOverlappedResult(SafeFileHandle h, IntPtr request, out uint count, bool wait);
        [DllImport("kernel32.dll")] static extern bool CancelIoEx(SafeFileHandle h, IntPtr request);
        [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr h, uint milliseconds);
        static readonly Guid Hid = new Guid("4d1e55b2-f16f-11cf-88cb-001111000030");

        public static List<HidDevice> Enumerate()
        {
            var result = new List<HidDevice>(); Guid guid = Hid;
            IntPtr set = SetupDiGetClassDevs(ref guid, null, IntPtr.Zero, 0x12);
            if (set == new IntPtr(-1)) return result;
            try
            {
                for (uint i=0; ; i++)
                {
                    var entry = new Interface {Size=Marshal.SizeOf(typeof(Interface))};
                    if (!SetupDiEnumDeviceInterfaces(set, IntPtr.Zero, ref guid, i, ref entry)) break;
                    uint needed; SetupDiGetDeviceInterfaceDetail(set, ref entry, IntPtr.Zero, 0, out needed, IntPtr.Zero);
                    if (needed == 0) continue;
                    IntPtr detail=Marshal.AllocHGlobal((int)needed);
                    try
                    {
                        Marshal.WriteInt32(detail, IntPtr.Size==8 ? 8 : 6);
                        if (!SetupDiGetDeviceInterfaceDetail(set, ref entry, detail, needed, out needed, IntPtr.Zero)) continue;
                        string path=Marshal.PtrToStringUni(IntPtr.Add(detail,4));
                        var device=new HidDevice {Path=path, Name=""};
                        using (var handle=Open(path,0,false))
                        {
                            if (!handle.IsInvalid)
                            {
                                IntPtr text=Marshal.AllocHGlobal(512);
                                try { if (HidD_GetProductString(handle,text,512)) device.Name=Marshal.PtrToStringUni(text); }
                                finally { Marshal.FreeHGlobal(text); }
                                IntPtr preparsed;
                                if (HidD_GetPreparsedData(handle,out preparsed))
                                {
                                    try
                                    {
                                        Caps caps;
                                        if (HidP_GetCaps(preparsed,out caps)>=0)
                                        {
                                            device.Page=caps.Page; device.Usage=caps.Usage;
                                            device.Input=caps.Input; device.Output=caps.Output; device.Feature=caps.Feature;
                                        }
                                    }
                                    finally { HidD_FreePreparsedData(preparsed); }
                                }
                            }
                        }
                        result.Add(device);
                    }
                    finally { Marshal.FreeHGlobal(detail); }
                }
            }
            finally { SetupDiDestroyDeviceInfoList(set); }
            return result;
        }

        static SafeFileHandle Open(string path, uint access, bool async)
        { return CreateFile(path,access,3,IntPtr.Zero,3,async ? Overlapped : 0,IntPtr.Zero); }

        static byte[] Receive(SafeFileHandle handle, int length, int timeout, CancellationToken stop)
        {
            using (var completed=new EventWaitHandle(false,EventResetMode.ManualReset))
            {
                IntPtr buffer=Marshal.AllocHGlobal(length), request=Marshal.AllocHGlobal(Marshal.SizeOf(typeof(NativeOverlapped)));
                try
                {
                    Marshal.StructureToPtr(new NativeOverlapped {Event=completed.SafeWaitHandle.DangerousGetHandle()},request,false);
                    uint count;
                    bool ready=ReadFile(handle,buffer,(uint)length,out count,request);
                    if (!ready && Marshal.GetLastWin32Error()!=997) return null;
                    if (!ready)
                    {
                        int signaled=WaitHandle.WaitAny(new WaitHandle[]{completed,stop.WaitHandle},timeout);
                        if (signaled!=0)
                        {
                            CancelIoEx(handle,request);
                            GetOverlappedResult(handle,request,out count,true);
                            return null;
                        }
                        if (!GetOverlappedResult(handle,request,out count,false)) return null;
                    }
                    byte[] bytes=new byte[count]; Marshal.Copy(buffer,bytes,0,(int)count); return bytes;
                }
                finally { Marshal.FreeHGlobal(request); Marshal.FreeHGlobal(buffer); }
            }
        }

        public static void Mouse(List<HidDevice> devices, Battery state, CancellationToken stop)
        {
            var status=devices.FirstOrDefault(d=> (d.Path.ToLowerInvariant().Contains("vid_24ae&pid_1462") || d.Path.ToLowerInvariant().Contains("vid_24ae&pid_4662")) && d.Path.ToLowerInvariant().Contains("mi_01&col09"));
            if (status==null) { state.Status="Disconnected"; state.Level=-1; return; }
            using (var handle=Open(status.Path,Read,true))
            {
                if (!handle.IsInvalid)
                {
                    DateTime deadline=DateTime.UtcNow.AddSeconds(8);
                    while (!stop.IsCancellationRequested && DateTime.UtcNow<deadline)
                    {
                        byte[] b=Receive(handle,Math.Max(19,(int)status.Input),500,stop);
                        if (b==null || b.Length<9 || b[0]!=7 || (b[1]>>4<1 || b[1]>>4>2) || b[2]>=6) continue;
                        int x=b[3]|b[4]<<8,y=b[5]|b[6]<<8;
                        if (x<50 || y<50 || b[8]>100) continue;
                        state.Level=b[8]; state.Charging=(b[7]&2)!=0 || (b.Length>9 && (b[9]==1 || b[9]==2));
                        state.DpiX=x; state.DpiY=y; state.Slot=b[2]+1;
                        state.Status=state.Charging ? "Charging" : "Connected"; state.Stale=false;state.LastUpdate=DateTime.UtcNow;break;
                    }
                }
            }
            if (state.Stale) state.Status="No fresh report";
            ReadSetup(devices,status,state,stop);
        }

        static byte[] Register(SafeFileHandle output, SafeFileHandle feature, int address, int length, int bank, CancellationToken stop)
        {
            for (int attempt=0; attempt<3 && !stop.IsCancellationRequested; attempt++)
            {
                byte[] command=new byte[33]; command[0]=6; command[1]=0xa5; command[2]=0xa4;
                command[3]=(byte)length; command[4]=(byte)address; command[5]=(byte)bank;
                if (!HidD_SetOutputReport(output,command,command.Length)) return null;
                for (int i=0; i<5; i++)
                {
                    if (stop.WaitHandle.WaitOne(15)) return null;
                    byte[] response=new byte[33]; response[0]=8;
                    if (!HidD_GetFeature(feature,response,response.Length)) continue;
                    int offset=response[0]==1 ? 4 : response[0]==8 && response[1]==1 ? 5 : 0;
                    if (offset!=0) return response.Skip(offset).Take(length).ToArray();
                }
            }
            return null;
        }

        public static void ReadSetup(List<HidDevice> devices, HidDevice status, Battery state, CancellationToken stop)
        {
            string[] parts=status.Path.Split('#');
            string group=parts[2].Substring(0,parts[2].LastIndexOf('&'));
            Func<string,HidDevice> find=col=>devices.FirstOrDefault(d=>d.Path.ToLowerInvariant().Contains("mi_01&col"+col+"#") && d.Path.ToLowerInvariant().Contains(group.ToLowerInvariant()));
            var o=find("05"); var f=find("06");
            if (o==null || f==null || o.Output!=33 || f.Feature!=33) return;
            using (var output=Open(o.Path,Write,false))
            using (var feature=Open(f.Path,0,false))
            {
                if (output.IsInvalid || feature.IsInvalid) return;
                for (int attempt=0;attempt<2;attempt++)
                {
                    byte[] profile=Register(output,feature,12,1,1,stop);
                    if (profile==null || profile[0]>7) return;
                    int bank=8+profile[0]*4;
                    byte[] slot=Register(output,feature,150,3,bank,stop);
                    if (slot==null || slot[0]>6 || slot[2]>=Math.Min(6,slot[0]+1)) return;
                    int count=Math.Min(6,slot[0]+1);
                    byte[] x=Register(output,feature,136,count*2,bank,stop),y=Register(output,feature,200,count*2,bank,stop);
                    byte[] rate=Register(output,feature,128,1,bank,stop),again=Register(output,feature,12,1,1,stop);
                    if (x==null || y==null || rate==null || again==null) return;
                    if (again[0]!=profile[0]) continue;
                    int index=slot[2]*2,dx=x[index]|x[index+1]<<8,dy=y[index]|y[index+1]<<8;
                    if (dx<50 || dx>26000 || dy<50 || dy>26000) return;
                    state.DpiX=dx;state.DpiY=dy;state.Slot=slot[2]+1;
                    var rates=new Dictionary<byte,int>{{8,125},{4,250},{2,500},{1,1000},{132,2000},{130,4000},{129,8000}};
                    state.Rate=rates.ContainsKey(rate[0]) ? rates[rate[0]] : 0; return;
                }
            }
        }

        public static byte[] Feature(HidDevice device, byte report)
        {
            if (device.Feature==0) return null;
            using (var handle=Open(device.Path,0,false))
            {
                if (handle.IsInvalid) return null;
                byte[] data=new byte[device.Feature];data[0]=report;
                return HidD_GetFeature(handle,data,data.Length) ? data : null;
            }
        }
    }
}

