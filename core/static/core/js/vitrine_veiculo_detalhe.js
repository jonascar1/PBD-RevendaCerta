document.addEventListener('DOMContentLoaded', () => {
 const gallery=document.querySelector('.vd-galeria');
 const main=document.getElementById('foto-principal');
 const hero=document.querySelector('.vd-hero > img');
 const thumbs=Array.from(document.querySelectorAll('.vd-miniatura'));
 const prev=document.querySelector('.vd-prev'), next=document.querySelector('.vd-next');
 const counter=document.querySelector('.vd-contador-texto');
 let index=0, token=0;
 function show(i){if(!main||!thumbs.length)return; index=(i+thumbs.length)%thumbs.length; const current=++token; const url=thumbs[index].dataset.fotoUrl; const image=new Image(); image.onload=()=>{if(current!==token)return;main.src=url; if(hero){hero.src=url; if(!matchMedia('(prefers-reduced-motion: reduce)').matches)hero.animate([{opacity:.35},{opacity:.82}],{duration:400});} if(!matchMedia('(prefers-reduced-motion: reduce)').matches)main.animate([{opacity:.45},{opacity:1}],{duration:260});}; image.onerror=()=>{if(current===token)main.src=url;}; image.src=url; thumbs.forEach((b,j)=>{b.classList.toggle('ativa',j===index);b.setAttribute('aria-pressed',String(j===index));}); if(counter)counter.textContent=`${index+1} / ${thumbs.length}`; const strip=thumbs[index].parentElement; strip.scrollTo({left:thumbs[index].offsetLeft-strip.offsetLeft-strip.clientWidth/2+thumbs[index].offsetWidth/2,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}
 thumbs.forEach((b,i)=>b.addEventListener('click',()=>show(i))); if(prev&&next){prev.hidden=next.hidden=thumbs.length<2;prev.addEventListener('click',()=>show(index-1));next.addEventListener('click',()=>show(index+1));} if(gallery)gallery.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();show(index+(e.key==='ArrowRight'?1:-1));}});
 const options=document.querySelector('.vd-opcionais'); if(options){const items=options.innerText.split(/[,;\n]+/).map(s=>s.trim()).filter(Boolean); if(items.length){options.replaceChildren();items.forEach(item=>{const span=document.createElement('span');const icon=document.createElement('i');icon.dataset.lucide='check';span.append(icon,document.createTextNode(item));options.append(span);});}}
 if(window.lucide)window.lucide.createIcons();
});
