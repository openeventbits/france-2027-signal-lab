// Run with Node and Playwright. ROOT/OUT arguments keep artifacts outside the repository.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.FR27_PLAYWRIGHT_MODULE || 'playwright');
const root=path.resolve(process.argv[2]), out=path.resolve(process.argv[3]);
assert(!out.startsWith(root+path.sep), 'Browser artifacts must be outside the repository');
fs.mkdirSync(out,{recursive:true});
 const baseline=process.argv.includes('--baseline');
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2'};
const server=http.createServer((req,res)=>{
 let file=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
 if(file!==root&&!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 if(fs.existsSync(file)&&fs.statSync(file).isDirectory())file=path.join(file,'index.html');
 if(!fs.existsSync(file)){res.writeHead(404).end();return;}
 res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store'});fs.createReadStream(file).pipe(res);
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,...(process.env.FR27_CHROMIUM?{executablePath:process.env.FR27_CHROMIUM}:{})});
const cases=baseline?[{name:'normal'},{name:'delay-both',recent:3000,news:3000}]:[
 {name:'normal'},{name:'delay-recent',recent:3000},{name:'delay-news',news:3000},
 {name:'fail-recent',recent:'fail'},{name:'fail-news',news:'fail'},
 {name:'delay-both',recent:3000,news:3000},{name:'cache-disabled'},
 {name:'delay-candidates',candidates:3000},{name:'fail-candidates',candidates:'fail'},
 {name:'invalid-hash',hash:'#invalid'},{name:'direct-reload'},
 {name:'empty-recent',recent:'empty'},{name:'invalid-recent',recent:'invalid'},
 {name:'provenance-mismatch',news:'mismatch'},{name:'workspace-error',workspaceError:true}
];
const results=[],statics=[],failures=[];
async function sample(page){return page.evaluate(()=>{
 const data={t:Math.round(performance.now()),path:location.pathname,search:location.search,hash:location.hash,lang:document.documentElement.lang,overflow:document.documentElement.scrollWidth-innerWidth};
 for(const [key,id] of [['what','what-changed-list'],['media','top-media-pulse-content']]){
  const el=document.getElementById(id), panel=el.closest('article'), r=el.getBoundingClientRect();
  data[key]={text:el.innerText.replace(/\s+/g,' ').slice(0,300),height:r.height,panelHeight:panel.getBoundingClientRect().height,top:r.top+scrollY,busy:el.getAttribute('aria-busy'),snapshot:el.dataset.fr27SemanticSnapshot==='true',state:el.dataset.refreshState||'',entries:el.querySelectorAll('.changes-ledger-entry').length,coverage:el.querySelectorAll('.top-media-coverage-row').length,skeleton:!!el.querySelector('.fr27-skeleton-region'),status:document.getElementById(key==='what'?'what-changed-status':'top-media-pulse-status')?.innerText||''};
 }
 const following=document.getElementById('hybrid-signal-board');data.following=following.getBoundingClientRect().top+scrollY;
 data.mediaMetrics=[...document.querySelectorAll('#top-media-pulse-metrics strong')].map(x=>x.innerText.trim());
 data.duplicateIds=[...document.querySelectorAll('[id]')].map(x=>x.id).filter((id,i,all)=>all.indexOf(id)!==i);
 return data;
});}
const record=()=>fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({statics,results,failures},null,2));
function check(ok,message,item){if(!ok)failures.push({lang:item.lang,width:item.width,case:item.case,message});}
async function run(lang,width,spec){
 const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'}), errors=[],warnings=[],requests=[];
 await context.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.origin!==base){await route.abort();return;}
  const type=url.pathname.endsWith('/recent_changes.json')?'recent':url.pathname.endsWith('/news_wire.json')?'news':url.pathname.endsWith('/candidate_signals.json')?'candidates':null;
  const action=spec[type];
  if(action==='fail'){await route.fulfill({status:503,contentType:'application/json',body:'{}'});return;}
  if(action==='empty'||action==='invalid'||action==='mismatch'){
   const payload=JSON.parse(fs.readFileSync(path.join(root,url.pathname),'utf8'));
   if(action==='empty'){payload.items=[];payload.newest_trusted_change_at=null;payload.oldest_trusted_change_at=null;payload.window.max_items=0;}
   if(action==='invalid')payload.schema_version=999;
   if(action==='mismatch'){payload.sources.pop();payload.feed_coverage.direct_feeds=payload.sources.length;}
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload)});return;
  }
  if(spec.workspaceError&&url.pathname.endsWith('/hybrid-dashboard.js')){
   const source=fs.readFileSync(path.join(root,'assets/hybrid-dashboard.js'),'utf8').replace('renderFocusWorkspace(models);','(() => { throw new Error("Injected unrelated workspace failure"); })();');
   await route.fulfill({status:200,contentType:'text/javascript',body:source});return;
  }
  if(typeof action==='number')await new Promise(r=>setTimeout(r,action));
  await route.continue();
 });
 const page=await context.newPage();
 page.on('request',r=>{if(/(?:recent_changes|news_wire|candidate_signals)\.json/.test(r.url()))requests.push({path:new URL(r.url()).pathname,t:Date.now()});});
 page.on('pageerror',e=>errors.push('UNCAUGHT '+e.message));
 page.on('console',m=>{if(m.type()==='error')errors.push(m.text());if(m.type()==='warning')warnings.push(m.text());});
 await page.addInitScript(()=>{
  window.__bindings=new WeakMap();const original=EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener=function(type,fn,options){const counts=window.__bindings.get(this)||{};counts[type]=(counts[type]||0)+1;window.__bindings.set(this,counts);return original.call(this,type,fn,options);};
  window.__loadingTrace=[];
  new MutationObserver(()=>{for(const id of ['what-changed-list','top-media-pulse-content']){const el=document.getElementById(id);if(!el)continue;const previous=window.__loadingTrace.filter(x=>x.id===id).at(-1);const text=el.textContent.trim().replace(/\s+/g,' ').slice(0,100);const snapshot=el.dataset.fr27SemanticSnapshot||'';if(!previous||previous.text!==text||previous.snapshot!==snapshot)window.__loadingTrace.push({id,text,snapshot,t:performance.now(),height:el.getBoundingClientRect().height,skeleton:!!el.querySelector('.fr27-skeleton-region')});}}).observe(document,{subtree:true,childList:true,attributes:true,attributeFilter:['data-fr27-semantic-snapshot']});
 });
 if(spec.name==='cache-disabled'){const cdp=await context.newCDPSession(page);await cdp.send('Network.enable');await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});}
 const pathname=lang==='fr'?'/':'/en/';
 await page.goto(base+pathname+'?x=1'+(spec.hash||''),{waitUntil:'domcontentloaded'});
 const boot=await sample(page);
 await page.waitForTimeout(1100);
 const pending=await sample(page);
 if(['delay-both','fail-news'].includes(spec.name)&&width!==1440)await page.screenshot({path:path.join(out,`${lang}-${width}-${spec.name}-pending.png`)});
 await page.waitForTimeout((typeof spec.recent==='number'||typeof spec.news==='number'||typeof spec.candidates==='number')?2400:400);
 const final=await sample(page);
 const item={lang,width,case:spec.name,boot,pending,final,requests,errors,warnings};
 if(['cache-disabled','direct-reload','invalid-hash'].includes(spec.name)){await page.reload({waitUntil:'domcontentloaded'});await page.waitForTimeout(650);item.reload=await sample(page);}
 if(!baseline&&spec.name==='normal'){
  item.repeated=await page.evaluate(async()=>{
   const list=document.getElementById('what-changed-list'),media=document.getElementById('top-media-pulse-content');
   const ledgerChild=list.firstElementChild,mediaChild=media.firstElementChild;
   const tab=media.querySelector('[role=tab]');const before=window.__bindings.get(tab);
   const a=loadRecentChanges(),b=loadRecentChanges(),c=loadNewsWire(),d=loadNewsWire();await Promise.all([a,b,c,d]);
   renderWhatChanged();markDataset('polls','loaded',dashboardState.polls);renderWhatChanged();
   document.dispatchEvent(new CustomEvent('hybrid:dataset',{detail:{name:'news'}}));
   document.dispatchEvent(new CustomEvent('hybrid:dataset',{detail:{name:'news'}}));
   const script=document.createElement('script');script.src='/assets/hybrid-dashboard.js';await new Promise((resolve,reject)=>{script.onload=resolve;script.onerror=reject;document.head.append(script);});
   return {ledgerRetained:list.firstElementChild===ledgerChild,mediaRetained:media.firstElementChild===mediaChild,bindingsBefore:before,bindingsAfter:window.__bindings.get(tab),sameRecentPromise:a===b,sameNewsPromise:c===d,model:window.hybridDashboard.buildMediaViewModel()};
  });
 }
 item.trace=await page.evaluate(()=>window.__loadingTrace);
 if(!baseline&&spec.name==='fail-news'){
  item.snapshotActions=await page.evaluate(()=>{
   const media=document.getElementById('top-media-pulse-content');
   document.dispatchEvent(new CustomEvent('hybrid:dataset',{detail:{name:'news'}}));
   document.dispatchEvent(new CustomEvent('hybrid:dataset',{detail:{name:'news'}}));
   const controls=[...media.querySelectorAll('[data-election-coverage-open],[data-topic-coverage-open],[data-hybrid-media-topic],[data-hybrid-media-candidate]')];
   const counts=controls.map(el=>window.__bindings.get(el)?.click||0);
   let opens=0;const modal=window.France2027ElectionCoverageModal, original=modal.open;
   // Spy on the existing dialog entrypoint while preserving its real behavior.
   // The public modal object may be frozen, so use its aria-expanded result instead.
   media.querySelector('[data-election-coverage-open]').click();
   return {counts,expanded:media.querySelector('[data-election-coverage-open]').getAttribute('aria-expanded'),dialogVisible:document.getElementById('election-coverage-modal')?.getAttribute('aria-hidden')};
  });
  check(item.snapshotActions.counts.every(n=>n===1),'snapshot action listeners bound exactly once',item);
  check(item.snapshotActions.expanded==='true','published snapshot evidence dialog usable',item);
  await page.keyboard.press('Escape');
 }
 if(!baseline){
  for(const s of [pending,final,item.reload].filter(Boolean)){
   check(s.path===pathname&&s.search==='?x=1'&&s.lang===lang,'pathname/query/language retained',item);
   check(s.overflow<=1,'no horizontal overflow',item);check(s.duplicateIds.length===0,'no duplicate IDs',item);
  }
  check(final.hash==='#signal-candidates','hash normalized within pathname',item);
  check(final.media.coverage===20,'Media retains source-linked coverage',item);
  check(!pending.what.skeleton&&!pending.media.skeleton,'no skeleton replaces useful snapshot',item);
  check(!errors.some(x=>x.startsWith('UNCAUGHT')),'no uncaught JS error',item);
  if(spec.name==='delay-news')check(pending.what.state==='ready','Recent Changes ready before News',item);
  if(spec.name==='delay-recent')check(pending.media.state==='ready','Media ready before Recent Changes',item);
  if(spec.name==='fail-recent'||spec.name==='invalid-recent')check(final.what.snapshot&&final.what.entries===3&&final.what.state==='stale','ledger failure retains published entries',item);
  else if(spec.name==='empty-recent')check(!final.what.snapshot&&final.what.entries===0&&final.what.text.length>0,'validated empty ledger shows real empty state',item);
  else check(final.what.entries>3&&final.what.state==='ready','valid ledger available',item);
  if(spec.name==='fail-news')check(final.media.snapshot&&final.media.state==='stale'&&final.what.state==='ready','News failure scoped; static Media retained',item);
  if(spec.name==='delay-candidates'||spec.name==='fail-candidates')check(pending.media.state==='ready','candidate comparison optional',item);
  if(spec.name==='delay-both')check(pending.what.snapshot&&pending.media.snapshot,'both snapshots retained while independently pending',item);
  if(spec.name==='provenance-mismatch')check(final.what.status.length>0&&warnings.some(x=>x.includes('provenance')),'scoped provenance warning preserves ledger',item);
  if(item.repeated){check(item.repeated.ledgerRetained&&item.repeated.mediaRetained,'unrelated/repeated updates preserve DOM',item);check(JSON.stringify(item.repeated.bindingsBefore)===JSON.stringify(item.repeated.bindingsAfter),'no duplicate tab listeners',item);check(item.repeated.sameRecentPromise&&item.repeated.sameNewsPromise,'loaders single-flight',item);}
 }
 results.push(item);record();console.log(lang,width,spec.name,'completed');await context.close();
}
try{
 for(const lang of ['fr','en'])for(const width of [1440,390,358]){
  const c=await browser.newContext({javaScriptEnabled:false,viewport:{width,height:1000}}),p=await c.newPage();await p.goto(base+(lang==='fr'?'/':'/en/'));statics.push({lang,width,...await sample(p)});await c.close();
 }
 const queue=[];for(const lang of ['fr','en'])for(const width of [1440,390,358])for(const spec of cases)queue.push({lang,width,spec});
 await Promise.all(Array.from({length:3},async()=>{while(queue.length){const job=queue.shift();await run(job.lang,job.width,job.spec);}}));
 if(!baseline){for(const item of results){
  const movement=Math.abs((item.final.following-item.final.media.top)-(item.boot.following-item.boot.media.top));
  item.followingShift=movement;item.absoluteFollowingShift=Math.abs(item.final.following-item.boot.following);item.mediaHeightShift=Math.abs(item.final.media.height-item.boot.media.height);
  check(item.width===1440||movement<=64,'mobile following-content shift <=64px (two status lines plus ledger toolbar wrapping)',item);
  check(item.width===1440||item.mediaHeightShift<=64,'mobile Media height shift <=64px',item);
 }}
 record();console.log(JSON.stringify({cases:results.length,failures:failures.length}));
}finally{await browser.close();await new Promise(r=>server.close(r));}
if(failures.length)process.exitCode=1;
