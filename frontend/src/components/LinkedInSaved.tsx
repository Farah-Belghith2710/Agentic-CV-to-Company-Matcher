import { useEffect, useRef, useState } from "react";
import { bookmarkletHref } from "../bookmarklet";
import type { SavedJob } from "../types";
import { Logo } from "./marks";

/** The draggable bookmark. React refuses javascript: links in markup, so the address is set directly. */
function BookmarkButton() {
  const ref = useRef<HTMLAnchorElement>(null);
  const [clicked, setClicked] = useState(false);
  useEffect(() => {
    ref.current?.setAttribute("href", bookmarkletHref(window.location.origin));
  }, []);
  return (
    <>
      <a
        ref={ref}
        className="bookmarklet"
        title="Drag me to your bookmarks bar"
        onClick={(e) => {
          e.preventDefault();
          setClicked(true);
        }}
      >
        <Logo />
        Send to CV Matcher
      </a>
      {clicked && <span className="bookmarklet-hint">Drag it to the bookmarks bar instead of clicking it here.</span>}
    </>
  );
}

/** Under "Jobs you saved from LinkedIn": the saved jobs, and how to add more. */
export function LinkedInSaved({ saved, onRemove, onClear }: { saved: SavedJob[]; onRemove: (id: string) => void; onClear: () => void }) {
  const steps = (
    <ol className="howto">
      <li>
        Drag this button to your bookmarks bar: <BookmarkButton />
        <span className="hint">No bookmarks bar? Press Ctrl+Shift+B.</span>
      </li>
      <li>Open a job or internship on LinkedIn and click the button. A small window confirms it was saved.</li>
      <li>Come back here and press Find and rank jobs.</li>
    </ol>
  );
  return (
    <div className="linkedin">
      {saved.length > 0 ? (
        <>
          <ul className="saved-list" aria-label="Jobs you saved from LinkedIn">
            {saved.map((j) => (
              <li key={j.id}>
                <span className="saved-text">
                  <span className="saved-title">{j.title}</span>
                  <span className="saved-meta">
                    {j.company}
                    {j.location ? `, ${j.location}` : ""}
                  </span>
                </span>
                <button type="button" className="text-button" onClick={() => onRemove(j.id)} aria-label={`Remove ${j.title}`}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
          <p className="saved-foot">
            <button type="button" className="text-button" onClick={onClear}>
              Remove all
            </button>
          </p>
          <details className="howto-more">
            <summary>How to add more</summary>
            {steps}
          </details>
        </>
      ) : (
        <>
          <p className="hint">Nothing saved yet. It takes three steps:</p>
          {steps}
        </>
      )}
    </div>
  );
}
