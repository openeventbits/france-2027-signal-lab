// node dashboard-navigation.mjs ROOT OUT [BEFORE_RESULTS]
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.FR27_PLAYWRIGHT_MODULE || 'playwright');
const root=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]);
assert(!out.startsWith(root+path.sep),'Artifacts must be outside the repository');
fs.mkdirSync(out,{recursive:true});
const before=process.argv[4]?JSON.parse(fs.readFileSync(process.argv[4],'utf8')):null;
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp'};
const server=http.createServer((req,res)=>{
 let file=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
 if(file!==root&&!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 if(fs.existsSync(file)&&fs.statSync(file).isDirectory())file=path.join(file,'index.html');
 if(!fs.existsSync(file)){res.writeHead(404).end();return;}
 res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'});fs.createReadStream(file).pipe(res);
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,...(process.env.FR27_CHROMIUM?{executablePath:process.env.FR27_CHROMIUM}:{})});
const report={pages:[],graph:{},failures:[]};
const save=()=>fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(report,null,2));
async function context(width){
 const c=await browser.newContext({viewport:{width,height:1100},reducedMotion:'reduce'});
 c.setDefaultTimeout(8000);
 await c.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());return c;
}
async function geometry(p){return p.evaluate(()=>{
 const rect=e=>{const r=e.getBoundingClientRect();return {top:r.top+scrollY,bottom:r.bottom+scrollY,height:r.height,width:r.width};};
 const visible=e=>{const r=e.getBoundingClientRect();let t=r.top,b=r.bottom;for(let a=e.parentElement;a;a=a.parentElement)if(/hidden|auto|scroll|clip/.test(getComputedStyle(a).overflowY)){const ar=a.getBoundingClientRect();t=Math.max(t,ar.top);b=Math.min(b,ar.bottom);}return b-t>=r.height-1;};
 const panels=['.what-changed','.race-glance','.top-media-pulse'].map(s=>{const e=document.querySelector(s);return {panel:rect(e),cta:e.querySelector('.race-footer,.top-media-tab-panel:not([hidden])>.top-media-panel-link')?rect(e.querySelector('.race-footer,.top-media-tab-panel:not([hidden])>.top-media-panel-link')):null};});
 const rows=[...document.querySelectorAll('#top-media-overview-panel .top-media-shift-row')];
 return {panels,mediaHeight:document.getElementById('top-media-pulse-content').getBoundingClientRect().height,dom:rows.length,visible:rows.filter(visible).length,launcher:rect(document.querySelector('.fr27-section-launcher-trigger')),overflow:document.documentElement.scrollWidth-innerWidth};
 });}
