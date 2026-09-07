(function () {
  'use strict';

  const WELCOME_KEY = 'theRochelleEditWelcomeSeen';
  const VISIT_TRACK_KEY = 'theRochelleEditVisitTracked';
  const UMAMI_WEBSITE_ID = '4d20ec6e-67e3-44fc-acd3-5c53bfd78c80';
  const UMAMI_SCRIPT = 'https://cloud.umami.is/script.js';

  function safeGet(storage, key) {
    try { return storage.getItem(key); } catch (_) { return null; }
  }

  function safeSet(storage, key, value) {
    try { storage.setItem(key, value); return true; } catch (_) { return false; }
  }

  const hadWelcome = safeGet(window.localStorage, WELCOME_KEY) === '1';
  const visitorType = hadWelcome ? 'returning' : 'first';

  if (!hadWelcome) {
    safeSet(window.localStorage, WELCOME_KEY, '1');
  }

  function getEntryType() {
    const path = window.location.pathname.toLowerCase();
    if (path.endsWith('/article.html') || path.endsWith('article.html')) return 'article';
    return 'blog-home';
  }

  function withUmami(callback) {
    let completed = false;

    function invokeOnce() {
      if (completed || !window.umami || typeof window.umami.track !== 'function') return false;
      completed = true;
      callback();
      return true;
    }

    if (invokeOnce()) return;

    let script = document.querySelector('script[data-rochelle-umami="true"]') ||
      document.querySelector('script[data-website-id="' + UMAMI_WEBSITE_ID + '"]');

    if (!script) {
      script = document.createElement('script');
      script.defer = true;
      script.src = UMAMI_SCRIPT;
      script.dataset.websiteId = UMAMI_WEBSITE_ID;
      script.dataset.domains = 'rrlvsva.wasmer.app';
      script.dataset.rochelleUmami = 'true';
      document.head.appendChild(script);
    }

    function runWhenReady() {
      let attempts = 0;
      const timer = window.setInterval(function () {
        attempts += 1;
        if (invokeOnce() || attempts >= 30) {
          window.clearInterval(timer);
        }
      }, 200);
    }

    script.addEventListener('load', runWhenReady, { once: true });
    window.setTimeout(runWhenReady, 500);
  }

  function trackBlogVisit() {
    if (safeGet(window.sessionStorage, VISIT_TRACK_KEY) === '1') return;
    safeSet(window.sessionStorage, VISIT_TRACK_KEY, '1');

    withUmami(function () {
      window.umami.track('blog-visit', {
        visitor_type: visitorType,
        entry: getEntryType()
      });
    });
  }

  function trackReaderSignal() {
    if (getEntryType() !== 'article') return;

    let elapsedEnough = false;
    let scrolledEnough = false;
    let tracked = false;

    function maybeTrack() {
      if (tracked || !elapsedEnough || !scrolledEnough) return;
      tracked = true;
      withUmami(function () {
        window.umami.track('blog-reader', {
          article: document.title.replace(' | The Rochelle Edit', '')
        });
      });
      window.removeEventListener('scroll', checkScroll);
    }

    function checkScroll() {
      const doc = document.documentElement;
      const scrollable = Math.max(doc.scrollHeight - window.innerHeight, 1);
      const depth = window.scrollY / scrollable;
      if (depth >= 0.25) {
        scrolledEnough = true;
        maybeTrack();
      }
    }

    window.addEventListener('scroll', checkScroll, { passive: true });
    checkScroll();
    window.setTimeout(function () {
      elapsedEnough = true;
      maybeTrack();
    }, 20000);
  }

  function injectWelcomeStyles() {
    const style = document.createElement('style');
    style.textContent = `
      .tre-welcome{position:fixed;right:22px;bottom:22px;z-index:9999;width:min(390px,calc(100vw - 28px));background:#181512;color:#f7f1ea;border:1px solid #5a4738;box-shadow:0 18px 50px rgba(0,0,0,.34);padding:23px 22px 20px;opacity:0;transform:translateY(14px);pointer-events:none;transition:opacity .22s ease,transform .22s ease;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
      .tre-welcome.show{opacity:1;transform:translateY(0);pointer-events:auto}
      .tre-welcome:before{content:"";position:absolute;left:22px;right:22px;top:0;height:1px;background:linear-gradient(90deg,transparent,#d1ab63,#cb8f96,transparent)}
      .tre-welcome-close{position:absolute;top:10px;right:11px;width:34px;height:34px;border:0;background:transparent;color:#b9aca1;font-size:1.3rem;cursor:pointer;border-radius:50%}
      .tre-welcome-close:hover,.tre-welcome-close:focus-visible{color:#fff;background:#27211d;outline:none}
      .tre-welcome-eyebrow{text-transform:uppercase;letter-spacing:.15em;font-size:.68rem;font-weight:800;color:#cb8f96;margin:0 36px 8px 0}
      .tre-welcome-title{font:500 2rem/1.05 Georgia,"Times New Roman",serif;margin:0 34px 11px 0;color:#f7f1ea}
      .tre-welcome-copy{margin:0;color:#c2b5ab;font-size:.9rem;line-height:1.58}
      .tre-welcome-actions{display:flex;align-items:center;gap:14px;margin-top:17px;flex-wrap:wrap}
      .tre-welcome-primary{border:0;border-radius:999px;background:#d1ab63;color:#17110d;padding:9px 14px;font-weight:800;cursor:pointer}
      .tre-welcome-link{color:#d9c6b4;font-size:.8rem;text-decoration:none;border-bottom:1px solid rgba(217,198,180,.35)}
      .tre-welcome-link:hover{color:#fff}
      @media(max-width:620px){.tre-welcome{right:14px;bottom:14px;padding:21px 19px 18px}.tre-welcome-title{font-size:1.72rem}}
      @media(prefers-reduced-motion:reduce){.tre-welcome{transition:none}}
    `;
    document.head.appendChild(style);
  }

  function showWelcome() {
    if (hadWelcome) return;

    injectWelcomeStyles();
    const box = document.createElement('aside');
    box.className = 'tre-welcome';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-labelledby', 'tre-welcome-title');
    box.innerHTML = `
      <button class="tre-welcome-close" type="button" aria-label="Close welcome">×</button>
      <div class="tre-welcome-eyebrow">The Rochelle Edit</div>
      <h2 class="tre-welcome-title" id="tre-welcome-title">Welcome to the Blog</h2>
      <p class="tre-welcome-copy">Thanks for stopping by. This is a place for notes, ideas, and whatever feels worth putting into words.</p>
      <div class="tre-welcome-actions">
        <button class="tre-welcome-primary" type="button">Start reading</button>
        <a class="tre-welcome-link" href="../../privacy.html">Privacy</a>
      </div>
    `;

    document.body.appendChild(box);
    const closeButton = box.querySelector('.tre-welcome-close');
    const primaryButton = box.querySelector('.tre-welcome-primary');

    function closeWelcome() {
      box.classList.remove('show');
      window.setTimeout(function () { box.remove(); }, 230);
    }

    closeButton.addEventListener('click', closeWelcome);
    primaryButton.addEventListener('click', closeWelcome);
    document.addEventListener('keydown', function onKeydown(event) {
      if (event.key === 'Escape' && document.body.contains(box)) {
        closeWelcome();
        document.removeEventListener('keydown', onKeydown);
      }
    });

    window.setTimeout(function () {
      box.classList.add('show');
    }, 650);
  }

  function init() {
    trackBlogVisit();
    trackReaderSignal();
    showWelcome();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
