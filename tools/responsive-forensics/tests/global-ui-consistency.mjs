// node global-ui-consistency.mjs ROOT OUT [warm|matrix|area] [--baseline]
// FR27_PLAYWRIGHT_MODULE / FR27_CHROMIUM may select an installed browser runtime.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.FR27_PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]);
fs.mkdirSync(out,{recursive:true});
// Modes: warm (retained dashboard transitions) and matrix (control census).
const mode=process.argv[4]||'warm';
assert(!out.startsWith(root+path.sep), 'Artifacts must remain outside the repository');
const server=http.createServer((req,res)=>{let f=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));if(!f.startsWith(root+path.sep)&&f!==root)return res.writeHead(403).end();if(fs.existsSync(f)&&fs.statSync(f).isDirectory())f=path.join(f,'index.html');if(!fs.existsSync(f))return res.writeHead(404).end();const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.woff2':'font/woff2'};res.writeHead(200,{'Content-Type':types[path.extname(f)]||'application/octet-stream'});fs.createReadStream(f).pipe(res);});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,...(process.env.FR27_CHROMIUM?{executablePath:process.env.FR27_CHROMIUM}:{})});
const report={mode,warm:[],matrix:[],failures:[]};
const save=()=>fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(report,null,2));
async function sample(page){return page.evaluate(()=>({lang:document.documentElement.lang,locale:FR27I18N.locale,hash:location.hash,path:location.pathname,entries:document.querySelectorAll('.changes-ledger-entry').length,filters:document.querySelectorAll('[data-ledger-filter]').length,filter:document.querySelector('[data-ledger-filter][aria-pressed="true"]')?.dataset.ledgerFilter,metrics:[...document.querySelectorAll('[id^="fr27-hud-"][id$="-value"]')].map(e=>[e.id,e.textContent.trim()]),skeleton:!!document.querySelector('#what-changed-list .fr27-skeleton-region, .hybrid-panel:not([hidden]) .fr27-skeleton-region'),selected:document.querySelector('[data-candidate-signals-candidate][aria-pressed="true"]')?.dataset.candidateSignalsCandidate,overflow:document.documentElement.scrollWidth-innerWidth}));}
try{
if(mode==='area') {
 for(const lang of ['fr','en'])for(const width of [1440,1024,390,358]){
  const c=await browser.newContext({viewport:{width,height:width<400?1600:1000},reducedMotion:'reduce'}),p=await c.newPage();
  await c.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());
  await p.goto(base+(lang==='fr'?'/':'/en/'),{waitUntil:'networkidle'});
  const area=await p.evaluate(()=>{
   const board=document.getElementById('hybrid-signal-board');let previous=board.previousElementSibling;
   while(previous && !previous.getBoundingClientRect().height)previous=previous.previousElementSibling;
   return {gap:board.getBoundingClientRect().top-previous.getBoundingClientRect().bottom,previous:previous.className,
    nav:document.querySelectorAll('.dashboard-family-navigation,[data-dashboard-hub]').length,overflow:document.documentElement.scrollWidth-innerWidth};
  });
  assert.equal(area.nav,0);assert.equal(area.overflow,0);assert(area.gap>=0&&area.gap<=24,'No residual navigation gap');
  await p.evaluate(()=>window.scrollTo(0,Math.max(0,document.querySelector('.context-strip').getBoundingClientRect().top+scrollY-100)));
  await p.screenshot({path:path.join(out,`dashboard-area-${lang}-${width}.png`)});report.matrix.push({lang,width,...area});save();await c.close();
 }
}
else if(mode==='warm')for(const lang of ['fr','en'])for(const width of [1440,1024,390,358])for(const delayed of [false,true]){
const c=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'}),p=await c.newPage(),errors=[],requests=[];
await c.route('**/*',async r=>{if(new URL(r.request().url()).origin!==base)return r.abort();if(delayed&&/candidate_attention|runoff_archive/.test(r.request().url()))await new Promise(resolve=>setTimeout(resolve,2500));await r.continue();});
p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.url().endsWith('.json'))requests.push(r.url());});
await p.goto(base+(lang==='fr'?'/':'/en/')+'?probe=1#signal-candidates',{waitUntil:'domcontentloaded'});
await p.waitForFunction(()=>document.querySelectorAll('[data-ledger-filter]').length===5&&!document.querySelector('.hybrid-panel:not([hidden]) .fr27-skeleton-region')&&[...document.querySelectorAll('[id^="fr27-hud-"][id$="-value"]')].every(e=>/\d/.test(e.textContent)),{timeout:20000});
await p.locator('[data-ledger-filter=campaign]').click();
await p.evaluate(()=>{window.__documentIdentity={};window.__warmTrace=[];new MutationObserver(()=>{window.__warmTrace.push({entries:document.querySelectorAll('.changes-ledger-entry').length,filters:document.querySelectorAll('[data-ledger-filter]').length,metrics:[...document.querySelectorAll('[id^="fr27-hud-"][id$="-value"]')].map(e=>e.textContent.trim()),skeleton:!!document.querySelector('#what-changed-list .fr27-skeleton-region,.hybrid-panel:not([hidden]) .fr27-skeleton-region'),lang:document.documentElement.lang});}).observe(document.body,{childList:true,subtree:true});});
const initial=await sample(p),initialRequests=requests.length;
const other=lang==='fr'?'en':'fr';
await p.locator(`[data-fr27-language="${other}"]`).click();await p.waitForTimeout(180);const alternate=await sample(p);alternate.allLabel=await p.locator('[data-ledger-filter=all]').textContent();alternate.workspaceLabel=await p.locator('[data-hybrid-view=candidates] .hybrid-tab-label').textContent();
await p.locator(`[data-fr27-language="${lang}"]`).click();await p.waitForTimeout(180);const returned=await sample(p);
await p.evaluate(([other,lang])=>{document.querySelector(`[data-fr27-language="${other}"]`).click();document.querySelector(`[data-fr27-language="${lang}"]`).click();},[other,lang]);await p.waitForTimeout(2800);
const final=await sample(p),trace=await p.evaluate(()=>window.__warmTrace),item={lang,width,delayed,initial,alternate,returned,final,trace,errors,requestDelta:requests.length-initialRequests};
try{assert.equal(alternate.lang,other);assert.equal(alternate.allLabel,`${other==='fr'?'TOUT':'ALL'} ${await p.evaluate(()=>dashboardState.recentChanges.items.length)}`);assert.equal(alternate.workspaceLabel,other==='fr'?'CANDIDATS':'CANDIDATES');assert.equal(alternate.locale,other);assert.equal(final.lang,lang);assert.equal(final.path,lang==='fr'?'/':'/en/');assert.equal(final.hash,initial.hash);assert.equal(final.filter,initial.filter);assert.equal(final.selected,initial.selected);assert.equal(item.requestDelta,0);assert.equal(errors.length,0);for(const s of [alternate,returned,final]){assert.equal(s.entries,initial.entries);assert.equal(s.filters,initial.filters);assert.deepEqual(s.metrics,initial.metrics);assert(!s.skeleton);assert.equal(s.overflow,0);}for(const s of trace){assert.equal(s.entries,initial.entries);assert.equal(s.filters,initial.filters);assert(!s.skeleton);assert.deepEqual(s.metrics,initial.metrics.map(x=>x[1]));}assert(await p.evaluate(()=>!!window.__documentIdentity));}catch(e){report.failures.push({lang,width,delayed,error:e.message});}
// All already-hydrated workspaces share retained view/selection ownership.
item.workspaces=[];
for(const view of ['candidates','issues','agenda','events','runoff']){
 await p.evaluate(view=>{location.hash=`#signal-${view}`;},view);
 await p.waitForTimeout(100);
 await p.waitForFunction(()=>!document.querySelector('.hybrid-panel:not([hidden]) .fr27-skeleton-region'));
 const prior=await sample(p);
 await p.evaluate(([other,lang])=>{document.querySelector(`[data-fr27-language="${other}"]`).click();document.querySelector(`[data-fr27-language="${lang}"]`).click();},[other,lang]);
 await p.waitForTimeout(100);const next=await sample(p);
 assert.equal(next.hash,prior.hash);assert.equal(next.selected,prior.selected);assert.equal(next.filter,prior.filter);assert(!next.skeleton);assert.equal(next.entries,prior.entries);assert.deepEqual(next.metrics,prior.metrics);
 item.workspaces.push({view,prior,next});
}
await p.evaluate(()=>{location.hash='#signal-candidates';});await p.waitForTimeout(100);
await p.evaluate(()=>window.scrollTo(0,document.querySelector('.context-strip').getBoundingClientRect().top+scrollY-100));await p.screenshot({path:path.join(out,`dashboard-${lang}-${width}.png`)});
report.warm.push(item);save();console.log('warm',lang,width,delayed,report.failures.length);await c.close();
}
else {
const registry=JSON.parse(fs.readFileSync(path.join(root,'route_registry.json'),'utf8')).routes;
for(const lang of ['fr','en']){let routes=[{kind:'dashboard',path:lang==='fr'?'/':'/en/'}];for(const family of ['candidates','polls','issues','agenda']){routes.push({kind:`${family}-hub`,path:lang==='en'?(family==='polls'?'/en/sondages/':`/en/${family}/`):({candidates:'/candidates/',polls:'/sondages/',issues:'/enjeux/',agenda:'/agenda/'})[family]});const details=registry.filter(r=>r.language===lang&&r.family===family&&(family!=='candidates'||r.entity_id==='marine-le-pen')&&(r.kind===`${family.slice(0,-1)}-detail`||r.kind===`${family}-detail`||r.kind==='poll-wave'));routes.push(...details.slice(0,family==='polls'?2:1));}
for(const width of [1440,1024,390,358])for(const route of routes){const c=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'}),p=await c.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));await c.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());await p.goto(base+route.path,{waitUntil:'networkidle'});
const census=await p.evaluate(()=>{const visible=e=>!!e.getBoundingClientRect().height&&getComputedStyle(e).visibility!=='hidden';const controls=[...document.querySelectorAll('button,select,input,summary,a,.poll-detail-scenario-toggle,.poll-detail-side-summary-action,.poll-detail-related-open,.candidate-related-open,.issue-card-open,.agenda-card-open')].filter(visible).map(e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();const classes=e.className;const tier=/source-cta|history-gateway-cta|history-detail-cta|hub-open|card-open|inspector-open/.test(classes)?'TIER_1_PRIMARY':/related-open|scenario-toggle|summary-action/.test(classes)?'TIER_2_COMPACT':/info|tooltip|hud-|launcher/.test(classes)?'SPECIAL_CASE':e.matches('button,select,input')?'TIER_3_UTILITY':e.matches('summary')?'SPECIAL_CASE':'NOT_A_CONTROL';return {tag:e.tagName,text:e.textContent.trim().replace(/\s+/g,' ').slice(0,85),classes,tier,fontSize:s.fontSize,fontWeight:s.fontWeight,letterSpacing:s.letterSpacing,lineHeight:s.lineHeight,padding:s.padding,height:r.height,border:s.border,radius:s.borderRadius,whiteSpace:s.whiteSpace,clipped:e.scrollWidth>e.clientWidth+1};});return {controls,overflow:document.documentElement.scrollWidth-innerWidth,nav:document.querySelectorAll('.dashboard-family-navigation,[data-dashboard-hub]').length};});
const interactions=[];
if(mode==='matrix' && !process.argv.includes('--baseline')){
 const compact=p.locator('.poll-detail-scenario-toggle,.poll-detail-side-summary-action,.poll-detail-related-open,.candidate-related-open');
 for(let i=0;i<await compact.count();i++){
  const measurement=await compact.nth(i).evaluate(e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return {font:parseFloat(s.fontSize),line:parseFloat(s.lineHeight),height:r.height,white:s.whiteSpace,clipped:e.scrollWidth>e.clientWidth+1};});
  assert.equal(measurement.font,11.5);assert(measurement.height>=26);assert.equal(measurement.white,'nowrap');assert(!measurement.clipped);interactions.push(measurement);
 }
 const focus=p.locator('.poll-detail-scenario-summary,.candidate-hub-open,.issue-history-gateway-cta,.agenda-history-gateway-cta,.poll-detail-source-cta').first();
 if(await focus.count()){
  await focus.focus();const focused=await focus.evaluate(e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return {outline:s.outlineWidth,style:s.outlineStyle,height:r.height,width:r.width};});assert.equal(focused.outline,'2px');assert.equal(focused.style,'solid');
  await focus.hover();const hover=await focus.evaluate(e=>{const r=e.getBoundingClientRect();return {height:r.height,width:r.width};});assert.equal(hover.height,focused.height);assert.equal(hover.width,focused.width);
 }
 if(await p.locator('.poll-detail-scenario').count()){
  const disclosure=p.locator('.poll-detail-scenario').first();const prior=await disclosure.evaluate(e=>e.open);await disclosure.locator('summary').click();assert.equal(await disclosure.evaluate(e=>e.open),!prior);await disclosure.locator('summary').click();
 }
}
const item={lang,width,route:route.path,kind:route.kind,...census,errors,interactions};if(census.overflow||errors.length||census.nav)report.failures.push({route:route.path,width,overflow:census.overflow,errors,nav:census.nav});
if(width===1440||(width===390&&route.kind==='poll-wave')||(route.kind==='dashboard'&&width<400))await p.screenshot({path:path.join(out,`${lang}-${width}-${route.kind}-${routes.indexOf(route)}.png`),fullPage:true});report.matrix.push(item);save();console.log('matrix',lang,width,route.path,census.overflow);await c.close();}}
}
}finally{save();await browser.close();await new Promise(r=>server.close(r));}
if(report.failures.length)process.exitCode=1;
