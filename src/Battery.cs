using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;

namespace ChargeviewNative
{
    [DataContract] sealed class Sample
    {
        [DataMember] public DateTime Time;
        [DataMember] public int Level;
        [DataMember] public bool Charging;
        [DataMember] public double Seconds, Points, LearnedHoursPerPoint;
    }
    sealed class Battery
    {
        public string Name,Source,Status="Waiting for data",Estimate="Estimating…";
        public int Level=-1,DpiX,DpiY,Slot,Rate;
        public bool Charging,Stale=true;
        public DateTime? LastUpdate;
        public Battery(string name,string source){Name=name;Source=source;}
        public Battery Copy(){return (Battery)MemberwiseClone();}
    }
    [DataContract] sealed class LegacySample
    {
        [DataMember] public string updated { get; set; }
        [DataMember] public int level { get; set; }
        [DataMember] public bool charging { get; set; }
        [DataMember] public double[][] runtime { get; set; }
    }
    [DataContract] sealed class Preferences
    {
        [DataMember] public int Interval=60;
        [DataMember] public Dictionary<string,Sample> History=new Dictionary<string,Sample>();
        public static readonly string Folder=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ChargeviewNative");
        public static Preferences Load()
        {
            try { using (var stream=File.OpenRead(Path.Combine(Folder,"preferences.json"))) return (Preferences)new DataContractJsonSerializer(typeof(Preferences)).ReadObject(stream); }
            catch (Exception)
            {
                var preferences=new Preferences();
                try
                {
                    string file=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"DeskCharge","battery.json");
                    using(var stream=File.OpenRead(file))
                    {
                        var serializer=new DataContractJsonSerializer(typeof(Dictionary<string,LegacySample>),new DataContractJsonSerializerSettings{UseSimpleDictionaryFormat=true});
                        var legacy=(Dictionary<string,LegacySample>)serializer.ReadObject(stream);
                        foreach(var pair in legacy)
                        {
                            var value=pair.Value;
                            DateTime time;
                            if(value.level<0 || value.level>100 || !DateTime.TryParse(value.updated,CultureInfo.InvariantCulture,DateTimeStyles.RoundtripKind,out time))continue;
                            double seconds=value.runtime==null?0:value.runtime.Where(b=>b.Length==3 && b[1]>=0 && b[2]>=0).Sum(b=>b[1]);
                            double points=value.runtime==null?0:value.runtime.Where(b=>b.Length==3 && b[1]>=0 && b[2]>=0).Sum(b=>b[2]);
                            preferences.History[pair.Key]=new Sample{Time=time.ToUniversalTime(),Level=value.level,Charging=value.charging,Seconds=seconds,Points=points,LearnedHoursPerPoint=!value.charging && seconds>=1800 && points>=2?seconds/points/3600:0};
                        }
                    }
                }
                catch(Exception){}
                return preferences;
            }
        }
        public void Save()
        {
            Directory.CreateDirectory(Folder);
            string file=Path.Combine(Folder,"preferences.json"),temporary=file+".tmp";
            using (var stream=File.Create(temporary)) new DataContractJsonSerializer(typeof(Preferences)).WriteObject(stream,this);
            if (File.Exists(file)) File.Replace(temporary,file,null);else File.Move(temporary,file);
        }
        public void Observe(Battery battery)
        {
            if (battery.Level<0) {battery.Estimate="";return;}
            if (battery.Stale) return;
            DateTime now=DateTime.UtcNow;
            Sample previous;
            History.TryGetValue(battery.Name,out previous);
            var sample=new Sample {Time=now,Level=battery.Level,Charging=battery.Charging};
            if (previous!=null)
            {
                sample.LearnedHoursPerPoint=previous.LearnedHoursPerPoint;
                if (previous.Charging==battery.Charging)
                {
                    sample.Seconds=previous.Seconds; sample.Points=previous.Points;
                    double elapsed=(now-previous.Time).TotalSeconds;
                    int difference=battery.Charging ? battery.Level-previous.Level : previous.Level-battery.Level;
                    if (elapsed>0 && elapsed<=Math.Max(180,Interval*3) && difference>=0)
                    {sample.Seconds+=elapsed;sample.Points+=difference;}
                    if (battery.Charging && elapsed>Math.Max(180,Interval*3)) {sample.Seconds=0;sample.Points=0;}
                }
            }
            battery.Estimate="Estimating…";
            if (battery.Charging)
            {
                if (battery.Level==100) battery.Estimate="Fully charged";
                else if (sample.Seconds>=300 && sample.Points>=2)
                {
                    int minutes=Math.Max(5,(int)Math.Round((100-battery.Level)*sample.Seconds/sample.Points/300)*5);
                    battery.Estimate="~"+(minutes/60>0 ? minutes/60+" h " : "")+minutes%60+" min to full";
                }
            }
            else
            {
                if (sample.Seconds>=1800 && sample.Points>=2) sample.LearnedHoursPerPoint=sample.Seconds/sample.Points/3600;
                if (battery.Level==0) battery.Estimate="Charge now";
                else if (sample.LearnedHoursPerPoint>0)
                {
                    int hours=Math.Max(1,(int)Math.Round(battery.Level*sample.LearnedHoursPerPoint));
                    battery.Estimate=hours<24 ? "~"+hours+" h left" : "~"+hours/24+" d "+hours%24+" h left";
                }
            }
            History[battery.Name]=sample;
        }
    }
}
