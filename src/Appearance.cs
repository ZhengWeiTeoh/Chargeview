using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace ChargeviewNative
{
    static class Artwork
    {
        static readonly double[,] Bolt={{.76,.07},{.94,.07},{.76,.42},{.93,.42},{.45,.94},{.56,.59},{.39,.59}};
        public static Color Color(string hex){return ColorTranslator.FromHtml(hex);}
        static double Distance(double x,double y,double ax,double ay,double bx,double by)
        {
            double dx=bx-ax,dy=by-ay,t=Math.Max(0,Math.Min(1,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy)));
            return Math.Sqrt(Math.Pow(x-ax-dx*t,2)+Math.Pow(y-ay-dy*t,2));
        }
        public static Bitmap Action(int size,string kind,Color background)
        {
            var bitmap=new Bitmap(size,size,PixelFormat.Format32bppArgb);
            Color ink=Color("#f0edf8");
            for(int y=0;y<size;y++)for(int x=0;x<size;x++)
            {
                int count=0;
                for(int dy=0;dy<4;dy++)for(int dx=0;dx<4;dx++)
                {
                    double sx=(x+(dx+.5)/4)/size,sy=(y+(dy+.5)/4)/size;
                    double angle=Math.Atan2(sy-.5,sx-.5),radius=Math.Sqrt((sx-.5)*(sx-.5)+(sy-.5)*(sy-.5));
                    bool inside;
                    if(kind=="close")inside=Math.Min(Distance(sx,sy,.25,.25,.75,.75),Distance(sx,sy,.75,.25,.25,.75))<.054;
                    else if(kind=="settings")inside=radius>=.14 && radius<=(Math.Cos(8*angle)>.30?.35:.26);
                    else inside=(Math.Abs(radius-.285)<.052 && !(angle>-Math.PI && angle< -2.28)) ||
                        Math.Min(Distance(sx,sy,.23,.48,.14,.34),Distance(sx,sy,.23,.48,.35,.38))<.052;
                    if(inside)count++;
                }
                bitmap.SetPixel(x,y,Blend(background,ink,count/16.0));
            }
            return bitmap;
        }
        static Color Blend(Color a,Color b,double f)
        {return System.Drawing.Color.FromArgb((int)Math.Round(a.R+(b.R-a.R)*f),(int)Math.Round(a.G+(b.G-a.G)*f),(int)Math.Round(a.B+(b.B-a.B)*f));}
        static void Span(byte[] row,int width,double left,double right,Color color)
        {
            if(right<=left)return;
            int start=(int)left,end=Math.Min(width-1,(int)right);
            for(int x=Math.Max(0,start);x<=end;x++)
            {
                double coverage=Math.Min(right,x+1)-Math.Max(left,x);
                if(coverage<=0)continue;
                int n=x*4;
                row[n]=(byte)Math.Round(row[n]+(color.B-row[n])*coverage);
                row[n+1]=(byte)Math.Round(row[n+1]+(color.G-row[n+1])*coverage);
                row[n+2]=(byte)Math.Round(row[n+2]+(color.R-row[n+2])*coverage);
                row[n+3]=255;
            }
        }
        static double Edge(double y,int height,double radius,int inset)
        {double r=Math.Max(0,radius-inset),dy=Math.Max(Math.Max(radius-y,y-height+radius),0);return inset+r-Math.Sqrt(Math.Max(0,r*r-dy*dy));}
        public static Bitmap Card(int width,int height,int radius,int level,Color hue)
        {
            Color backdrop=Color("#171429"),rim=Color("#333044"),ink=Color("#17161e"),dim=Color("#32313c");
            var bitmap=new Bitmap(width,height,PixelFormat.Format32bppArgb);
            var data=bitmap.LockBits(new Rectangle(0,0,width,height),ImageLockMode.WriteOnly,PixelFormat.Format32bppArgb);
            byte[] row=new byte[width*4];
            var intersections=new List<double>(7);
            try
            {
            for(int y=0;y<height;y++)
            {
                double at=y+.5;
                for(int x=0;x<width;x++){row[x*4]=backdrop.B;row[x*4+1]=backdrop.G;row[x*4+2]=backdrop.R;row[x*4+3]=255;}
                double left=Edge(at,height,radius,0);Span(row,width,left,width-left,rim);
                if(y>=1 && y<height-1){left=Edge(at,height,radius,1);Span(row,width,left,width-left,ink);}
                intersections.Clear();
                for(int i=0;i<7;i++)
                {
                    int previous=(i+6)%7;
                    double x1=Bolt[previous,0]*width,y1=Bolt[previous,1]*height,x2=Bolt[i,0]*width,y2=Bolt[i,1]*height;
                    if(Math.Min(y1,y2)<=at && at<Math.Max(y1,y2))intersections.Add(x1+(x2-x1)*(at-y1)/(y2-y1));
                }
                intersections.Sort();
                double surface=height*(.94-.87*Math.Max(0,level)/100);
                Color color=dim;
                if(level>0 && at>=surface)color=Blend(ink,hue,.96-.36*Math.Min(1,(at-surface)/Math.Max(1,height*.94-surface)));
                for(int i=0;i+1<intersections.Count;i+=2)Span(row,width,intersections[i],intersections[i+1],color);
                Marshal.Copy(row,0,IntPtr.Add(data.Scan0,y*data.Stride),row.Length);
            }
            }
            finally{bitmap.UnlockBits(data);}
            return bitmap;
        }
        public static bool Rounded(double x,double y,double left,double top,double right,double bottom,double radius)
        {
            if(x<left || x>=right || y<top || y>=bottom)return false;
            double dx=Math.Max(Math.Max(left+radius-x,x-right+radius),0),dy=Math.Max(Math.Max(top+radius-y,y-bottom+radius),0);
            return dx*dx+dy*dy<=radius*radius;
        }
        public static Bitmap Tray(Battery[] batteries,int size)
        {
            var bitmap=new Bitmap(size,size,PixelFormat.Format32bppArgb);
            for(int index=0;index<2;index++)
            {
                int tile=index==0?(int)Math.Round(size*.69):size,left=index==0?(int)Math.Round(size*.36):0,top=index==0?-(int)Math.Round(size*.03):(int)Math.Round(size*.22);
                Battery battery=batteries[index];Color fill=MainWindow.BatteryColor(battery);
                bool mouse=index==0;
                double l=mouse?.22:.035,t=mouse?.055:.245,r=mouse?.78:.965,b=mouse?.945:.755,inset=mouse?.064:.060,corner=mouse?.26:.105;
                double il=l+inset,it=t+inset,ir=r-inset,ib=b-inset,depth=ib-it,surface=ib-depth*Math.Max(0,battery.Level)/100;
                double wave=Math.Min(.035,Math.Min(surface-it,ib-surface));
                for(int y=Math.Max(0,-top);y<Math.Min(tile,size-top);y++)for(int x=Math.Max(0,-left);x<Math.Min(tile,size-left);x++)
                {
                    int red=0,green=0,blue=0,count=0;
                    for(int dy=0;dy<4;dy++)for(int dx=0;dx<4;dx++)
                    {
                        double sx=(x+(dx+.5)/4)/tile,sy=(y+(dy+.5)/4)/tile;
                        if(!Rounded(sx,sy,l,t,r,b,corner))continue;
                        Color color;
                        if(!Rounded(sx,sy,il,it,ir,ib,corner-inset))color=System.Drawing.Color.FromArgb(213,220,231);
                        else
                        {
                            bool detail=mouse?Rounded(sx,sy,.465,.23,.535,.40,.032):false;
                            if(!mouse)
                            {
                                foreach(double ky in new[]{.365,.48})foreach(double kx in new[]{.16,.35,.55,.74})
                                    detail=detail||Rounded(sx,sy,kx,ky,kx+.098,ky+.068,.022);
                                detail=detail||Rounded(sx,sy,.31,.60,.69,.665,.026);
                            }
                            double water=surface+wave*Math.Sin(2*Math.PI*(x*4+dx+.5)/(tile*4));
                            if(detail)color=System.Drawing.Color.FromArgb(228,235,246);
                            else if(battery.Level<0 && sx>=.39 && sx<.61 && sy>=.47 && sy<.53)color=fill;
                            else if(battery.Level>=0 && sy>=Math.Min(water,ib-.04))
                                color=sy-water<.055?Blend(fill,System.Drawing.Color.White,.22):Blend(System.Drawing.Color.Black,fill,1-.16*(sy-it)/depth);
                            else color=System.Drawing.Color.FromArgb(27,34,47);
                        }
                        count++;red+=color.R;green+=color.G;blue+=color.B;
                    }
                    if(count>0)bitmap.SetPixel(x+left,y+top,System.Drawing.Color.FromArgb((int)Math.Round(count*255/16.0),(int)Math.Round(red/(double)count),(int)Math.Round(green/(double)count),(int)Math.Round(blue/(double)count)));
                }
            }
            return bitmap;
        }
    }

    sealed class PopupSurface : Control
    {
        public Battery[] Readings;
        public int Mode,Interval=60;
        public bool StartupEnabled;
        public Action<string> Command;
        readonly List<KeyValuePair<RectangleF,string>> hits=new List<KeyValuePair<RectangleF,string>>();
        readonly Dictionary<string,Font> fonts=new Dictionary<string,Font>();
        readonly Dictionary<string,Bitmap> icons=new Dictionary<string,Bitmap>();
        readonly ToolTip tooltip=new ToolTip{InitialDelay=150,ReshowDelay=100,BackColor=System.Drawing.Color.FromArgb(41,36,55),ForeColor=System.Drawing.Color.White};
        readonly Bitmap[] cards=new Bitmap[2];
        readonly string[] cardKeys=new string[2];
        string hovered;
        public PopupSurface(){DoubleBuffered=true;BackColor=Artwork.Color("#171429");}
        Font FontAt(float points,bool bold,float scale)
        {
            string key=points+":"+bold+":"+scale;
            Font font;
            if(!fonts.TryGetValue(key,out font)){font=new Font("Segoe UI",points*96/72*scale,bold?FontStyle.Bold:FontStyle.Regular,GraphicsUnit.Pixel);fonts[key]=font;}
            return font;
        }
        void TextAt(Graphics g,string text,float size,string color,float x,float y,bool bold=false,float width=0)
        {
            float scale=g.DpiX/96f;
            var state=g.Save();
            try
            {
                // Let Windows rasterize text directly on the physical pixel grid.
                g.ResetTransform();
                Font font=FontAt(size,bold,scale);
                var flags=TextFormatFlags.NoPadding|TextFormatFlags.NoPrefix|TextFormatFlags.PreserveGraphicsClipping;
                var bounds=new Rectangle((int)Math.Round(x*scale),(int)Math.Round(y*scale),
                    width>0?(int)Math.Round(width*scale):2000,
                    (int)Math.Ceiling(width>0?42*scale:Math.Max(42*scale,font.GetHeight(g)+4)));
                flags|=width>0?TextFormatFlags.WordBreak:TextFormatFlags.SingleLine;
                TextRenderer.DrawText(g,text,font,bounds,Artwork.Color(color),flags);
            }
            finally{g.Restore(state);}
        }
        static void ImageAt(Graphics g,Bitmap bitmap,float x,float y)
        {
            float scale=g.DpiX/96f;
            var state=g.Save();
            try
            {
                // Source and destination sizes match, avoiding fractional DPI resampling.
                g.ResetTransform();
                g.InterpolationMode=InterpolationMode.NearestNeighbor;
                g.PixelOffsetMode=PixelOffsetMode.Half;
                var target=new Rectangle((int)Math.Round(x*scale),(int)Math.Round(y*scale),bitmap.Width,bitmap.Height);
                g.DrawImage(bitmap,target,0,0,bitmap.Width,bitmap.Height,GraphicsUnit.Pixel);
            }
            finally{g.Restore(state);}
        }
        void Hit(RectangleF bounds,string command){hits.Add(new KeyValuePair<RectangleF,string>(bounds,command));}
        void Icon(Graphics g,float x,float y,string kind)
        {
            RectangleF box=new RectangleF(x,y,23,23);Hit(box,kind);
            Color bg=hovered==kind?Artwork.Color("#443a60"):Mode==2?Artwork.Color("#302650"):BackColor;
            using(var path=DeviceCard.Rounded(Rectangle.Round(box),8))
            using(var brush=new SolidBrush(bg))g.FillPath(brush,path);
            int size=Math.Max(1,(int)Math.Round(21*g.DpiX/96));
            string key=kind+":"+bg.ToArgb()+":"+size;
            Bitmap image;
            if(!icons.TryGetValue(key,out image)){image=Artwork.Action(size,kind,bg);icons[key]=image;}
            ImageAt(g,image,x+1,y+1);
        }
        void ButtonAt(Graphics g,string text,RectangleF bounds,string command)
        {
            Hit(bounds,command);
            using(var path=DeviceCard.Rounded(Rectangle.Round(bounds),7))
            using(var brush=new SolidBrush(Artwork.Color(hovered==command?"#49303c":"#2c2a34")))g.FillPath(brush,path);
            float scale=g.DpiX/96f;
            var state=g.Save();
            try
            {
                g.ResetTransform();
                var pixels=Rectangle.FromLTRB((int)Math.Round(bounds.Left*scale),(int)Math.Round(bounds.Top*scale),
                    (int)Math.Round(bounds.Right*scale),(int)Math.Round(bounds.Bottom*scale));
                TextRenderer.DrawText(g,text,FontAt(9,true,scale),pixels,Artwork.Color("#f3f7ff"),
                    TextFormatFlags.HorizontalCenter|TextFormatFlags.VerticalCenter|TextFormatFlags.SingleLine|TextFormatFlags.NoPadding|TextFormatFlags.NoPrefix);
            }
            finally{g.Restore(state);}
        }
        protected override void OnPaint(PaintEventArgs e)
        {
            hits.Clear();
            Graphics g=e.Graphics;g.SmoothingMode=SmoothingMode.AntiAlias;
            g.TextRenderingHint=System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
            float scale=g.DpiX/96f;g.ScaleTransform(scale,scale);
            float width=Width/scale,height=Height/scale;
            using(var border=new Pen(Artwork.Color(Mode==2?"#534a6a":"#302849")))
            using(var shape=DeviceCard.Rounded(new Rectangle(0,0,(int)width-1,(int)height-1),Mode==2?14:18))g.DrawPath(border,shape);
            if(Mode==2){DrawMenu(g,width);return;}
            TextAt(g,Mode==1?"SETTINGS":"CHARGEVIEW",17,"#f3f7ff",19,17,true);
            Icon(g,width-40,19,"close");Icon(g,width-67,19,"refresh");Icon(g,width-94,19,"settings");
            if(Mode==1){DrawSettings(g,width);return;}
            for(int i=0;i<2;i++)
            {
                Battery reading=Readings[i];float x=17+i*267,y=60;
                int w=(int)Math.Round(255*scale),h=(int)Math.Round(224*scale);
                Color color=MainWindow.BatteryColor(reading);
                string key=w+":"+h+":"+reading.Level+":"+color.ToArgb();
                if(cards[i]==null || cardKeys[i]!=key)
                {
                    if(cards[i]!=null)cards[i].Dispose();
                    cards[i]=Artwork.Card(w,h,(int)Math.Round(21*scale),reading.Level,color);
                    cardKeys[i]=key;
                }
                ImageAt(g,cards[i],x,y);
                TextAt(g,i==0?"MOUSE":"KEYBOARD",8,"#a9a2bf",x+17,y+17,true);
                TextAt(g,reading.Name,12,"#f3f7ff",x+17,y+34,true);
                string hex=ColorTranslator.ToHtml(color);
                TextAt(g,reading.Level<0?"—":reading.Level+"%",33,hex,x+17,y+57,true);
                TextAt(g,reading.Level<0 || String.IsNullOrEmpty(reading.Estimate)?reading.Status:reading.Estimate,10,"#f3f7ff",x+17,y+116,true,221);
                if(reading.Level>=0 && !String.IsNullOrEmpty(reading.Estimate))TextAt(g,reading.Status,9,"#b9b4c9",x+17,y+140,false,221);
                string source=reading.Source;
                if(reading.Stale && reading.LastUpdate.HasValue)source+="  ·  "+reading.LastUpdate.Value.ToLocalTime().ToString("MMM dd HH:mm");
                TextAt(g,source,8,"#c2bccd",x+17,y+188,false,221);
            }
            using(var shape=DeviceCard.Rounded(new Rectangle(17,293,522,106),10))
            using(var brush=new SolidBrush(Artwork.Color("#19191f")))
            using(var pen=new Pen(Artwork.Color("#35333d"))){g.FillPath(brush,shape);g.DrawPath(pen,shape);}
            var mouse=Readings[0];
            TextAt(g,"ONBOARD SETUP",8,"#ff566d",31,303,true);
            TextAt(g,mouse.DpiX>0?"Slot "+mouse.Slot+"  ·  "+mouse.DpiX+" × "+mouse.DpiY+" DPI":"Reading active settings…",11,"#f3f7ff",31,322,true);
            TextAt(g,mouse.DpiX>0?"Polling rate: "+(mouse.Rate>0?mouse.Rate+" Hz":"Unavailable"):"",10,"#f3f7ff",31,347);
            TextAt(g,mouse.DpiX>0?"Live from mouse":"Wake the mouse to refresh.",9,"#b1afb8",31,370);
            ButtonAt(g,"Open Rapoo Web Hub",new RectangleF(377,330,148,33),"hub");
        }
        void DrawSettings(Graphics g,float width)
        {
            TextAt(g,"Refresh interval",9,"#b1afb8",17,62);
            int[] seconds={30,60,120,300,600};string[] captions={"30s","1min","2min","5min","10min"};float x=112;
            for(int i=0;i<5;i++)
            {
                bool selected=Interval==seconds[i];string command="interval:"+seconds[i];
                Hit(new RectangleF(x-3,59,i==0?36:45,23),command);
                using(var pen=new Pen(Artwork.Color(selected?"#87dfa7":"#b1afb8")))g.DrawEllipse(pen,x,66,8,8);
                if(selected)using(var brush=new SolidBrush(Artwork.Color("#87dfa7")))g.FillEllipse(brush,x+2,68,4,4);
                TextAt(g,captions[i],9,selected?"#87dfa7":"#b1afb8",x+12,62);x+=i==0?39:48;
            }
            TextAt(g,"Start with Windows",10,"#f3f7ff",30,98);
            DrawSwitch(g,new RectangleF(width-69,98,38,20),StartupEnabled);Hit(new RectangleF(17,89,width-34,39),"startup");
            ButtonAt(g,"Windows tray settings",new RectangleF(17,134,width-34,33),"tray");
            ButtonAt(g,"HID calibration",new RectangleF(17,172,width-34,33),"diagnostics");
            ButtonAt(g,"Back to devices",new RectangleF(17,217,width-34,33),"back");
        }
        static void DrawSwitch(Graphics g,RectangleF rect,bool enabled)
        {
            using(var path=DeviceCard.Rounded(Rectangle.Round(rect),10))
            using(var brush=new SolidBrush(Artwork.Color(enabled?"#39785b":"#4b4558")))g.FillPath(brush,path);
            using(var brush=new SolidBrush(Artwork.Color("#f5f2fb")))g.FillEllipse(brush,enabled?rect.Right-17:rect.Left+3,rect.Top+3,14,14);
        }
        void DrawMenu(Graphics g,float width)
        {
            using(var brush=new SolidBrush(Artwork.Color("#302650")))g.FillRectangle(brush,1,1,width-2,32);
            TextAt(g,"CHARGEVIEW",9,"#f3f7ff",14,10,true);
            Icon(g,width-37,6,"close");Icon(g,width-60,6,"refresh");Icon(g,width-88,6,"settings");
            for(int i=0;i<2;i++)
            {
                Battery reading=Readings[i];float y=34+i*47;
                Hit(new RectangleF(1,y,width-2,46),"devices");
                using(var pen=new Pen(Artwork.Color("#282631")))g.DrawLine(pen,1,y-1,width-1,y-1);
                Color color=MainWindow.BatteryColor(reading);
                TextAt(g,reading.Name,11,reading.Stale?"#b1afb8":"#f3f7ff",14,y+10);
                Rectangle rect=new Rectangle(142,(int)y+18,72,9);
                using(var path=DeviceCard.Rounded(rect,4))
                using(var brush=new SolidBrush(Artwork.Color("#4a4657")))g.FillPath(brush,path);
                if(reading.Level>0)using(var path=DeviceCard.Rounded(new Rectangle(142,(int)y+18,Math.Max(8,72*reading.Level/100),9),4))
                using(var brush=new SolidBrush(color))g.FillPath(brush,path);
                TextAt(g,reading.Level<0?"—":reading.Level+"%",12,ColorTranslator.ToHtml(color),225,y+8,true);
            }
            using(var pen=new Pen(Artwork.Color("#282631")))g.DrawLine(pen,1,127,width-1,127);
            Hit(new RectangleF(1,128,width-2,39),"exit");
            if(hovered=="exit")using(var brush=new SolidBrush(Artwork.Color("#392731")))g.FillRectangle(brush,1,128,width-2,39);
            TextAt(g,"Exit Chargeview",10,"#ef9aa6",14,139);
        }
        string At(Point point)
        {
            float scale=DeviceDpiScale;
            PointF logical=new PointF(point.X/scale,point.Y/scale);
            foreach(var hit in hits)if(hit.Key.Contains(logical))return hit.Value;
            return null;
        }
        float DeviceDpiScale{get{using(var g=CreateGraphics())return g.DpiX/96f;}}
        public void ReleaseArtwork()
        {
            for(int i=0;i<cards.Length;i++)
            {
                if(cards[i]!=null)cards[i].Dispose();
                cards[i]=null;cardKeys[i]=null;
            }
            foreach(var image in icons.Values)image.Dispose();
            icons.Clear();
            foreach(var font in fonts.Values)font.Dispose();
            fonts.Clear();
        }
        protected override void OnMouseMove(MouseEventArgs e)
        {
            base.OnMouseMove(e);string command=At(e.Location);
            if(command!=hovered)
            {
                hovered=command;Cursor=command==null?Cursors.Default:Cursors.Hand;
                tooltip.SetToolTip(this,command=="settings"?"Settings":command=="refresh"?"Refresh battery readings":command=="close"?"Close popup":null);
                Invalidate();
            }
        }
        protected override void OnMouseLeave(EventArgs e){base.OnMouseLeave(e);hovered=null;tooltip.Hide(this);Invalidate();}
        protected override void OnMouseUp(MouseEventArgs e){base.OnMouseUp(e);string command=At(e.Location);if(e.Button==MouseButtons.Left && command!=null && Command!=null)Command(command);}
        protected override void Dispose(bool disposing)
        {
            if(disposing){tooltip.Dispose();ReleaseArtwork();}
            base.Dispose(disposing);
        }
    }

    sealed class Fade
    {
        readonly Form form;
        readonly System.Windows.Forms.Timer timer=new System.Windows.Forms.Timer{Interval=15};
        DateTime started;
        double origin,target,duration;
        Action done;
        public Fade(Form window){form=window;timer.Tick+=(s,e)=>Step();window.Disposed+=(s,e)=>timer.Dispose();}
        public void To(double value,Action completed=null)
        {
            timer.Stop();origin=form.Opacity;target=value;duration=value==1?.16:.11;done=completed;started=DateTime.UtcNow;timer.Start();
        }
        void Step()
        {
            double progress=Math.Min(1,(DateTime.UtcNow-started).TotalSeconds/duration);
            double eased=target==1?1-Math.Pow(1-progress,3):progress*progress;
            form.Opacity=origin+(target-origin)*eased;
            if(progress>=1){timer.Stop();if(done!=null)done();}
        }
    }
}
