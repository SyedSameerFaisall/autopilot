import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Archive,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  FileText,
  Inbox,
  LayoutDashboard,
  ListChecks,
  Mail,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  UserRound,
} from "lucide-react";
import "./styles.css";

type Application = {
  id: number;
  title: string;
  organization: string;
  category: string;
  source_url: string;
  deadline?: string;
  workflow_status: string;
  outcome: string;
  submitted_at?: string;
  follow_up_at?: string;
  is_stale: boolean;
};
type Opportunity = {
  id: number;
  title: string;
  organization: string;
  category: string;
  source: string;
  source_url: string;
  deadline?: string;
  location?: string;
  effort: string;
  fit_score: number;
  tags: string[];
  summary: string;
};
type Fact = { id: number; section: string; label: string; value: string; verified: number };
type EmailMatch = {
  id: number;
  sender: string;
  subject: string;
  excerpt: string;
  classification: string;
  confidence: number;
  review_status: string;
  application_title?: string;
};
type Dashboard = {
  stats: { opportunities: number; applications: number; needs_attention: number; accepted: number };
  applications: Application[];
  opportunities: Opportunity[];
  pending_matches: number;
};

const api = async <T,>(path: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};

const labels: Record<string, string> = {
  ready_for_review: "Ready for review",
  needs_input: "Needs input",
  discovered: "Discovered",
  submitted: "Submitted",
  pending: "Pending",
  accepted: "Accepted",
  rejected: "Rejected",
  waitlisted: "Waitlisted",
  acknowledgement: "Acknowledgement",
  next_step: "Next step",
  unrelated: "Needs review",
};
const display = (value: string) => labels[value] || value.replaceAll("_", " ");
const formatDate = (value?: string) =>
  value ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" }).format(new Date(value)) : "No deadline";

function App() {
  const [view, setView] = useState("dashboard");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [applications, setApplications] = useState<Application[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [matches, setMatches] = useState<EmailMatch[]>([]);
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  const load = async () => {
    const [dash, apps, opps, profile, emailMatches] = await Promise.all([
      api<Dashboard>("/dashboard"),
      api<Application[]>("/applications"),
      api<Opportunity[]>("/opportunities"),
      api<Fact[]>("/profile"),
      api<EmailMatch[]>("/email-matches"),
    ]);
    setDashboard(dash); setApplications(apps); setOpportunities(opps); setFacts(profile); setMatches(emailMatches);
  };
  useEffect(() => { load().catch(console.error); }, []);

  const notify = (message: string) => { setToast(message); setTimeout(() => setToast(""), 2800); };
  const run = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try { await action(); await load(); notify(message); } catch (error) { notify(error instanceof Error ? error.message : "Something went wrong"); }
    finally { setBusy(false); }
  };
  const prepare = (id: number) => run(() => api(`/applications/${id}/prepare`, { method: "POST" }), "Application prepared for review");
  const addOpportunity = (opp: Opportunity) =>
    run(() => api("/applications", { method: "POST", body: JSON.stringify({ opportunity_id: opp.id, title: opp.title, organization: opp.organization, category: opp.category, source_url: opp.source_url, deadline: opp.deadline, tags: opp.tags }) }), "Added to your application queue");
  const sync = () => run(() => api("/email-sync", { method: "POST" }), "Inbox sync complete");
  const confirm = (id: number) => run(() => api(`/email-matches/${id}/confirm`, { method: "POST", body: JSON.stringify({ accept: true }) }), "Email match confirmed");

  const filteredApps = useMemo(() => applications.filter((app) =>
    filter === "all" || app.workflow_status === filter || app.outcome === filter || (filter === "stale" && app.is_stale)
  ), [applications, filter]);

  const nav = [
    ["dashboard", "Dashboard", LayoutDashboard],
    ["opportunities", "Opportunities", Sparkles],
    ["applications", "Applications", ListChecks],
    ["profile", "Profile vault", UserRound],
    ["inbox", "Inbox matches", Inbox],
    ["settings", "Settings", Settings],
  ] as const;

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="logo">A</div><div><strong>ApplyPilot</strong><span>Application OS</span></div></div>
      <nav>{nav.map(([id, label, Icon]) => <button key={id} className={view === id ? "active" : ""} onClick={() => setView(id)}><Icon size={18}/><span>{label}</span>{id === "inbox" && dashboard?.pending_matches ? <b>{dashboard.pending_matches}</b> : null}</button>)}</nav>
      <div className="privacy"><ShieldCheck size={18}/><div><strong>Private workspace</strong><span>Local-first storage</span></div></div>
    </aside>
    <main>
      <header><div><p className="eyebrow">Personal application desk</p><h1>{nav.find(([id]) => id === view)?.[1]}</h1></div><div className="header-actions"><button className="icon-btn" title="Refresh" onClick={() => run(load, "Dashboard refreshed")}><RefreshCw size={18}/></button><button className="primary" onClick={() => setView("opportunities")}><Plus size={17}/> New application</button></div></header>
      {view === "dashboard" && <DashboardView dashboard={dashboard} prepare={prepare} setView={setView}/>}
      {view === "opportunities" && <Opportunities opportunities={opportunities} add={addOpportunity} importSources={() => run(() => api("/opportunities/import", { method: "POST" }), "Opportunity sources checked")}/>}
      {view === "applications" && <Applications applications={filteredApps} filter={filter} setFilter={setFilter} prepare={prepare}/>}
      {view === "profile" && <Profile facts={facts} run={run}/>}
      {view === "inbox" && <InboxView matches={matches} sync={sync} confirm={confirm}/>}
      {view === "settings" && <SettingsView/>}
    </main>
    {toast && <div className="toast">{toast}</div>}
    {busy && <div className="busy"><RefreshCw size={20}/></div>}
  </div>;
}

