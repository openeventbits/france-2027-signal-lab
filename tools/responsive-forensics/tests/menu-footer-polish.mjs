// node menu-footer-polish.mjs ROOT OUT [--baseline] [--skip-census]
// FR27_PLAYWRIGHT_MODULE and FR27_CHROMIUM support a bundled browser runtime.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.FR27_PLAYWRIGHT_MODULE || 'playwright');
const root=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]);
assert(!out.startsWith(root+path.sep),'Artifacts must be outside the repository');
fs.mkdirSync(out,{recursive:true});
const baseline=process.argv.includes('--baseline'),skipCensus=process.argv.includes('--skip-census');
const compareIndex=process.argv.indexOf('--compare');
const before=compareIndex<0?null:JSON.parse(fs.readFileSync(process.argv[compareIndex+1],'utf8'));
const routes=JSON.parse(fs.readFileSync(path.join(root,'route_registry.json'),'utf8')).routes.filter(r=>r.source_file.endsWith('.html'));
const mime={'.html':'text/html','.css':'text/css','.js':'text/javascript','.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2'};
const server=http.createServer((req,res)=>{
 let file=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
 if(file!==root&&!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 if(fs.existsSync(file)&&fs.statSync(file).isDirectory())file=path.join(file,'index.html');
 if(!fs.existsSync(file)){res.writeHead(404).end();return;}
 // Optional equivalent data for the pre-Phase-2A comparison.
 if(process.env.FR27_DATA_ROOT&&path.extname(file)==='.json')file=path.join(process.env.FR27_DATA_ROOT,path.relative(root,file));
 res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store'});fs.createReadStream(file).pipe(res);
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,...(process.env.FR27_CHROMIUM?{executablePath:process.env.FR27_CHROMIUM}:{})});
const report={baseline,registeredRouteCount:routes.length,interactions:[],geometry:[],loading:[],census:[],failures:[]};
const check=(ok,message,where)=>{if(!baseline&&!ok)report.failures.push({where,message});};
const save=()=>fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(report,null,2));
async function context(width,options={}){
 const c=await browser.newContext({viewport:{width,height:1100},reducedMotion:'reduce',...options});
 await c.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());return c;
}
async function geometry(page){return page.evaluate(()=>{
 const rect=e=>{if(!e)return null;const r=e.getBoundingClientRect();return {top:r.top+scrollY,bottom:r.bottom+scrollY,height:r.height,width:r.width,left:r.left};};
 const visible=e=>{const r=e.getBoundingClientRect();if(!r.height)return false;let t=r.top,b=r.bottom;for(let a=e.parentElement;a;a=a.parentElement)if(/hidden|auto|scroll|clip/.test(getComputedStyle(a).overflowY)){const ar=a.getBoundingClientRect();t=Math.max(t,ar.top);b=Math.min(b,ar.bottom);}return b-t>=r.height-1;};
 const panels=['.what-changed','.race-glance','.top-media-pulse'].map(selector=>{const e=document.querySelector(selector);return {selector,panel:rect(e),cta:rect(e.querySelector('.race-footer,.top-media-tab-panel:not([hidden])>.top-media-panel-link')),status:rect(e.querySelector('.dashboard-refresh-status')),content:rect(e.querySelector('#what-changed-list,.race-scroll-shell,#top-media-pulse-content'))};});
 const rows=[...document.querySelectorAll('#top-media-overview-panel .top-media-shift-row')],list=document.querySelector('#top-media-overview-panel .top-media-shift-list');
 const model=window.hybridDashboard?.buildMediaViewModel();
 return {panels,model:model?.candidateCoverageLeaders?.length ?? JSON.parse(document.getElementById('published-media-snapshot').textContent).candidateCoverageLeaders.length,dom:rows.length,visible:rows.filter(visible).length,rows:rows.map(e=>({text:e.textContent.trim().replace(/\s+/g,' '),rect:rect(e),visible:visible(e),display:getComputedStyle(e).display})),list:{height:list.clientHeight,scrollHeight:list.scrollHeight,overflow:getComputedStyle(list).overflowY},mediaHeight:document.getElementById('top-media-pulse-content').getBoundingClientRect().height,overflow:document.documentElement.scrollWidth-innerWidth};
 });}
