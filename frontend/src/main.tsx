import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Archive, CalendarDays, CheckCircle2, ChevronRight, CircleAlert, Clock3, ExternalLink,
  FileCheck2, FileText, Inbox, LayoutDashboard, ListChecks, Mail, Plus, RefreshCw, Save, Search,
  Settings, ShieldCheck, Sparkles, Upload, UserRound, WandSparkles, X,
} from "lucide-react";
import "./styles.css";
import "./tracker.css";
import "./profile-vault.css";
import "./profile-actions.css";
import "./preparation.css";
import "./autopilot-command.css";

type Application = {
  id:number; title:string; organization:string; category:string; source_url:string; deadline?:string;
  workflow_status:string; outcome:string; submitted_at?:string; follow_up_at?:string; notes:string; is_stale:boolean;
};
type TimelineEvent = { id:number; event_type:string; title:string; detail:string; created_at:string };
type ApplicationDetail = Application & { timeline:TimelineEvent[] };
type Opportunity = {
  id:number; title:string; organization:string; category:string; source:string; source_url:string;
  deadline?:string; location?:string; effort:string; fit_score:number; tags:string[]; summary:string;
};
type ProfileDocument = { id:number; filename:string; extraction_status:string; candidate_count:number; created_at:string };
type KnowledgeStats = { chunks:number; answers:number; documents:number };
type AIStatus = { provider:string; configured:boolean; model:string };
type EmailMatch = {
  id:number; sender:string; subject:string; excerpt:string; classification:string; confidence:number;
  review_status:string; application_title?:string;
};
type Dashboard = {
  stats:{ opportunities:number; applications:number; needs_attention:number; accepted:number };
  applications:Application[]; opportunities:Opportunity[]; pending_matches:number;
};
type AppSettings = { stale_days:number };
type PreparationField = { id:number; label:string; field_type:string; required:number; mapped_value?:string; confidence:number; review_status:string; reason:string };
type PreparationPreview = { id:number; application_id:number; adapter:string; source_url:string; status:string; fields:PreparationField[]; requires_approval:boolean };
type AutofillReceipt = { session_id:number; status:string; filled:string[]; skipped:string[]; screenshot_url?:string; submitted:boolean };

const api = async <T,>(path:string, options?:RequestInit):Promise<T> => {
  const response = await fetch(`/api${path}`, { headers:{"Content-Type":"application/json"}, ...options });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};
const labels:Record<string,string> = {
  ready_for_review:"Ready for review", needs_input:"Needs input", discovered:"Discovered",
  submitted:"Submitted", pending:"Pending", accepted:"Accepted", rejected:"Rejected",
  waitlisted:"Waitlisted", acknowledgement:"Acknowledgement", next_step:"Next step", unrelated:"Needs review",
};
const display = (value:string) => labels[value] || value.replaceAll("_"," ");
const formatDate = (value?:string) => value ? new Intl.DateTimeFormat("en-GB",{day:"numeric",month:"short"}).format(new Date(value)) : "No deadline";

