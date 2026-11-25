// Only revalidate documents restored from the back-forward cache.
// Ordinary link clicks and fresh history requests remain untouched.
window.addEventListener("pagehide", () => {
    document.documentElement.style.visibility = "hidden";
});
window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
        window.location.reload();
    } else {
        document.documentElement.style.visibility = "";
    }
});