async function launcher(page){return page.evaluate(()=>{
 const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};};
 const t=document.querySelector('.fr27-section-launcher-trigger'),s=getComputedStyle(t),caret=getComputedStyle(t.querySelector('.fr27-section-caret'));
 return {trigger:rect(t),masthead:rect(t.closest('header')),adjacent:[...t.closest('header').querySelectorAll('.lang-switch,.language-switch,.candidate-language-switch,.masthead-countdown,.candidate-countdown')].map(rect),border:s.borderColor,background:s.backgroundColor,shadow:s.boxShadow,outline:s.outline,caretColor:caret.color,caretStroke:caret.borderRightWidth,caretRotation:caret.transform,expanded:t.getAttribute('aria-expanded'),columns:getComputedStyle(document.getElementById('fr27-section-menu')).gridTemplateColumns,overflow:document.documentElement.scrollWidth-innerWidth};
 });}
const hudState=page=>page.locator('.fr27-app-hud').getAttribute('data-expanded');
async function clearPopup(page){await page.mouse.move(0,0);await page.evaluate(()=>{document.activeElement.blur();window.FR27UI?.hideTooltip();});}
async function expand(page){await clearPopup(page);if(await hudState(page)!=='true')await page.locator('#fr27-app-hud-toggle').evaluate(e=>e.click());await clearPopup(page);}
async function footer(page){
 await expand(page);await page.evaluate(()=>window.scrollTo(0,document.documentElement.scrollHeight));
 const expanded=await page.evaluate(()=>{const hud=document.querySelector('.fr27-app-hud'),shell=hud.closest('main,.shell'),r=hud.getBoundingClientRect();const children=[...shell.children].filter(e=>e!==hud&&e.getBoundingClientRect().height&&getComputedStyle(e).position!=='fixed');const last=children.at(-1).getBoundingClientRect();return {height:r.height,top:r.top,bottom:r.bottom,reserve:getComputedStyle(shell).paddingBottom,lastBottom:last.bottom,gap:r.top-last.bottom,overflow:document.documentElement.scrollWidth-innerWidth};});
 await page.keyboard.press('Escape');const collapsed=await page.evaluate(()=>{const r=document.querySelector('.fr27-app-hud').getBoundingClientRect();return {height:r.height,top:r.top,visibleRail:innerHeight-r.top,reserve:getComputedStyle(document.querySelector('.fr27-app-hud').closest('main,.shell')).paddingBottom};});
 await expand(page);return {expanded,collapsed};
}
const templateKinds=[['core','home'],['candidates','hub'],['candidates','candidate-detail'],['polls','hub'],['polls','poll-wave'],['issues','hub'],['issues','issue-detail'],['issues','issue-history-detail'],['agenda','hub'],['agenda','agenda-detail'],['agenda','agenda-history-detail']];
async function interactions(route,width){
 const c=await context(width,{hasTouch:width<680}),p=await c.newPage(),where=`${route.path}@${width}`;
 try{
 await p.goto(base+route.path,{waitUntil:'networkidle'});await p.evaluate(()=>document.fonts.ready);
 const trigger=p.locator('.fr27-section-launcher-trigger'),item={path:route.path,language:route.language,width};
 await clearPopup(p);item.closed=await launcher(p);await p.screenshot({path:path.join(out,`${route.route_id.replace(/[^\w-]/g,'-')}-${width}-closed.png`)});
 await trigger.hover();await p.waitForTimeout(80);item.hover=await launcher(p);await p.mouse.move(0,0);await p.keyboard.press('Tab');await trigger.focus();await p.waitForTimeout(80);item.focus=await launcher(p);
 await p.screenshot({path:path.join(out,`${route.route_id.replace(/[^\w-]/g,'-')}-${width}-focus.png`)});
 await expand(p);await trigger.click();await p.waitForTimeout(80);item.open=await launcher(p);
 item.firstLinkFocused=await p.locator('#fr27-section-menu a').first().evaluate(e=>e===document.activeElement);
 await p.screenshot({path:path.join(out,`${route.route_id.replace(/[^\w-]/g,'-')}-${width}-open.png`)});
 await p.keyboard.press('Tab');item.tabInMenu=await p.evaluate(()=>document.activeElement.closest('#fr27-section-menu')!==null);
 await p.keyboard.press('Shift+Tab');item.shiftTabReturns=await p.locator('#fr27-section-menu a').first().evaluate(e=>e===document.activeElement);
 await p.keyboard.press('Escape');item.launcherEscape={expanded:await hudState(p),closed:await trigger.getAttribute('aria-expanded')==='false',focus:await trigger.evaluate(e=>document.activeElement===e)};
 await trigger.click();await p.mouse.click(width-2,2);item.outsideClosed=await trigger.getAttribute('aria-expanded')==='false';
 await expand(p);await p.keyboard.press('Escape');item.noPopupEscape=await hudState(p);
 await expand(p);const tip=p.locator('[data-fr27-tooltip]:not([aria-expanded="true"]):not(#fr27-app-hud-toggle)').filter({visible:true}).first();
 await tip.focus();await p.waitForTimeout(200);item.tooltipOpened=await p.locator('#fr27-shared-tooltip').getAttribute('aria-hidden')==='false';
 await p.keyboard.press('Escape');item.tooltipEscape={hidden:await p.locator('#fr27-shared-tooltip').getAttribute('aria-hidden')==='true',hud:await hudState(p),focus:await tip.evaluate(e=>e===document.activeElement)};
 await p.keyboard.press('Escape');item.secondEscape=await hudState(p);
 const note=p.locator('.issue-note-tooltip-trigger,.agenda-note-tooltip-trigger').first();
 if(await note.count()){
  await expand(p);await note.focus();await p.waitForTimeout(180);
  item.noteOpened=await note.evaluate(e=>getComputedStyle(e.parentElement.querySelector('[role=tooltip]')).visibility==='visible');
  await p.keyboard.press('Escape');item.noteEscape=await note.evaluate(e=>({hidden:getComputedStyle(e.parentElement.querySelector('[role=tooltip]')).visibility==='hidden',focus:document.activeElement===e}));item.noteEscape.hud=await hudState(p);
  await p.keyboard.press('Escape');item.noteSecondEscape=await hudState(p);
  await note.blur();await note.focus();item.noteReopened=await note.evaluate(e=>getComputedStyle(e.parentElement.querySelector('[role=tooltip]')).visibility==='visible');
 }
 if(width<680){await expand(p);await trigger.tap();item.touchOpen=await trigger.getAttribute('aria-expanded');await trigger.tap();item.touchClose={expanded:await trigger.getAttribute('aria-expanded'),hud:await hudState(p)};}
 item.footer=await footer(p);
 const previous=before?.interactions.find(x=>x.path===route.path&&x.width===width);
 if(previous){
  check(JSON.stringify(item.closed.trigger)===JSON.stringify(previous.closed.trigger),'before/after launcher geometry unchanged',where);
  check(JSON.stringify(item.closed.masthead)===JSON.stringify(previous.closed.masthead),'before/after masthead geometry unchanged',where);
  check(JSON.stringify(item.closed.adjacent)===JSON.stringify(previous.closed.adjacent),'adjacent controls unchanged',where);
  for(const state of ['expanded','collapsed'])for(const key of ['height','reserve','visibleRail'])if(key in item.footer[state])check(item.footer[state][key]===previous.footer[state][key],'footer height/reserve/rail unchanged',where);
  check(Math.abs(item.footer.expanded.gap-previous.footer.expanded.gap)<=1,'footer final content gap unchanged',where);
  check(item.footer.expanded.gap>=-1,'final content reachable above dock',where);
 }
 for(const state of ['hover','focus','open'])check(item[state].trigger.width===item.closed.trigger.width&&item[state].trigger.height===item.closed.trigger.height,'trigger dimensions invariant',where);
 check(item.closed.trigger.width===(width<680?48:52)&&item.closed.trigger.height===(width<680?48:52),'host dimensions retained',where);
 check(item.closed.background!==item.open.background&&item.closed.border!==item.open.border,'distinct open state',where);
 if(width>=680)check(item.closed.background!==item.hover.background,'pointer hover distinct',where);
 check(item.focus.outline.includes('2px'),'keyboard focus obvious',where);
 check(item.open.caretRotation!==item.closed.caretRotation,'caret communicates open',where);
 check(item.firstLinkFocused&&item.tabInMenu&&item.shiftTabReturns,'predictable Tab order',where);
 check(item.launcherEscape.closed&&item.launcherEscape.expanded==='true'&&item.launcherEscape.focus,'launcher Escape isolation and focus',where);
 check(item.outsideClosed,'outside click closes',where);check(item.noPopupEscape==='false','ordinary HUD Escape',where);
 check(item.tooltipOpened&&item.tooltipEscape.hidden&&item.tooltipEscape.hud==='true'&&item.tooltipEscape.focus,'tooltip Escape isolation and focus',where);
 check(item.secondEscape==='false','second Escape reaches HUD',where);
 if(item.noteEscape)check(item.noteOpened&&item.noteEscape.hidden&&item.noteEscape.hud==='true'&&item.noteEscape.focus&&item.noteSecondEscape==='false'&&item.noteReopened,'custom note Escape, focus, second Escape and reopening',where);
 if(width<680){check(item.open.columns.split(' ').length===2,'mobile two columns',where);check(item.touchOpen==='true'&&item.touchClose.expanded==='false'&&item.touchClose.hud==='true','touch open/close preserves HUD',where);}
 check([item.closed,item.open].every(x=>x.overflow<=1),'no overflow',where);
 report.interactions.push(item);save();
 }catch(e){report.failures.push({where,message:e.message});save();}finally{await c.close();}
}
async function topRow(lang,width){
 const c=await context(width),p=await c.newPage(),where=`top-row ${lang}@${width}`;
 try{
 await p.goto(base+(lang==='fr'?'/':'/en/'),{waitUntil:'networkidle'});const normal=await geometry(p),states={empty:normal};
 const leaders=await p.evaluate(()=>window.hybridDashboard.buildMediaViewModel().candidateCoverageLeaders);
 const snapshot=await p.locator('#published-media-snapshot').textContent();check(JSON.stringify(JSON.parse(snapshot).candidateCoverageLeaders)===JSON.stringify(leaders),'generated runtime model leader parity',where);
 for(const name of ['empty','loading','stale']){
  await p.evaluate(name=>{for(const id of ['top-media-pulse-status','what-changed-status'])document.getElementById(id).textContent=name==='empty'?'':window.FR27_LOCALES[document.documentElement.lang][name==='loading'?'loading_status.updating':'loading_status.stale'];},name);
  states[name]=await geometry(p);await p.locator('.top-media-pulse').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(out,`${lang}-${width}-status-${name}.png`)});
  check(Math.abs(states[name].mediaHeight-normal.mediaHeight)<=1,'status cannot change Media content height',where);
  check(Math.abs(states[name].panels[2].cta.bottom-normal.panels[2].cta.bottom)<=1,'status cannot move CTA',where);
 }
 check(states.empty.panels[2].status.height===0,'empty status zero height',where);
 check(normal.dom===normal.model&&normal.model===6,'six model/DOM leaders',where);
 if(width>=1024){const bottoms=normal.panels.map(x=>x.panel.bottom),ctas=normal.panels.filter(x=>x.cta).map(x=>x.cta.bottom);check(Math.max(...bottoms)-Math.min(...bottoms)<=1,'outer panels align',where);check(Math.max(...ctas)-Math.min(...ctas)<=1,'CTA bottoms align',where);check(normal.visible>=4,'at least four complete desktop leaders',where);check(normal.rows.every(x=>x.display!=='none'),'all six leaders participate in scroll',where);}
 await p.locator('#top-media-overview-panel .top-media-shift-list').evaluate(e=>e.scrollTop=e.scrollHeight);
 const scrolled=await geometry(p);if(width>=1024)check(scrolled.rows.at(-1).visible,'last candidate scroll reachable',where);
 await p.screenshot({path:path.join(out,`${lang}-${width}-last-candidates.png`)});
 report.geometry.push({lang,width,states,scrolled});save();
 }catch(e){report.failures.push({where,message:e.message});save();}finally{await c.close();}
}
async function loading(lang,width,spec){
 const c=await context(width),p=await c.newPage(),where=`loading ${spec.name} ${lang}@${width}`;let release;const gate=new Promise(r=>release=r);
 await c.route('**/*.json',async r=>{const name=path.basename(new URL(r.request().url()).pathname),action=spec[name];if(action==='delay')await gate;if(action==='fail')return r.fulfill({status:503,contentType:'application/json',body:'{}'});return r.continue();});
 try{
 await p.goto(base+(lang==='fr'?'/':'/en/'),{waitUntil:'domcontentloaded'});
 const boot=await geometry(p);await p.waitForTimeout(500);const pending=await geometry(p);release();await p.waitForTimeout(700);const ready=await geometry(p);
 const delta=Math.max(boot.mediaHeight,pending.mediaHeight,ready.mediaHeight)-Math.min(boot.mediaHeight,pending.mediaHeight,ready.mediaHeight);
 check(delta<=1,'bootstrap/pending/ready Media height stability',where);
 check(ready.dom===6&&pending.dom===6,'loading/failure never discards leaders',where);
 check(ready.overflow<=1&&pending.overflow<=1,'loading no horizontal overflow',where);
 report.loading.push({lang,width,case:spec.name,boot,pending,ready,delta,status:await p.locator('#top-media-pulse-status').textContent(),ledgerStatus:await p.locator('#what-changed-status').textContent()});save();
 }catch(e){report.failures.push({where,message:e.message});save();}finally{release();await c.close();}
}
async function census(width){
 const queue=[...routes];await Promise.all(Array.from({length:4},async()=>{
 const c=await context(width,{javaScriptEnabled:false}),p=await c.newPage();
 try{while(queue.length){const route=queue.shift();await p.goto(base+route.path,{waitUntil:'load'});const data=await p.evaluate(()=>{const t=document.querySelector('.fr27-section-launcher-trigger'),m=document.getElementById('fr27-section-menu');const r=t?.getBoundingClientRect();return {present:!!t,visible:!!r?.width&&!!r?.height,overflow:document.documentElement.scrollWidth-innerWidth,labels:[...m.querySelectorAll('.fr27-section-label')].map(e=>e.textContent),hrefs:[...m.querySelectorAll('a')].map(e=>e.getAttribute('href'))};});
  const en=route.language==='en',labels=en?['CANDIDATES','POLLS','ISSUES','AGENDA']:['CANDIDATS','SONDAGES','ENJEUX','AGENDA'],hrefs=en?['/en/candidates/','/en/sondages/','/en/issues/','/en/agenda/']:['/candidates/','/sondages/','/enjeux/','/agenda/'];
  await p.locator('#fr27-section-menu').evaluate(e=>e.hidden=false);const cols=await p.locator('#fr27-section-menu').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length);const openOverflow=await p.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
  const bad=JSON.stringify(labels)!==JSON.stringify(data.labels)||JSON.stringify(hrefs)!==JSON.stringify(data.hrefs)||cols!==2;
  check(data.visible&&!bad&&data.overflow<=1&&openOverflow<=1,'route launcher census',`${route.path}@${width}`);report.census.push({path:route.path,width,...data,cols,openOverflow,bad});
 }}finally{await c.close();}
 }));save();
}
try{
 const queue=[];for(const lang of ['fr','en'])for(const [family,kind] of templateKinds)for(const width of [1440,390,358])queue.push({route:routes.find(r=>r.language===lang&&r.family===family&&r.kind===kind),width});
 await Promise.all(Array.from({length:3},async()=>{while(queue.length){const job=queue.shift();await interactions(job.route,job.width);}}));
 console.log('Representative interactions',report.interactions.length,'failures',report.failures.length);
 for(const lang of ['fr','en'])for(const width of [1440,1600,1920,390,358])await topRow(lang,width);
 if(!baseline){const jobs=[];for(const lang of ['fr','en'])for(const width of [1440,390,358])for(const spec of [{name:'pending','news_wire.json':'delay','recent_changes.json':'delay','candidate_signals.json':'delay'},{name:'news-delayed','news_wire.json':'delay'},{name:'recent-delayed','recent_changes.json':'delay'},{name:'news-failed','news_wire.json':'fail'},{name:'recent-failed','recent_changes.json':'fail'},{name:'candidates-failed','candidate_signals.json':'fail'}])jobs.push({lang,width,spec});await Promise.all(Array.from({length:3},async()=>{while(jobs.length){const j=jobs.shift();await loading(j.lang,j.width,j.spec);}}));}
 if(!skipCensus)for(const width of [390,358])await census(width);
}finally{save();await browser.close();await new Promise(r=>server.close(r));}
console.log(JSON.stringify({interactions:report.interactions.length,geometry:report.geometry.length,loading:report.loading.length,census:report.census.length,failures:report.failures},null,2));
if(report.failures.length&&!baseline)process.exitCode=1;
