using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Windows.Devices.Bluetooth;
using Windows.Devices.Enumeration;

namespace ChargeviewNative
{
    static class BluetoothBattery
    {
        [StructLayout(LayoutKind.Sequential)] struct Key { public Guid Format; public uint Id; public Key(string guid,uint id){Format=new Guid(guid);Id=id;} }
        [DllImport("cfgmgr32.dll", CharSet=CharSet.Unicode)] static extern uint CM_Get_Device_ID_List_Size(out uint size,string filter,uint flags);
        [DllImport("cfgmgr32.dll", CharSet=CharSet.Unicode)] static extern uint CM_Get_Device_ID_List(string filter,[Out] char[] buffer,uint size,uint flags);
        [DllImport("cfgmgr32.dll", CharSet=CharSet.Unicode)] static extern uint CM_Locate_DevNode(out uint node,string id,uint flags);
        [DllImport("cfgmgr32.dll")] static extern uint CM_Get_Parent(out uint parent,uint node,uint flags);
        [DllImport("cfgmgr32.dll", CharSet=CharSet.Unicode)] static extern uint CM_Get_DevNode_Property(uint node,ref Key key,out uint type,byte[] buffer,ref uint size,uint flags);

        public static async Task Read(Battery state)
        {
            var properties=new string[]{"System.Devices.Aep.IsConnected","System.Devices.Aep.DeviceAddress"};
            var operation=DeviceInformation.FindAllAsync(BluetoothLEDevice.GetDeviceSelectorFromPairingState(true),properties,DeviceInformationKind.AssociationEndpoint);
            var completion=new TaskCompletionSource<DeviceInformationCollection>();
            operation.Completed=(result,status)=>{
                try {completion.TrySetResult(result.GetResults());}
                catch(Exception error){completion.TrySetException(error);}
            };
            DeviceInformationCollection devices;
            try
            {
                if(await Task.WhenAny(completion.Task,Task.Delay(5000))!=completion.Task)
                {
                    operation.Cancel();
                    throw new TimeoutException("Bluetooth status query timed out.");
                }
                devices=await completion.Task;
            }
            finally {operation.Close();}
            var connected=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var device in devices)
            {
                object online,address;
                if (device.Properties.TryGetValue("System.Devices.Aep.IsConnected",out online) && online is bool && (bool)online &&
                    device.Properties.TryGetValue("System.Devices.Aep.DeviceAddress",out address) && address is string)
                    connected.Add(((string)address).Replace(":",""));
            }
            state.Level=-1;state.Status="Disconnected";state.Stale=false;
            char[] buffer=null;
            for (int attempt=0;attempt<2;attempt++)
            {
                uint size;
                if (CM_Get_Device_ID_List_Size(out size,"BTHLEDEVICE",0x101)!=0) return;
                buffer=new char[size];
                uint result=CM_Get_Device_ID_List("BTHLEDEVICE",buffer,size,0x101);
                if (result==0) break;
                buffer=null;
                if (result!=26) return;
            }
            if (buffer==null) return;
            foreach (string id in new string(buffer).Split('\0'))
            {
                string value=id.ToUpperInvariant();
                if (!value.Contains("{0000180F-0000-1000-8000-00805F9B34FB}") || !value.Contains("VID&02245A_PID&8276")) continue;
                string[] parts=id.Split('\\');
                if (parts.Length<2) continue;
                string address=parts[1].Substring(parts[1].LastIndexOf('_')+1);
                if (!connected.Contains(address)) continue;
                state.Status="Battery unavailable";
                uint service,node;
                if (CM_Locate_DevNode(out service,id,0)!=0 || CM_Get_Parent(out node,service,0)!=0) continue;
                var key=new Key("104ea319-6ee2-4701-bd47-8ddbf425bbe5",2);
                uint type,length=1;byte[] data=new byte[1];
                if (CM_Get_DevNode_Property(node,ref key,out type,data,ref length,0)==0 && type==3 && data[0]<=100)
                {state.Level=data[0];state.Status="Connected";state.LastUpdate=DateTime.UtcNow;}
                return;
            }
        }
    }
}