function DashboardView({ dashboard, prepare, setView }: { dashboard: Dashboard | null; prepare: (id:number)=>void; setView:(v:string)=>void }) {
  if (!dashboard) return <EmptyLoading/>;
  const stats = [
    ["Open opportunities", dashboard.stats.opportunities, Sparkles],
    ["Applications tracked", dashboard.stats.applications, FileText],
    ["Needs attention", dashboard.stats.needs_attention, CircleAlert],
    ["Accepted", dashboard.stats.accepted, CheckCircle2],
  ] as const;
  return <div className="content">
    <section className="stats">{stats.map(([label, value, Icon]) => <article key={label}><Icon size={19}/><span>{label}</span><strong>{value}</strong></article>)}</section>
    <section className="two-col">
      <div><SectionHead title="Application queue" action="View all" onClick={() => setView("applications")}/><div className="list">{dashboard.applications.map(app => <ApplicationRow key={app.id} app={app} prepare={prepare}/>)}</div></div>
      <div><SectionHead title="Best opportunities" action="Browse" onClick={() => setView("opportunities")}/><div className="opportunity-stack">{dashboard.opportunities.slice(0,3).map(opp => <article className="compact-opportunity" key={opp.id}><div><strong>{opp.title}</strong><span>{opp.source} · {formatDate(opp.deadline)}</span></div><b>{opp.fit_score}%</b></article>)}</div></div>
    </section>
    <section className="band"><div><p className="eyebrow">Low-effort mode</p><h2>Let the queue do the remembering.</h2><span>Prepare applications in batches, then review only the decisions that need you.</span></div><button className="secondary" onClick={() => setView("opportunities")}>Find an opportunity <ChevronRight size={17}/></button></section>
  </div>;
}

function Opportunities({ opportunities, add, importSources }: { opportunities: Opportunity[]; add:(o:Opportunity)=>void; importSources:()=>void }) {
  return <div className="content"><div className="toolbar"><div className="search"><Search size={17}/><input placeholder="Search opportunities"/></div><button className="secondary" onClick={importSources}><RefreshCw size={16}/> Import sources</button></div><div className="opportunity-grid">{opportunities.map(opp => <article className="opportunity-card" key={opp.id}><div className="card-top"><span className="source">{opp.source}</span><b>{opp.fit_score}% fit</b></div><h3>{opp.title}</h3><p>{opp.summary}</p><div className="meta"><span><CalendarDays size={15}/>{formatDate(opp.deadline)}</span><span>{opp.location}</span><span>{opp.effort} effort</span></div><div className="tags">{opp.tags.map(tag => <span key={tag}>{tag}</span>)}</div><button className="secondary full" onClick={() => add(opp)}><Plus size={16}/> Add to queue</button></article>)}</div></div>;
}

function Applications({ applications, filter, setFilter, prepare }: { applications:Application[]; filter:string; setFilter:(f:string)=>void; prepare:(id:number)=>void }) {
  return <div className="content"><div className="filter-row">{["all","ready_for_review","submitted","accepted","rejected","stale"].map(value => <button key={value} className={filter===value?"selected":""} onClick={()=>setFilter(value)}>{display(value)}</button>)}</div><div className="list">{applications.length ? applications.map(app => <ApplicationRow key={app.id} app={app} prepare={prepare}/>) : <Empty title="Nothing in this view" text="Change the filter or add an opportunity to your queue."/>}</div></div>;
}

function ApplicationRow({ app, prepare }: { app:Application; prepare:(id:number)=>void }) {
  return <article className="application-row"><div className="app-icon"><FileText size={18}/></div><div className="grow"><strong>{app.title}</strong><span>{app.organization} · {app.category}</span></div><div className="date"><span>Deadline</span><strong>{formatDate(app.deadline)}</strong></div><span className={`status ${app.outcome !== "pending" ? app.outcome : app.workflow_status}`}>{app.is_stale ? "No reply" : display(app.outcome !== "pending" ? app.outcome : app.workflow_status)}</span>{!["submitted","archived"].includes(app.workflow_status) && <button className="icon-btn" title="Prepare application" onClick={()=>prepare(app.id)}><ChevronRight size={18}/></button>}</article>;
}

