export const THEME_KEY = "mfstsp.theme";

// Runs in <head> before paint so the page never flashes the wrong theme.
// A saved choice wins; on the first visit the device preference picks the theme.
export const THEME_SCRIPT = `(function(){var t;try{t=localStorage.getItem("${THEME_KEY}")}catch(e){}if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";document.documentElement.dataset.theme=t})()`;
