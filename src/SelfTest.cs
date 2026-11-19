using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace ChargeviewNative
{
    static class SelfTest
    {
        public static int Run()
        {
            try
            {
                var data=Hardware.Enumerate();
                var mouse=new Battery("Rapoo VT3 V2","Rapoo HID telemetry");
                Hardware.Mouse(data,mouse,CancellationToken.None);
                var keyboard=new Battery("WOBKEY Crush80","Windows Bluetooth LE");
                BluetoothBattery.Read(keyboard).GetAwaiter().GetResult();
                string result="HID interfaces: "+data.Count+"\r\nMouse: "+mouse.Level+"% "+mouse.Status+"\r\nDPI: "+mouse.DpiX+" x "+mouse.DpiY+"; rate: "+mouse.Rate+" Hz\r\nKeyboard: "+keyboard.Level+"% "+keyboard.Status;
                File.WriteAllText(Path.Combine(Path.GetTempPath(),"ChargeviewNative-self-test.txt"),result);
                return 0;
            }
            catch(Exception e){File.WriteAllText(Path.Combine(Path.GetTempPath(),"ChargeviewNative-self-test.txt"),e.ToString());return 1;}
        }
    }
}
