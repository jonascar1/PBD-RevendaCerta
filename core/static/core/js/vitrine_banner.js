document.addEventListener("DOMContentLoaded", () => {
 const banner = document.querySelector(".banner-carrossel"); if (!banner) return;
 const slides = [...banner.querySelectorAll(".banner-slide")], dots = [...banner.querySelectorAll(".banner-ponto")];
 if (slides.length < 2) return;
 const pause = banner.querySelector("[data-banner-pause]");
 let index = 0, timer, hover = banner.matches(":hover"), touching = false, x = 0;
 let paused = matchMedia("(prefers-reduced-motion: reduce)").matches;
 function show(i) { index = (i + slides.length) % slides.length; slides.forEach((s,n)=>{s.classList.toggle("ativo",n===index);s.inert=n!==index;s.setAttribute("aria-hidden",String(n!==index));}); dots.forEach((d,n)=>{d.classList.toggle("ativo",n===index);if(n===index)d.setAttribute("aria-current","true");else d.removeAttribute("aria-current");}); }
 function schedule(){clearTimeout(timer);if(!paused&&!hover&&!touching&&!document.hidden&&!banner.contains(document.activeElement))timer=setTimeout(()=>{show(index+1);schedule();},7000);}
 function go(i){show(i);schedule();}
 function updatePause(){pause.setAttribute("aria-pressed",String(paused));pause.setAttribute("aria-label",paused?"Retomar carrossel":"Pausar carrossel");pause.querySelector("span").textContent=paused?"▶":"Ⅱ";}
 banner.querySelector("[data-banner-prev]").addEventListener("click",()=>go(index-1));banner.querySelector("[data-banner-next]").addEventListener("click",()=>go(index+1));dots.forEach((d,n)=>d.addEventListener("click",()=>go(n)));
 pause.addEventListener("click",()=>{paused=!paused;updatePause();schedule();});
 banner.addEventListener("mouseenter",()=>{hover=true;schedule();});banner.addEventListener("mouseleave",()=>{hover=false;schedule();});banner.addEventListener("focusin",schedule);banner.addEventListener("focusout",()=>setTimeout(schedule,0));
 banner.addEventListener("touchstart",e=>{touching=true;x=e.changedTouches[0].clientX;schedule();},{passive:true});banner.addEventListener("touchend",e=>{touching=false;const dx=e.changedTouches[0].clientX-x;if(Math.abs(dx)>45)go(index+(dx<0?1:-1));else schedule();},{passive:true});banner.addEventListener("touchcancel",()=>{touching=false;schedule();});document.addEventListener("visibilitychange",schedule);show(0);updatePause();schedule();
});