using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Windows.Forms;
using Microsoft.Win32;

namespace ChargeviewNative
{
    static class Startup
    {
        const string Name="Chargeview Native.lnk";
        const string Approval=@"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder";
        static string Link {get{return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Startup),Name);}}
        public static bool Enabled()
        {
            if (!File.Exists(Link)) return false;
            using (var key=Registry.CurrentUser.OpenSubKey(Approval))
            {
                byte[] data=key==null ? null : key.GetValue(Name) as byte[];
                return data==null || data.Length==0 || (data[0]&1)==0;
            }
        }
        public static void Set(bool enabled)
        {
            if (enabled)
            {
                dynamic shell=Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
                dynamic link=null;
                try
                {
                    link=shell.CreateShortcut(Link);
                    link.TargetPath=Application.ExecutablePath;link.Arguments="--startup";
                    link.WorkingDirectory=AppDomain.CurrentDomain.BaseDirectory;link.Description="Chargeview Native";
                    link.IconLocation=Application.ExecutablePath+",0";link.Save();
                }
                finally
                {
                    if (link!=null) Marshal.FinalReleaseComObject(link);
                    Marshal.FinalReleaseComObject(shell);
                }
            }
            byte[] state=new byte[12]; state[0]=(byte)(enabled ? 2 : 3);
            using (var key=Registry.CurrentUser.CreateSubKey(Approval)) key.SetValue(Name,state,RegistryValueKind.Binary);
            if (enabled) InstallTask();
        }
        static void InstallTask()
        {
            dynamic scheduler=Activator.CreateInstance(Type.GetTypeFromProgID("Schedule.Service"));
            dynamic folder=null,task=null;
            try
            {
                scheduler.Connect();folder=scheduler.GetFolder(@"\");task=scheduler.NewTask(0);
                string sid=WindowsIdentity.GetCurrent().User.Value;
                task.RegistrationInfo.Description="Starts Chargeview Native at sign-in when its Startup entry is enabled.";
                task.Principal.UserId=sid;task.Principal.LogonType=3;
                task.Settings.DisallowStartIfOnBatteries=false;task.Settings.StopIfGoingOnBatteries=false;
                task.Settings.ExecutionTimeLimit="PT0S";
                task.Triggers.Create(9).UserId=sid;
                dynamic action=task.Actions.Create(0);
                action.Path=Application.ExecutablePath;action.Arguments="--startup";
                action.WorkingDirectory=AppDomain.CurrentDomain.BaseDirectory;
                folder.RegisterTaskDefinition("ChargeviewNative-"+sid,task,6,sid,null,3,null);
            }
            finally
            {
                if (task!=null) Marshal.FinalReleaseComObject(task);
                if (folder!=null) Marshal.FinalReleaseComObject(folder);
                Marshal.FinalReleaseComObject(scheduler);
            }
        }
    }
}