function App() {
  const [view,setView]=useState("dashboard");
  const [dashboard,setDashboard]=useState<Dashboard|null>(null);
  const [applications,setApplications]=useState<Application[]>([]);
  const [opportunities,setOpportunities]=useState<Opportunity[]>([]);
  const [profileDocuments,setProfileDocuments]=useState<ProfileDocument[]>([]);
  const [knowledgeStats,setKnowledgeStats]=useState<KnowledgeStats>({chunks:0,answers:0,documents:0});
  const [aiStatus,setAIStatus]=useState<AIStatus>({provider:"openai",configured:false,model:"gpt-4o-mini"});
  const [matches,setMatches]=useState<EmailMatch[]>([]);
  const [settings,setSettings]=useState<AppSettings>({stale_days:14});
  const [selectedApplication,setSelectedApplication]=useState<ApplicationDetail|null>(null);
  const [preparation,setPreparation]=useState<PreparationPreview|null>(null);
  const [filter,setFilter]=useState("all");
  const [busy,setBusy]=useState(false);
  const [toast,setToast]=useState("");

  const load=async()=>{
    const [dash,apps,opps,documents,knowledge,ai,emailMatches,appSettings]=await Promise.all([
      api<Dashboard>("/dashboard"),api<Application[]>("/applications"),api<Opportunity[]>("/opportunities"),
      api<ProfileDocument[]>("/profile/documents"),
      api<KnowledgeStats>("/knowledge/stats"),api<AIStatus>("/ai/status"),api<EmailMatch[]>("/email-matches"),api<AppSettings>("/settings"),
    ]);
    setDashboard(dash);setApplications(apps);setOpportunities(opps);setProfileDocuments(documents);setKnowledgeStats(knowledge);setAIStatus(ai);setMatches(emailMatches);setSettings(appSettings);
  };
  useEffect(()=>{load().catch(console.error)},[]);
  const notify=(message:string)=>{setToast(message);setTimeout(()=>setToast(""),2800)};
  const run=async(action:()=>Promise<unknown>,message:string)=>{
    setBusy(true);
    try{await action();await load();notify(message)}catch(error){notify(error instanceof Error?error.message:"Something went wrong")}
    finally{setBusy(false)}
  };
  const prepare=(id:number)=>run(async()=>{await api(`/applications/${id}/prepare`,{method:"POST"});setPreparation(await api<PreparationPreview>(`/applications/${id}/preparation`))},"Application prepared for review");
  const addOpportunity=(opp:Opportunity)=>run(()=>api("/applications",{method:"POST",body:JSON.stringify({
    opportunity_id:opp.id,title:opp.title,organization:opp.organization,category:opp.category,
    source_url:opp.source_url,deadline:opp.deadline,tags:opp.tags,
  })}),"Added to your application queue");
  const sync=()=>run(()=>api("/email-sync",{method:"POST"}),"Inbox sync complete");
  const confirm=(id:number)=>run(()=>api(`/email-matches/${id}/confirm`,{method:"POST",body:JSON.stringify({accept:true})}),"Email match confirmed");
  const openApplication=async(id:number)=>setSelectedApplication(await api<ApplicationDetail>(`/applications/${id}`));
  const updateApplication=(id:number,changes:Record<string,string>)=>run(async()=>{
    await api(`/applications/${id}`,{method:"PATCH",body:JSON.stringify(changes)});
    setSelectedApplication(await api<ApplicationDetail>(`/applications/${id}`));
  },"Application updated");
  const filteredApps=useMemo(()=>applications.filter(app=>filter==="all"||app.workflow_status===filter||app.outcome===filter||(filter==="stale"&&app.is_stale)),[applications,filter]);
  const nav=[
    ["dashboard","Dashboard",LayoutDashboard],["opportunities","Opportunities",Sparkles],
    ["applications","Applications",ListChecks],["profile","Profile vault",UserRound],
    ["inbox","Inbox matches",Inbox],["settings","Settings",Settings],
  ] as const;

  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><div className="logo">A</div><div><strong>ApplyPilot</strong><span>Application OS</span></div></div>
      <nav>{nav.map(([id,label,Icon])=><button key={id} className={view===id?"active":""} onClick={()=>setView(id)}><Icon size={18}/><span>{label}</span>{id==="inbox"&&dashboard?.pending_matches?<b>{dashboard.pending_matches}</b>:null}</button>)}</nav>
      <div className="privacy"><ShieldCheck size={18}/><div><strong>Private workspace</strong><span>Local-first storage</span></div></div>
    </aside>
    <main><header><div><p className="eyebrow">Personal application desk</p><h1>{nav.find(([id])=>id===view)?.[1]}</h1></div><div className="header-actions"><button className="icon-btn" title="Refresh" onClick={()=>run(load,"Dashboard refreshed")}><RefreshCw size={18}/></button><button className="primary" onClick={()=>setView("applications")}><Plus size={17}/> New application</button></div></header>
      {view==="dashboard"&&<DashboardView dashboard={dashboard} prepare={prepare} openApplication={openApplication} setView={setView}/>}
      {view==="opportunities"&&<Opportunities opportunities={opportunities} add={addOpportunity} importSources={()=>run(()=>api("/opportunities/import",{method:"POST"}),"Opportunity sources checked")}/>}
      {view==="applications"&&<Applications applications={filteredApps} filter={filter} setFilter={setFilter} prepare={prepare} openApplication={openApplication} run={run} autopilot={async(url)=>{const result=await api<{application_id:number}>("/autopilot/prepare",{method:"POST",body:JSON.stringify({source_url:url})});setPreparation(await api<PreparationPreview>(`/applications/${result.application_id}/preparation`));await load()}}/>}
      {view==="profile"&&<Profile documents={profileDocuments} knowledge={knowledgeStats} run={run}/>}
      {view==="inbox"&&<InboxView matches={matches} sync={sync} confirm={confirm}/>}
      {view==="settings"&&<SettingsView settings={settings} ai={aiStatus} run={run}/>}
    </main>
    {selectedApplication&&<ApplicationPanel application={selectedApplication} close={()=>setSelectedApplication(null)} update={updateApplication}/>}
    {preparation&&<PreparationPanel preparation={preparation} close={()=>setPreparation(null)} refresh={async()=>setPreparation(await api<PreparationPreview>(`/applications/${preparation.application_id}/preparation`))}/>}
    {toast&&<div className="toast">{toast}</div>}{busy&&<div className="busy"><RefreshCw size={20}/></div>}
  </div>;
}