function Profile({ facts, run }: { facts:Fact[]; run:(a:()=>Promise<unknown>,m:string)=>void }) {
  const [form, setForm] = useState({section:"Personal",label:"",value:""});
  const sections = Array.from(new Set(facts.map(f => f.section)));
  const add = () => { if (!form.label || !form.value) return; run(() => api("/profile", {method:"PUT", body:JSON.stringify({...form,verified:true})}), "Verified fact added"); setForm({section:"Personal",label:"",value:""}); };
  return <div className="content"><section className="profile-intro"><div><p className="eyebrow">Verified information only</p><h2>Your reusable facts</h2><span>Applications use confirmed details and pause when something is missing.</span></div><label className="upload"><FileText size={17}/> Import CV<input type="file" onChange={(e)=>{const file=e.target.files?.[0]; if(!file)return; const data=new FormData(); data.append("file",file); run(()=>fetch("/api/profile/import",{method:"POST",body:data}),"Document stored locally");}}/></label></section><div className="profile-grid"><div>{sections.map(section => <section className="fact-section" key={section}><h3>{section}</h3>{facts.filter(f=>f.section===section).map(f=><div className="fact" key={f.id}><div><strong>{f.label}</strong><span>{f.value}</span></div>{f.verified ? <CheckCircle2 size={17}/> : <CircleAlert size={17}/>}</div>)}</section>)}</div><aside className="add-panel"><h3>Add verified fact</h3><select value={form.section} onChange={e=>setForm({...form,section:e.target.value})}><option>Personal</option><option>Education</option><option>Experience</option><option>Projects</option><option>Eligibility</option><option>Preferences</option></select><input placeholder="Label" value={form.label} onChange={e=>setForm({...form,label:e.target.value})}/><textarea placeholder="Value" value={form.value} onChange={e=>setForm({...form,value:e.target.value})}/><button className="primary" onClick={add}><Plus size={16}/> Add fact</button></aside></div></div>;
}

function InboxView({ matches, sync, confirm }: { matches:EmailMatch[]; sync:()=>void; confirm:(id:number)=>void }) {
  return <div className="content"><div className="toolbar"><div><p className="eyebrow">Read-only inbox access</p><span className="muted">Messages are never sent, deleted, archived, or marked as read.</span></div><button className="secondary" onClick={sync}><RefreshCw size={16}/> Sync inboxes</button></div><div className="list">{matches.length ? matches.map(match => <article className="email-row" key={match.id}><Mail size={19}/><div className="grow"><strong>{match.subject}</strong><span>{match.sender}</span><p>{match.excerpt}</p></div><div className="email-side"><span className={`status ${match.classification}`}>{display(match.classification)}</span><small>{Math.round(match.confidence*100)}% confidence</small>{match.review_status==="pending" && match.application_title && <button className="secondary small" onClick={()=>confirm(match.id)}>Confirm match</button>}</div></article>) : <Empty title="No matched email yet" text="Sync Gmail and Microsoft inbox adapters to reconcile application replies."/>}</div></div>;
}

function SettingsView() {
  return <div className="content settings-grid"><section><h2>Inbox providers</h2><SettingRow title="Gmail" text="Read-only OAuth adapter" action="Configure"/><SettingRow title="Microsoft" text="Read-only Graph adapter" action="Configure"/></section><section><h2>Automation guardrails</h2><SettingRow title="Approval required" text="Every external submission needs your confirmation" action="Always on"/><SettingRow title="No-reply reminder" text="Flag pending applications after 14 days" action="14 days"/></section><section><h2>Browser workspace</h2><SettingRow title="Persistent browser profile" text="Reuse your local authenticated sessions" action="Local"/></section></div>;
}
function SettingRow({title,text,action}:{title:string;text:string;action:string}) { return <div className="setting-row"><div><strong>{title}</strong><span>{text}</span></div><button>{action}</button></div>; }
function SectionHead({title,action,onClick}:{title:string;action:string;onClick:()=>void}) { return <div className="section-head"><h2>{title}</h2><button onClick={onClick}>{action}<ChevronRight size={16}/></button></div>; }
function EmptyLoading(){ return <div className="content"><Empty title="Loading your application desk" text="Pulling together your local workspace."/></div>; }
function Empty({title,text}:{title:string;text:string}) { return <div className="empty"><Archive size={24}/><strong>{title}</strong><span>{text}</span></div>; }

createRoot(document.getElementById("root")!).render(<React.StrictMode><App/></React.StrictMode>);
