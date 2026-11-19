using System;
using System.Drawing;
using System.Linq;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace ChargeviewNative
{
    sealed class Diagnostics : Form
    {
        readonly ListBox devices=new ListBox{Dock=DockStyle.Fill};
        readonly TextBox output=new TextBox{Multiline=true,ScrollBars=ScrollBars.Both,Dock=DockStyle.Bottom,Height=200,ReadOnly=true,Font=new Font("Consolas",9)};
        readonly NumericUpDown report=new NumericUpDown{Maximum=255,Width=70};
        readonly Button scan=new Button{Text="Rescan",AutoSize=true};
        readonly Button read=new Button{Text="Read Feature",AutoSize=true};
        public Diagnostics()
        {
            Text="Chargeview Native · HID diagnostics";Size=new Size(850,560);
            var actions=new FlowLayoutPanel{Dock=DockStyle.Top,Height=40};
            actions.Controls.Add(scan);actions.Controls.Add(new Label{Text="Report ID",AutoSize=true,Padding=new Padding(0,7,0,0)});actions.Controls.Add(report);actions.Controls.Add(read);
            Controls.Add(devices);Controls.Add(output);Controls.Add(actions);
            devices.SelectedIndexChanged+=(s,e)=>{var d=devices.SelectedItem as HidDevice;if(d!=null)output.Text=d.Path;};
            scan.Click+=async(s,e)=>await Scan();
            read.Click+=async(s,e)=>
            {
                var selected=devices.SelectedItem as HidDevice;if(selected==null)return;
                byte id=(byte)report.Value;read.Enabled=false;
                try
                {
                    byte[] data=await Task.Run(()=>Hardware.Feature(selected,id));
                    if(!IsDisposed)output.Text=selected.Path+Environment.NewLine+(data==null?"No Feature response":BitConverter.ToString(data));
                }
                catch(Exception error){if(!IsDisposed)output.Text=error.Message;}
                finally{if(!IsDisposed)read.Enabled=true;}
            };
            Shown+=async(s,e)=>await Scan();
        }
        async Task Scan()
        {
            scan.Enabled=false;
            try
            {
                var items=await Task.Run(()=>Hardware.Enumerate());
                if(IsDisposed)return;
                devices.Items.Clear();devices.Items.AddRange(items.Cast<object>().ToArray());
                output.Text=items.Count+" HID interfaces";
            }
            catch(Exception error){if(!IsDisposed)output.Text=error.Message;}
            finally{if(!IsDisposed)scan.Enabled=true;}
        }
    }
}