function DashboardView({dashboard,prepare,openApplication,setView}:{dashboard:Dashboard|null;prepare:(id:number)=>void;openApplication:(id:number)=>void;setView:(v:string)=>void}) {
  if(!dashboard)return <EmptyLoading/>;
  const stats=[["Open opportunities",dashboard.stats.opportunities,Sparkles],["Applications tracked",dashboard.stats.applications,FileText],["Needs attention",dashboard.stats.needs_attention,CircleAlert],["Accepted",dashboard.stats.accepted,CheckCircle2]] as const;
  return <div className="content"><section className="stats">{stats.map(([label,value,Icon])=><article key={label}><Icon size={19}/><span>{label}</span><strong>{value}</strong></article>)}</section>
    <section className="two-col"><div><SectionHead title="Application queue" action="View all" onClick={()=>setView("applications")}/><div className="list">{dashboard.applications.map(app=><ApplicationRow key={app.id} app={app} prepare={prepare} open={openApplication}/>)}</div></div>
      <div><SectionHead title="Best opportunities" action="Browse" onClick={()=>setView("opportunities")}/><div className="opportunity-stack">{dashboard.opportunities.slice(0,3).map(opp=><article className="compact-opportunity" key={opp.id}><div><strong>{opp.title}</strong><span>{opp.source} · {formatDate(opp.deadline)}</span></div><b>{opp.fit_score}%</b></article>)}</div></div></section>
    <section className="band"><div><p className="eyebrow">Low-effort mode</p><h2>Let the queue do the remembering.</h2><span>Prepare applications in batches, then review only the decisions that need you.</span></div><button className="secondary" onClick={()=>setView("opportunities")}>Find an opportunity <ChevronRight size={17}/></button></section>
  </div>;
}
function Opportunities({opportunities,add,importSources}:{opportunities:Opportunity[];add:(o:Opportunity)=>void;importSources:()=>void}) {
  return <div className="content"><div className="toolbar"><div className="search"><Search size={17}/><input placeholder="Search opportunities"/></div><button className="secondary" onClick={importSources}><RefreshCw size={16}/> Import sources</button></div><div className="opportunity-grid">{opportunities.map(opp=><article className="opportunity-card" key={opp.id}><div className="card-top"><span className="source">{opp.source}</span><b>{opp.fit_score}% fit</b></div><h3>{opp.title}</h3><p>{opp.summary}</p><div className="meta"><span><CalendarDays size={15}/>{formatDate(opp.deadline)}</span><span>{opp.location}</span><span>{opp.effort} effort</span></div><div className="tags">{opp.tags.map(tag=><span key={tag}>{tag}</span>)}</div><button className="secondary full" onClick={()=>add(opp)}><Plus size={16}/> Add to queue</button></article>)}</div></div>;
}
function Applications({applications,filter,setFilter,prepare,openApplication,run,autopilot}:{applications:Application[];filter:string;setFilter:(f:string)=>void;prepare:(id:number)=>void;openApplication:(id:number)=>void;run:(a:()=>Promise<unknown>,m:string)=>void;autopilot:(url:string)=>Promise<void>}) {
  const [showCreate,setShowCreate]=useState(false);
  return <div className="content"><AutopilotCommand run={run} autopilot={autopilot}/><div className="toolbar"><div className="filter-row">{["all","ready_for_review","submitted","accepted","rejected","stale"].map(value=><button key={value} className={filter===value?"selected":""} onClick={()=>setFilter(value)}>{display(value)}</button>)}</div><button className="primary" onClick={()=>setShowCreate(!showCreate)}><Plus size={16}/> Add manually</button></div>{showCreate&&<ManualApplication run={run} close={()=>setShowCreate(false)}/>}<div className="list">{applications.length?applications.map(app=><ApplicationRow key={app.id} app={app} prepare={prepare} open={openApplication}/>):<Empty title="Nothing in this view" text="Change the filter or add an opportunity to your queue."/>}</div></div>;
}
function AutopilotCommand({run,autopilot}:{run:(a:()=>Promise<unknown>,m:string)=>void;autopilot:(url:string)=>Promise<void>}) {
  const [url,setUrl]=useState("");
  const launch=()=>{if(!url)return;run(()=>autopilot(url),"Form inspected. Review your draft.")};
  return <section className="autopilot-command"><div><p className="eyebrow">Lazy mode</p><h2>Paste a form. Let ApplyPilot prepare it.</h2><span>The browser inspects the page first. You review every answer before live autofill.</span></div><div className="command-input"><input placeholder="https://example.com/application" value={url} onChange={e=>setUrl(e.target.value)} onKeyDown={e=>{if(e.key==="Enter")launch()}}/><button className="primary" onClick={launch}><WandSparkles size={16}/> Prepare form</button></div><button className="demo-link" onClick={()=>setUrl(`${window.location.origin}/demo/application-form`)}>Use local demo form</button></section>;
}
function ApplicationRow({app,prepare,open}:{app:Application;prepare:(id:number)=>void;open:(id:number)=>void}) {
  return <article className="application-row" onClick={()=>open(app.id)}><div className="app-icon"><FileText size={18}/></div><div className="grow"><strong>{app.title}</strong><span>{app.organization} · {app.category}</span></div><div className="date"><span>Deadline</span><strong>{formatDate(app.deadline)}</strong></div><span className={`status ${app.outcome!=="pending"?app.outcome:app.workflow_status}`}>{app.is_stale?"No reply":display(app.outcome!=="pending"?app.outcome:app.workflow_status)}</span>{!["submitted","archived"].includes(app.workflow_status)&&<button className="icon-btn" title="Prepare application" onClick={event=>{event.stopPropagation();prepare(app.id)}}><ChevronRight size={18}/></button>}</article>;
}
function ManualApplication({run,close}:{run:(a:()=>Promise<unknown>,m:string)=>void;close:()=>void}) {
  const [form,setForm]=useState({title:"",organization:"",category:"Application",source_url:"",deadline:"",notes:""});
  const save=()=>{if(!form.title||!form.organization||!form.source_url)return;run(()=>api("/applications",{method:"POST",body:JSON.stringify({...form,deadline:form.deadline||null})}),"Application added to tracker");close()};
  return <section className="create-panel"><div className="section-head"><h2>Add application</h2><button onClick={close}><X size={16}/></button></div><div className="form-grid"><input placeholder="Application title" value={form.title} onChange={e=>setForm({...form,title:e.target.value})}/><input placeholder="Organization" value={form.organization} onChange={e=>setForm({...form,organization:e.target.value})}/><select value={form.category} onChange={e=>setForm({...form,category:e.target.value})}><option>Application</option><option>Hackathon</option><option>Competition</option><option>Job</option><option>Scholarship</option><option>Event</option></select><input type="date" value={form.deadline} onChange={e=>setForm({...form,deadline:e.target.value})}/><input className="span-2" placeholder="Application URL" value={form.source_url} onChange={e=>setForm({...form,source_url:e.target.value})}/><textarea className="span-2" placeholder="Notes" value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})}/></div><button className="primary" onClick={save}><Save size={16}/> Save application</button></section>;
}
function ApplicationPanel({application,close,update}:{application:ApplicationDetail;close:()=>void;update:(id:number,c:Record<string,string>)=>void}) {
  const [notes,setNotes]=useState(application.notes||"");
  useEffect(()=>setNotes(application.notes||""),[application.notes]);
  return <aside className="detail-panel"><div className="detail-head"><div><p className="eyebrow">Application record</p><h2>{application.title}</h2><span>{application.organization}</span></div><button className="icon-btn" title="Close details" onClick={close}><X size={17}/></button></div><div className="detail-actions"><a className="secondary" href={application.source_url} target="_blank" rel="noreferrer"><ExternalLink size={15}/> Open form</a>{application.workflow_status!=="archived"&&<button className="secondary" onClick={()=>update(application.id,{workflow_status:"archived"})}><Archive size={15}/> Archive</button>}</div><dl><div><dt>Workflow</dt><dd>{display(application.workflow_status)}</dd></div><div><dt>Outcome</dt><dd>{display(application.outcome)}</dd></div><div><dt>Deadline</dt><dd>{formatDate(application.deadline)}</dd></div><div><dt>Follow up</dt><dd>{formatDate(application.follow_up_at)}</dd></div></dl><label className="notes-label">Notes<textarea value={notes} onChange={e=>setNotes(e.target.value)}/></label><button className="primary" onClick={()=>update(application.id,{notes})}><Save size={15}/> Save notes</button><section className="timeline"><h3>Timeline</h3>{application.timeline.map(event=><article key={event.id}><Clock3 size={15}/><div><strong>{event.title}</strong><span>{new Date(event.created_at).toLocaleString("en-GB")}</span><p>{event.detail}</p></div></article>)}</section></aside>;
}
function Profile({documents,knowledge,run}:{documents:ProfileDocument[];knowledge:KnowledgeStats;run:(a:()=>Promise<unknown>,m:string)=>void}) {
  const [memory,setMemory]=useState({label:"",content:""});
  const add=()=>{if(!memory.label||!memory.content)return;run(()=>api("/knowledge/memories",{method:"POST",body:JSON.stringify(memory)}),"Memory note stored");setMemory({label:"",content:""})};
  const upload=(file:File)=>{const data=new FormData();data.append("file",file);return run(async()=>{const response=await fetch("/api/profile/import",{method:"POST",body:data});if(!response.ok)throw new Error(await response.text())},"CV analysed. Review the suggested facts.")};
  const uploadGithub=(file:File)=>{const data=new FormData();data.append("file",file);return run(async()=>{const response=await fetch("/api/profile/import-github-export",{method:"POST",body:data});if(!response.ok)throw new Error(await response.text())},"GitHub projects imported. Review the suggestions.")};
  const reindex=()=>run(()=>api("/knowledge/reindex",{method:"POST"}),"Local knowledge vault indexed");
  return <div className="content"><section className="profile-intro"><div><p className="eyebrow">Private local knowledge</p><h2>Your source data vault</h2><span>{knowledge.chunks} searchable passages · {knowledge.answers} reviewed answers · forms search your stored sources at fill time.</span></div><div className="upload-actions"><button className="secondary" onClick={reindex}><RefreshCw size={16}/> Reindex vault</button><label className="upload"><Upload size={17}/> Import CV<input type="file" accept=".pdf,.docx,.txt,.md" onChange={e=>{const file=e.target.files?.[0];if(file)upload(file)}}/></label><label className="upload"><Upload size={17}/> Import GitHub<input type="file" accept=".tar.gz" onChange={e=>{const file=e.target.files?.[0];if(file)uploadGithub(file)}}/></label></div></section>
    <div className="profile-grid"><section className="document-list"><h3>Imported source data</h3>{documents.length?documents.map(document=><article key={document.id}><FileCheck2 size={16}/><div><strong>{document.filename}</strong><span>{document.candidate_count} extracted references · {document.extraction_status}</span></div></article>):<span>No source data imported yet.</span>}</section><aside><section className="add-panel"><h3>Add memory note</h3><input placeholder="Label, such as Work preferences" value={memory.label} onChange={e=>setMemory({...memory,label:e.target.value})}/><textarea placeholder="Write anything the AI should remember when answering forms" value={memory.content} onChange={e=>setMemory({...memory,content:e.target.value})}/><button className="primary" onClick={add}><Plus size={16}/> Store memory</button></section></aside></div></div>;
}
function PreparationPanel({preparation,close,refresh}:{preparation:PreparationPreview;close:()=>void;refresh:()=>Promise<void>}) {
  const [receipt,setReceipt]=useState<AutofillReceipt|null>(null);const [launching,setLaunching]=useState(false);
  const save=async(field:PreparationField,value:string)=>{await api(`/preparation-fields/${field.id}`,{method:"PATCH",body:JSON.stringify({mapped_value:value})});await refresh()};
  const autofill=async()=>{setLaunching(true);try{setReceipt(await api<AutofillReceipt>(`/applications/${preparation.application_id}/autofill`,{method:"POST"}))}finally{setLaunching(false)}};
  return <aside className="preparation-panel"><div className="detail-head"><div><p className="eyebrow">Review before any browser changes</p><h2>Prepared form draft</h2><span>{preparation.adapter} · {preparation.fields.length} inspected fields</span></div><button className="icon-btn" title="Close preparation" onClick={close}><X size={17}/></button></div><div className="approval-lock"><ShieldCheck size={18}/><div><strong>Submission locked</strong><span>ApplyPilot fills reviewed values only. It will not click the external submit button.</span></div></div><button className="primary autofill-btn" disabled={launching} onClick={autofill}><WandSparkles size={16}/>{launching?" Opening browser...":" Fill visible browser"}</button>{receipt&&<div className="autofill-receipt"><CheckCircle2 size={17}/><div><strong>Browser filled for your review</strong><span>{receipt.filled.length} values filled · {receipt.skipped.length} skipped · no submission</span>{receipt.screenshot_url&&<a href={receipt.screenshot_url} target="_blank" rel="noreferrer">Open screenshot receipt</a>}</div></div>}<section className="prepared-fields">{preparation.fields.map(field=><PreparedField key={field.id} field={field} save={save}/>)}</section></aside>;
}
function PreparedField({field,save}:{field:PreparationField;save:(field:PreparationField,value:string)=>Promise<void>}) {
  const [value,setValue]=useState(field.mapped_value||"");useEffect(()=>setValue(field.mapped_value||""),[field.mapped_value]);
  return <article className={`prepared-field ${field.review_status}`}><div className="prepared-field-head"><div><strong>{field.label}</strong><span>{field.field_type}{field.required?" · required":""}</span></div><b>{field.review_status==="needs_input"?"Needs input":display(field.review_status)}</b></div><textarea value={value} placeholder="Add a reviewed answer" onChange={e=>setValue(e.target.value)}/><div><span>{field.reason}</span><button className="secondary small" onClick={()=>save(field,value)}><Save size={14}/> Save draft</button></div></article>;
}
function InboxView({matches,sync,confirm}:{matches:EmailMatch[];sync:()=>void;confirm:(id:number)=>void}) {
  return <div className="content"><div className="toolbar"><div><p className="eyebrow">Read-only inbox access</p><span className="muted">Messages are never sent, deleted, archived, or marked as read.</span></div><button className="secondary" onClick={sync}><RefreshCw size={16}/> Sync inboxes</button></div><div className="list">{matches.length?matches.map(match=><article className="email-row" key={match.id}><Mail size={19}/><div className="grow"><strong>{match.subject}</strong><span>{match.sender}</span><p>{match.excerpt}</p></div><div className="email-side"><span className={`status ${match.classification}`}>{display(match.classification)}</span><small>{Math.round(match.confidence*100)}% confidence</small>{match.review_status==="pending"&&match.application_title&&<button className="secondary small" onClick={()=>confirm(match.id)}>Confirm match</button>}</div></article>):<Empty title="No matched email yet" text="Sync Gmail and Microsoft inbox adapters to reconcile application replies."/>}</div></div>;
}
function SettingsView({settings,ai,run}:{settings:AppSettings;ai:AIStatus;run:(a:()=>Promise<unknown>,m:string)=>void}) {
  const [staleDays,setStaleDays]=useState(settings.stale_days);useEffect(()=>setStaleDays(settings.stale_days),[settings.stale_days]);
  return <div className="content settings-grid"><section><h2>AI answer provider</h2><SettingRow title="OpenAI Responses API" text={`${ai.model} · grounded answers from retrieved private memory`} action={ai.configured?"Configured":"API key required"}/></section><section><h2>Inbox providers</h2><SettingRow title="Gmail" text="Read-only OAuth adapter" action="Configure"/><SettingRow title="Microsoft" text="Read-only Graph adapter" action="Configure"/></section><section><h2>Automation guardrails</h2><SettingRow title="Approval required" text="Every external submission needs your confirmation" action="Always on"/><div className="setting-row"><div><strong>No-reply reminder</strong><span>Flag pending applications after this many days</span></div><div className="number-setting"><input type="number" min="1" max="180" value={staleDays} onChange={e=>setStaleDays(Number(e.target.value))}/><button title="Save reminder days" onClick={()=>run(()=>api("/settings",{method:"PUT",body:JSON.stringify({stale_days:staleDays})}),"Reminder settings saved")}><Save size={14}/></button></div></div></section><section><h2>Browser workspace</h2><SettingRow title="Persistent browser profile" text="Reuse your local authenticated sessions" action="Local"/></section></div>;
}
function SettingRow({title,text,action}:{title:string;text:string;action:string}){return <div className="setting-row"><div><strong>{title}</strong><span>{text}</span></div><button>{action}</button></div>}
function SectionHead({title,action,onClick}:{title:string;action:string;onClick:()=>void}){return <div className="section-head"><h2>{title}</h2><button onClick={onClick}>{action}<ChevronRight size={16}/></button></div>}
function EmptyLoading(){return <div className="content"><Empty title="Loading your application desk" text="Pulling together your local workspace."/></div>}
function Empty({title,text}:{title:string;text:string}){return <div className="empty"><Archive size={24}/><strong>{title}</strong><span>{text}</span></div>}
createRoot(document.getElementById("root")!).render(<React.StrictMode><App/></React.StrictMode>);
