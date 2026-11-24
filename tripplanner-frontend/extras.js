const css=document.createElement("style");css.textContent="main input,main select{padding:9px;border:1px solid var(--line);border-radius:8px;font:inherit;width:100%}";document.head.appendChild(css);
const v=id=>$("#"+id).value;
const inp=(id,ph,type="text",val="")=>`<input id="${id}" type="${type}" placeholder="${ph}" title="${ph}" value="${val}">`;
const apiSend=async(m,p,b)=>{const r=await fetch(CFG.api+p,{method:m,headers:{Authorization:"Bearer "+token,"Content-Type":"application/json"},body:JSON.stringify(b)});
if(r.status==401){logout();throw new Error("Sesión vencida")}
const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||r.status);return d};
async function askAgent(q){const r=await fetch(AGENT_URL,{method:"POST",headers:{Authorization:"Bearer "+token,"Content-Type":"application/json","X-Amzn-Bedrock-AgentCore-Runtime-Session-Id":sid()},body:JSON.stringify({prompt:q})});
if(r.status==401||r.status==403){logout();throw new Error("Sesión vencida")}
if(!r.ok)throw new Error("Error "+r.status);
const rd=r.body.getReader(),dec=new TextDecoder();let buf="",txt="";
for(;;){const{done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;while((i=buf.indexOf("\n\n"))>=0){txt+=piece(buf.slice(0,i));buf=buf.slice(i+2)}}
return txt+(buf.trim()?piece(buf):"")}
async function ask(el,q){el.innerHTML="<i class='mut'>Consultando…</i>";try{const t=await askAgent(q);el.innerHTML=fmt(t.replace(/```json[\s\S]*?```/g,"").trim())+cards(t)}catch(x){el.innerHTML=`<span class="err">${esc(x.message)}</span>`}}
const tabs={};
function show(id){document.querySelectorAll("nav button").forEach(x=>x.classList.toggle("on",x.dataset.t==id));document.querySelectorAll("main>section").forEach(s=>s.hidden=s.id!=id);if(tabs[id])tabs[id]()}
function addTab(id,label,fn,before){const b=document.createElement("button");b.dataset.t=id;b.textContent=label;const s=document.createElement("section");s.id=id;s.hidden=true;$("main").appendChild(s);$("nav").insertBefore(b,before?$(`nav [data-t=${before}]`):null);tabs[id]=fn;return s}
addTab("dash","Dashboard",async()=>{const el=$("#dash");try{const t=(await api("/trips")).trips||[],r=(await api("/reservations")).reservations||[];
const hoy=new Date().toISOString().slice(0,10);const next=t.filter(x=>x.start_date>=hoy).sort((a,b)=>a.start_date.localeCompare(b.start_date))[0];
el.innerHTML=`<div class="grid"><div class="card"><b>${t.length}</b><br>viajes</div><div class="card"><b>${r.length}</b><br>reservas</div></div><h3>Próximo viaje</h3>${next?R.trips(next):"<p class='mut'>Sin viajes próximos.</p>"}<h3>Reservas recientes</h3>${R.reservations(r.slice(-3).reverse())||"<p class='mut'>Sin reservas.</p>"}<p><button class="btn" onclick="show('chat')">Planear con el asistente</button> <button class="btn" onclick="show('flights')">Buscar vuelos</button> <button class="btn" onclick="show('weather')">Ver clima</button></p>`}catch(x){el.innerHTML=`<p class="err">${esc(x.message)}</p>`}},"chat");
addTab("flights","Vuelos",null,"trips").innerHTML=`<div class="card"><div class="grid">${inp("fo","Origen","text","Bogotá")}${inp("fd","Destino","text","Cartagena")}${inp("fa","Ida","date")}${inp("fb","Vuelta","date")}${inp("fn","Viajeros","number","1")}</div><br><button class="btn" onclick="searchFlights()">Buscar vuelos</button></div><div id="fout"></div>`;
function searchFlights(){ask($("#fout"),`Busca vuelos de ${v("fo")} a ${v("fd")}, ida ${v("fa")}, vuelta ${v("fb")}, para ${v("fn")} personas. Solo vuelos, sin clima.`)}
addTab("weather","Clima",null,"trips").innerHTML=`<div class="card"><div class="grid">${inp("wd","Destino","text","Cartagena")}${inp("wa","Desde","date")}${inp("wb","Hasta","date")}</div><br><button class="btn" onclick="searchWeather()">Consultar clima</button></div><div id="wout"></div>`;
function searchWeather(){ask($("#wout"),`Consulta el clima en ${v("wd")} del ${v("wa")} al ${v("wb")}. Solo clima, sin vuelos.`)}
let RES=[],TRIPS=[];
loadRes=async function(){const el=$("#res");try{TRIPS=(await api("/trips")).trips||[];RES=(await api("/reservations")).reservations||[];
el.innerHTML=`<div class="card"><b id="rt">Nueva reserva</b><div class="grid"><select id="rtrip">${TRIPS.map(t=>`<option value="${esc(t.tripId)}">${esc(t.destination)} (${esc(t.start_date)})</option>`).join("")}</select><select id="rtype"><option>VUELO</option><option>HOTEL</option><option>ACTIVIDAD</option></select>${inp("rti","Título")}${inp("rpr","Proveedor")}${inp("rpc","Precio","number")}${inp("rdt","Fecha","date")}<select id="rst"><option value="SIMULADA">Simulada</option><option value="PENDIENTE">Pendiente</option></select></div><input type="hidden" id="rid"><br><button class="btn" onclick="saveRes()">Guardar</button> <span id="rmsg" class="err"></span></div>`+(RES.map((r,i)=>R.reservations(r)+`<button class="btn" onclick="editRes(${i})">Editar</button> <button class="btn" style="background:#b91c1c" onclick="delRes(${i})">Eliminar</button>`).join("")||"<p class='mut'>Sin reservas todavía.</p>")}catch(x){el.innerHTML=`<p class="err">${esc(x.message)}</p>`}};
async function saveRes(){const id=v("rid"),b={type:v("rtype"),title:v("rti"),provider:v("rpr")||undefined,price:v("rpc")?Number(v("rpc")):undefined,date:v("rdt")||undefined,status:v("rst")};
try{if(id)await apiSend("PUT",`/trips/${v("rtrip")}/reservations/${id}`,b);else await apiSend("POST",`/trips/${v("rtrip")}/reservations`,b);loadRes()}catch(x){$("#rmsg").textContent=x.message}}
function editRes(i){const r=RES[i];$("#rt").textContent="Editando reserva";$("#rid").value=r.reservationId;$("#rtrip").value=r.tripId;$("#rtrip").disabled=true;$("#rtype").value=r.type;$("#rti").value=r.title||"";$("#rpr").value=r.provider||"";$("#rpc").value=r.price??"";$("#rdt").value=r.date||"";$("#rst").value=r.status==="CONFIRMADA"?"PENDIENTE":r.status;scrollTo(0,0)}
tabs.trips=()=>loadTrips();tabs.res=()=>loadRes();
const _start=start;start=function(){_start();show("dash")};
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>show(b.dataset.t));
if(token)show("dash");


