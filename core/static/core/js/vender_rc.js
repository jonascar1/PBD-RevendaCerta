(()=>{
'use strict';
const f=document.querySelector('#ri-form'); if(!f)return;
const status=document.querySelector('#ri-status'),actions=document.querySelector('#ri-actions');
let pdf, filename, revision=0, logoReady=null, shareMessage="", pdfFile=null;
const phoneInput=f.elements.telefone, phoneError=document.querySelector('#ri-phone-error'), shareButton=document.querySelector('#ri-share');
function setStatus(message,kind='error'){status.textContent=message;status.dataset.kind=kind;}
function clearPhone(){phoneInput.removeAttribute('aria-invalid');phoneError.textContent='';}
phoneInput.addEventListener('input',()=>{const n=phoneInput.value.replace(/\D/g,'').slice(0,11);phoneInput.value=n.length<=2?n:n.length<=6?'('+n.slice(0,2)+') '+n.slice(2):'('+n.slice(0,2)+') '+n.slice(2,-4)+'-'+n.slice(-4);clearPhone();});
function shareData(){return {files:[pdfFile],text:shareMessage};}
function canShareFile(){try{return !!(window.isSecureContext && navigator.share && navigator.canShare && navigator.canShare({files:[pdfFile]}));}catch{return false;}}
async function sharePDF(){if(!pdfFile || !canShareFile())return;try{await navigator.share(shareData());setStatus('Compartilhamento concluído no dispositivo.','success');}catch(e){if(e.name==='AbortError'){setStatus('Ficha pronta. Você pode compartilhar novamente.','success');}else{setStatus('Não foi possível compartilhar. Use Baixar PDF ou tente novamente.','error');}}}
shareButton.addEventListener('click',sharePDF);

f.ano.max=new Date().getFullYear()+1;
const logoPromise=new Promise(resolve=>{const img=new Image(); const src=document.querySelector('link[rel="icon"]')?.href; if(!src){resolve(null);return;} const timer=setTimeout(()=>resolve(null),2500); img.onload=()=>{clearTimeout(timer);try{const c=document.createElement('canvas');c.width=240;c.height=240;const ctx=c.getContext('2d');const scale=240/Math.max(img.naturalWidth,img.naturalHeight);const w=img.naturalWidth*scale,h=img.naturalHeight*scale;ctx.drawImage(img,(240-w)/2,(240-h)/2,w,h);resolve(c.toDataURL('image/png'));}catch{resolve(null);}};img.onerror=()=>{clearTimeout(timer);resolve(null);};img.src=src;});
logoPromise.then(value=>{logoReady=value;});
f.addEventListener('input',()=>{revision++;pdf=null;pdfFile=null;actions.hidden=true;status.textContent='';});
f.addEventListener('submit',async e=>{
e.preventDefault();const ticket=++revision;pdf=null;pdfFile=null;actions.hidden=true;
const d=Object.fromEntries(new FormData(f));const digits=d.telefone.replace(/\D/g,'');
if(![10,11].includes(digits.length)){phoneInput.setAttribute('aria-invalid','true');phoneError.textContent='Informe um telefone com DDD (10 ou 11 dígitos).';phoneInput.focus();return;}
if(!window.jspdf){setStatus('Não foi possível carregar o gerador de PDF. Recarregue a página.');return;}
setStatus('Preparando sua ficha...','pending');const logo=logoReady;if(ticket!==revision)return;
try{
const p=new window.jspdf.jsPDF({unit:'mm',format:'a4'});const navy=[16,30,56],blue=[33,101,223],muted=[79,98,123],light=[240,244,249];
const fill=(c)=>p.setFillColor(...c);const ink=(c)=>p.setTextColor(...c);
const text=(s,x,y,size=10,bold=false,color=navy)=>{p.setFont('helvetica',bold?'bold':'normal');p.setFontSize(size);ink(color);p.text(String(s),x,y);};
const clean=v=>String(v??'').trim()||'Não informado';
const date=new Date().toLocaleString('pt-BR',{timeZone:'America/Recife',dateStyle:'short',timeStyle:'short'});
const phone=`(${digits.slice(0,2)}) ${digits.slice(2,-4)}-${digits.slice(-4)}`;
function header(first){fill(navy);p.rect(0,0,210,first?46:24,'F');fill(blue);p.rect(0,0,210,2,'F');if(logo)p.addImage(logo,'PNG',14,7,12,12);text('REVENDA CERTA',logo?30:14,14,15,true,[255,255,255]);if(first){text('Ficha de avaliação veicular',14,30,20,true,[255,255,255]);text('Solicitação de avaliação • '+date,14,39,9,false,[205,222,245]);}else{text('Continuação da ficha',145,14,9,false,[205,222,245]);}}
let y=54;header(true);
function ensure(h){if(y+h>269){p.addPage();header(false);y=32;}}
function section(n,title){ensure(14);fill(blue);p.roundedRect(14,y,8,8,2,2,'F');text(n,16,y+5.5,9,true,[255,255,255]);text(title,26,y+5.8,13,true);y+=12;}
function pair(a,b){const entries=[a,b];p.setFont('helvetica','bold');p.setFontSize(11);const lines=entries.map(v=>p.splitTextToSize(clean(v[1]),79));const h=Math.max(17,10+Math.max(...lines.map(l=>l.length))*5);ensure(h+3);entries.forEach((v,i)=>{const x=14+i*93;fill(light);p.roundedRect(x,y,89,h,2.5,2.5,'F');text(v[0].toUpperCase(),x+4,y+5,8,false,muted);p.setFont('helvetica','bold');p.setFontSize(11);ink(navy);p.text(lines[i],x+4,y+10.5,{lineHeightFactor:1.15});});y+=h+3;}
const title=clean(d.marca)+' '+clean(d.modelo);p.setFont('helvetica','bold');p.setFontSize(18);const titleLines=p.splitTextToSize(title,145);text('VEÍCULO PARA AVALIAÇÃO',14,y,8,true,muted);p.setFontSize(18);ink(navy);p.text(titleLines,14,y+8);fill([226,237,255]);p.roundedRect(165,y-3,31,10,3,3,'F');text(d.troca?'TROCA':'VENDA',170,y+3.5,10,true,blue);y+=12+titleLines.length*7;
section('01','Dados do veículo');pair(['Marca',d.marca],['Modelo',d.modelo]);pair(['Versão',d.versao],['Ano',d.ano]);pair(['Quilometragem',Number(d.km).toLocaleString('pt-BR')+' km'],['Câmbio',d.cambio]);y+=3;
section('02','Dados do proprietário');pair(['Nome',d.nome],['WhatsApp',phone]);pair(['Cidade',d.cidade],['Finalidade',d.troca?'Troca por outro veículo':'Venda do veículo']);y+=3;
section('03','Observações adicionais');p.setFont('helvetica','normal');p.setFontSize(10);let lines=p.splitTextToSize(String(d.observacoes||'').trim()||'Nenhuma observação informada.',172);while(lines.length){ensure(16);const count=Math.max(1,Math.floor((269-y-8)/5));const part=lines.splice(0,count);const h=8+part.length*5;fill(light);p.roundedRect(14,y,182,h,2,2,'F');p.setFont('helvetica','normal');p.setFontSize(10);ink(navy);p.text(part,19,y+6,{lineHeightFactor:1.35});y+=h+4;}
ensure(16);fill([231,240,255]);p.roundedRect(14,y,182,14,2,2,'F');text('Esta ficha é uma solicitação de avaliação, sem compromisso de compra.',19,y+5.5,9,false,navy);text('Os dados foram informados pelo solicitante e estão sujeitos à conferência.',19,y+10,8,false,muted);
const total=p.getNumberOfPages();for(let i=1;i<=total;i++){p.setPage(i);fill(navy);p.rect(0,277,210,20,'F');text('REVENDA CERTA  |  WhatsApp (87) 98102-5012',14,288,9,true,[255,255,255]);text(`${i} / ${total}`,184,288,9,false,[255,255,255]);}
p.setProperties({title:'Ficha de avaliação veicular',author:'Revenda Certa'});pdf=p;filename='RevendaCerta_Avaliacao_'+title.normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-zA-Z0-9]+/g,'_').slice(0,100)+'.pdf';
shareMessage='Olá! Gostaria de solicitar uma avaliação do meu veículo '+title+'. Segue a ficha em PDF.';
pdfFile=new File([p.output('blob')],filename,{type:'application/pdf'});
document.querySelector('#ri-wa').href='https://wa.me/5587981025012?text='+encodeURIComponent(shareMessage);
actions.hidden=false;shareButton.hidden=!canShareFile();
if(!shareButton.hidden){setStatus('Ficha pronta para compartilhar.','success');await sharePDF();}
else{setStatus(window.isSecureContext?'Ficha pronta. Este navegador não oferece compartilhamento de arquivos.':'Ficha pronta. O compartilhamento direto requer HTTPS ou localhost.','success');}

}catch(err){console.error(err);setStatus('Não foi possível gerar a ficha. Tente novamente.');}
});
document.querySelector('#ri-download').addEventListener('click',()=>{if(!pdfFile)return;const url=URL.createObjectURL(pdfFile);const a=document.createElement('a');a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);});
})();
