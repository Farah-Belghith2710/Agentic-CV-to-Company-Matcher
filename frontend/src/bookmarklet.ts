/**
 * The "Send to CV Matcher" bookmark.
 *
 * You drag it to your bookmarks bar once. On a LinkedIn job you are reading, a click runs this code in
 * your own browser tab: it reads what the page already shows (title, company, location, description,
 * or the text you selected) and opens a small CV Matcher window with it in the address, after "#".
 * It never loads another LinkedIn page and never runs on its own.
 *
 * The posting travels in the address fragment, which the browser does not send over the network;
 * the CV Matcher window then saves it to the app from its own page.
 */
const SOURCE = `(function(){
var APP="__APP__";
if(!/(^|\\.)linkedin\\.com$/.test(location.hostname)){alert("Open a job on LinkedIn first, then click Send to CV Matcher.");return;}
function pick(list){for(var i=0;i<list.length;i++){var el=document.querySelector(list[i]);if(el&&el.innerText&&el.innerText.trim()){return el;}}return null;}
function text(el){return el?el.innerText.replace(/\\u00a0/g," ").trim():"";}
var desc=pick(["#job-details",".jobs-description__content",".jobs-description-content__text",".jobs-box__html-content",".show-more-less-html__markup",".description__text"]);
var head=pick([".job-details-jobs-unified-top-card__job-title h1",".job-details-jobs-unified-top-card__job-title",".jobs-unified-top-card__job-title",".top-card-layout__title",".topcard__title","h1"]);
var comp=pick([".job-details-jobs-unified-top-card__company-name a",".job-details-jobs-unified-top-card__company-name",".jobs-unified-top-card__company-name",".topcard__org-name-link",".top-card-layout__second-subline a"]);
var place=pick([".job-details-jobs-unified-top-card__primary-description-container .tvm__text",".job-details-jobs-unified-top-card__bullet",".jobs-unified-top-card__bullet",".topcard__flavor--bullet"]);
var card=pick([".job-details-jobs-unified-top-card__container--two-pane",".job-details-jobs-unified-top-card__primary-description-container",".jobs-unified-top-card",".top-card-layout"]);
var title=text(head),company=text(comp),where=text(place);
var doc=document.title.replace(/^\\(\\d+\\+?\\)\\s*/,"");
var guest=doc.match(/^(.+?) hiring (.+?) in (.+?) \\| LinkedIn$/);
var parts=doc.split(" | ");
if(guest){title=title||guest[2];company=company||guest[1];where=where||guest[3];}
else if(parts.length>=3&&/LinkedIn$/.test(parts[parts.length-1])){title=title||parts[0];company=company||parts[1];}
var picked=String(window.getSelection()||"").trim();
var data={url:location.href,title:title,company:company,location:where,top:text(card).slice(0,1500),description:text(desc).slice(0,20000),selection:picked.slice(0,20000)};
if(!desc&&picked.length<200){data.page_text=document.body.innerText.slice(0,40000);}
var win=window.open(APP+"/#save="+encodeURIComponent(JSON.stringify(data)),"cv_matcher_save_"+Date.now(),"width=480,height=440");
if(!win){alert("Your browser blocked the CV Matcher window. Allow pop-ups for linkedin.com, then click the button again.");}
})();`;

/** The bookmark's address, pointing at this copy of CV Matcher (for example http://localhost:8000). */
export function bookmarkletHref(appOrigin: string): string {
  const code = SOURCE.replace("__APP__", appOrigin).replace(/\n/g, "");
  return `javascript:${encodeURIComponent(code)}`;
}

export interface Capture {
  url: string;
  title: string;
  company: string;
  location: string;
  top: string;
  description: string;
  selection: string;
  page_text?: string;
}

/** Reads the posting the bookmark put after "#save=". */
export function captureFromHash(hash: string): Capture | null {
  if (!hash.startsWith("#save=")) return null;
  try {
    const data = JSON.parse(decodeURIComponent(hash.slice("#save=".length)));
    return data && typeof data === "object" ? (data as Capture) : null;
  } catch {
    return null;
  }
}