async function delRes(i){const r=RES[i];if(!confirm("¿Eliminar la reserva '"+r.title+"'?"))return;try{await apiSend("DELETE",`/trips/${r.tripId}/reservations/${r.reservationId}`);loadRes()}catch(x){alert(x.message)}}

const PREF_HTML=`<div class="card"><b>Mis preferencias</b><div class="grid">${inp("pa","Actividades preferidas (ej. playa, historia)")}<select id="pb"><option value="">Presupuesto: sin definir</option><option value="ECONOMICO">Económico</option><option value="MEDIO">Medio</option><option value="ALTO">Alto</option></select>${inp("pr","Restricciones (ej. vegetariano)")}${inp("pn","Notas")}</div><br><button class="btn" onclick="savePrefs()">Guardar preferencias</button> <span id="pmsg" class="mut"></span></div>`;
const _lt=loadTrips;
loadTrips=async function(){await _lt();$("#trips").insertAdjacentHTML("afterbegin",PREF_HTML);try{const p=await api("/preferences");$("#pa").value=p.preferred_activities||"";$("#pb").value=p.budget_level||"";$("#pr").value=p.restrictions||"";$("#pn").value=p.notes||""}catch(x){}};
async function savePrefs(){try{await apiSend("PUT","/preferences",{preferred_activities:v("pa"),budget_level:v("pb")||undefined,restrictions:v("pr"),notes:v("pn")});$("#pmsg").textContent="Guardado"}catch(x){$("#pmsg").textContent=x.message}}