async function workspace(p,view,width){
 if(width<1024)await p.locator('[data-tier3-workspace-control] select').selectOption(view);
 else await p.locator(`[data-hybrid-view="${view}"]`).click();
 await p.waitForTimeout(120);
 assert(new URL(p.url()).hash===`#signal-${view}`,'workspace selection remains functional');
}
async function selection(p,family,id,width){
 if(family==='candidates'){
  if(width<1024)await p.locator('[data-tier3-candidate-control] select').selectOption(id);
  else await p.locator(`[data-candidate-signals-candidate="${id}"]`).click();
 }else{
  const attr=family==='issues'?'data-hybrid-policy-issue':'data-hybrid-agenda-topic';
  // Mobile selectors dispatch to these existing owner buttons too.
  await p.locator(`[${attr}="${id}"]`).first().evaluate(e=>e.click());
 }
 await p.waitForTimeout(120);
}
async function follow(p,locator,href,lang){
 const current=p.url();await locator.click();await p.waitForURL(base+href);
 assert.equal(await p.locator('html').getAttribute('lang'),lang);
 assert.equal(new URL(p.url()).pathname,new URL(href,base).pathname);
 if(href.includes('#'))assert(await p.locator(new URL(href,base).hash).evaluate(e=>e.open),'destination scenario opened');
 await p.goBack({waitUntil:'networkidle'});assert.equal(p.url(),current);
 assert(await p.locator('#candidate-signals-root').count(),'dashboard remains functional after Back');
}
async function checkGraph(p,lang,routes){
 const hrefs=new Set(Object.values(routes.hubs).map(r=>r[lang]));
 for(const family of ['candidates','issues','agenda'])for(const route of Object.values(routes[family]))hrefs.add(route[lang]);
 for(const [wave,index] of Object.values(routes.events))hrefs.add(`${routes.waves[wave][lang]}#scenario-${index}`);
 const pages=new Map();let broken=0;
 for(const href of hrefs){const [url,fragment]=href.split('#');let text=pages.get(url);
  if(text===undefined){const response=await p.request.get(base+url);if(!response.ok()){broken++;await response.dispose();continue;}text=await response.text();await response.dispose();pages.set(url,text);}
  if(fragment&&!text.includes(`id="${fragment}"`))broken++;
 }
 report.graph[lang]={links:hrefs.size,pages:pages.size,broken};assert.equal(broken,0);
}
try{
 for(const lang of ['fr','en'])for(const width of [1440,390,358]){
 if(process.env.FR27_CASE && process.env.FR27_CASE!==`${lang}@${width}`)continue;
 const c=await context(width),p=await c.newPage(),where=`${lang}@${width}`,item={lang,width,selections:[],race:[]};
 try{
 await p.goto(base+(lang==='fr'?'/':'/en/'),{waitUntil:'networkidle'});
 const routes=JSON.parse(await p.locator('#published-dashboard-navigation').textContent());
 item.geometry=await geometry(p);assert.equal(item.geometry.overflow,0);
 assert.equal(item.geometry.launcher.width,width>=680?52:48);assert.equal(item.geometry.launcher.height,width>=680?52:48);
 assert.equal(await p.locator('#fr27-section-menu a').count(),4);
 if(width>=1024){
  const panels=item.geometry.panels.map(x=>x.panel);assert(Math.max(...panels.map(x=>x.bottom))-Math.min(...panels.map(x=>x.bottom))<=1);
  assert(Math.abs(item.geometry.panels[1].cta.bottom-item.geometry.panels[2].cta.bottom)<=1);
 }
 assert.equal(item.geometry.dom,6);assert.equal(item.geometry.visible,4);
 if(before){const prior=before.geometry.find(x=>x.lang===lang&&x.width===width).normal;
  assert.equal(item.geometry.mediaHeight,prior.mediaHeight);
  item.geometry.panels.forEach((x,i)=>assert.equal(x.panel.height,prior.panels[i].panel.height));
 }
 if(width===1440)await checkGraph(p,lang,routes);
 await p.screenshot({path:path.join(out,`${lang}-${width}-race.png`)});
 await p.locator('.top-media-pulse [data-top-media-tab="coverage"]').click();
 await p.locator('.top-media-pulse .ecm-open').click();
 item.mediaSources=await p.locator('#election-coverage-modal .ecm-feed-source').evaluateAll(es=>es.map(e=>e.getAttribute('href')));
 assert(item.mediaSources.length>0&&item.mediaSources.every(h=>/^https?:/.test(h)));
 await p.locator('#election-coverage-modal [data-ecm-close]').click();
 await p.locator('.top-media-pulse [data-top-media-tab="overview"]').click();
 for(const family of ['candidates','issues','agenda']){
  await workspace(p,family,width);
  const available=family==='candidates'?await p.locator(width<1024?'[data-tier3-candidate-control] option':'[data-candidate-signals-candidate]').evaluateAll(es=>es.map(e=>e.value||e.dataset.candidateSignalsCandidate)):[];
  const ids=family==='candidates'?[...available.filter(id=>routes.candidates[id]).slice(0,2),...available.filter(id=>!routes.candidates[id]).slice(0,1)]:Object.keys(routes[family]).slice(0,2);
  for(const id of ids){
   await selection(p,family,id,width);
   const link=p.locator(`[data-dashboard-detail="${family}"]`),expected=routes[family][id]?.[lang];
   if(!expected){assert.equal(await link.count(),0);item.selections.push({family,id,absent:true});continue;}
   assert.equal(await link.getAttribute('href'),expected);assert.equal(await link.getAttribute('target'),null);
   assert((await link.getAttribute('aria-label')).length>10);assert.equal(await link.locator('button,a').count(),0);
   await p.keyboard.press('Tab');await link.focus();const focus=await link.evaluate(e=>({width:parseFloat(getComputedStyle(e).outlineWidth),visible:e.matches(':focus-visible'),active:document.activeElement===e}));assert(focus.active&&focus.visible&&focus.width>=2,`visible keyboard focus ${family}/${id}: ${JSON.stringify(focus)}`);
   await p.screenshot({path:path.join(out,`${lang}-${width}-${family}-${id}.png`)});
   await follow(p,link,expected,lang);item.selections.push({family,id,href:expected});
  }
 }
 await workspace(p,'events',width);
 item.eventSources=await p.locator('.hybrid-events-dossier-source').evaluateAll(es=>es.map(e=>e.getAttribute('href')));
 assert(item.eventSources.every(h=>/^https?:/.test(h)));
 item.whatChangedSources=await p.locator('#what-changed-list a').evaluateAll(es=>es.map(e=>e.getAttribute('href')));
 assert(item.whatChangedSources.every(h=>/^https?:/.test(h)));
 const tabs=await p.locator('#race-poll-tabs button').count();
 for(let tab=0;tab<tabs;tab++){
  await p.locator('#race-poll-tabs button').nth(tab).click();
  const tabLabel=await p.locator('#race-poll-tabs button').nth(tab).getAttribute('aria-label');
  const select=p.locator('#hypothesis-select'),count=await select.locator('option').count();
  for(let scenario=0;scenario<count;scenario++){
   if(count>1)await select.selectOption(String(scenario));
   const href=await p.locator('#race-source').getAttribute('href');
   const eventId=await p.evaluate(()=>{const pack=activeRacePollPackage();return pack.events[selectedRaceHypothesisIndex(pack)].event_id;});
   const [wave,index]=routes.events[eventId];assert.equal(href,`${routes.waves[wave][lang]}#scenario-${index}`);
   assert(href.startsWith(lang==='fr'?'/sondages/':'/en/sondages/'));assert(href.includes('#scenario-'));
   assert.equal(await p.locator('#race-source').getAttribute('target'),null);
   const label=await p.locator('#race-source').textContent();assert.equal(label,lang==='fr'?'Voir le sondage →':'View poll →');
   assert(!label.includes('↗'));item.race.push({tab:tabLabel,scenario,eventId,href});
   await follow(p,p.locator('#race-source'),href,lang);
   // Back reloads the dashboard; restore the exact tab for the next scenario.
   await p.locator('#race-poll-tabs button').nth(tab).click();
  }
 }
 item.finalOverflow=await p.evaluate(()=>document.documentElement.scrollWidth-innerWidth);assert.equal(item.finalOverflow,0);
 report.pages.push(item);save();
 }catch(e){report.failures.push({where,message:e.stack});save();}finally{await c.close();}
 }
}finally{save();await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
console.log(JSON.stringify({pages:report.pages.length,graph:report.graph,failures:report.failures},null,2));
if(report.failures.length)process.exitCode=1;
