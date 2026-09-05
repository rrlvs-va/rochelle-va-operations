from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def write(name, text):
    (ROOT / name).write_text(text, encoding="utf-8")


def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"{label}: target not found")
    return text.replace(old, new, 1)


def replace_regex(text, pattern, replacement, label):
    updated, count = re.subn(pattern, replacement, text, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 replacement, got {count}")
    return updated


MENU_BUTTON_CSS = """
.menu-btn{display:none;width:44px;height:44px;align-items:center;justify-content:center;background:transparent;border:0;color:#fff;font-size:1.45rem;line-height:1;padding:0;cursor:pointer;border-radius:10px}
.menu-btn:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
""".strip()

MENU_BUTTON_HTML = '    <button class="menu-btn" type="button" aria-label="Toggle navigation" aria-expanded="false" onclick="toggleMobileMenu(this)">☰</button>\n'

MOBILE_NAV_SCRIPT = r'''
<script id="mobile-nav-script">
function toggleMobileMenu(button){
  const nav = button.closest('.nav-inner').querySelector('.nav-links');
  const isOpen = nav.classList.toggle('open');
  button.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
}

document.querySelectorAll('.nav-links a').forEach(function(link){
  link.addEventListener('click', function(){
    const nav = link.closest('.nav-links');
    nav.classList.remove('open');
    const button = nav.closest('.nav-inner')?.querySelector('.menu-btn');
    if(button) button.setAttribute('aria-expanded', 'false');
  });
});

document.addEventListener('keydown', function(event){
  if(event.key !== 'Escape') return;
  document.querySelectorAll('.nav-links.open').forEach(function(nav){
    nav.classList.remove('open');
    const button = nav.closest('.nav-inner')?.querySelector('.menu-btn');
    if(button) button.setAttribute('aria-expanded', 'false');
  });
});
</script>
'''


def add_menu_button_css(text):
    if MENU_BUTTON_CSS in text:
        return text
    match = re.search(r"\.nav-links\{[^}]+\}", text)
    if not match:
        raise RuntimeError("nav-links CSS not found")
    return text[:match.end()] + "\n" + MENU_BUTTON_CSS + text[match.end():]


def add_menu_button_html(text):
    if 'type="button" aria-label="Toggle navigation"' in text:
        return text
    needle = '    <div class="nav-links">'
    if needle not in text:
        raise RuntimeError("nav-links HTML insertion point not found")
    return text.replace(needle, MENU_BUTTON_HTML + needle, 1)


def add_mobile_script(text):
    if 'id="mobile-nav-script"' in text:
        return text
    if '</body>' not in text:
        raise RuntimeError("closing body not found")
    return text.replace('</body>', MOBILE_NAV_SCRIPT + '</body>', 1)


# ---------------------------------------------------------------------------
# INDEX / HOME PAGE
# ---------------------------------------------------------------------------
text = read("index.html")

home_media = r'''@media(max-width:980px){
  .wrap{width:min(var(--max),calc(100% - 36px))}
  .hero-grid,.services-layout,.experience-grid,.workflow-top,.portfolio-intro,.reviews-layout,.contact-grid{grid-template-columns:1fr}
  .hero{min-height:auto;padding:56px 0 60px!important}
  .hero-grid{gap:44px}
  .services-layout,.experience-grid,.workflow-top,.portfolio-intro,.reviews-layout,.contact-grid{gap:40px}
  .tools-grid{grid-template-columns:1fr}
  .portrait-shell{max-width:430px;margin:0 auto}
  .metric-strip{grid-template-columns:repeat(2,1fr)}
  .metric-item:nth-child(2){border-right:0}
  .metric-item:nth-child(-n+2){border-bottom:1px solid #342b25}
  .workflow-steps{grid-template-columns:repeat(2,1fr)}
  .workflow-step:nth-child(2){border-right:0}
  .workflow-step:nth-child(-n+2){border-bottom:1px solid var(--line-light)}
  .pricing-grid{grid-template-columns:1fr}
  .price-panel{border-right:0;border-bottom:1px solid var(--line-light)}
  .price-panel:last-child{border-bottom:0}
  .nav-links{position:absolute;left:0;right:0;top:72px;background:#13110f;border-bottom:1px solid #2e2722;padding:18px 20px 22px;display:none;flex-direction:column;align-items:center;text-align:center;gap:4px}
  .nav-links.open{display:flex}
  .nav-links a{width:min(320px,100%);min-height:44px;display:flex;align-items:center;justify-content:center;padding:10px 14px}
  .nav-links .nav-cta{width:auto;min-width:150px;margin-top:4px}
  .menu-btn{display:flex;width:44px;height:44px;align-items:center;justify-content:center}
}
@media(max-width:640px){
  .wrap{width:min(var(--max),calc(100% - 28px))}
  .nav-inner{min-height:66px;gap:10px}
  .brand strong{font-size:1rem}
  .brand span{font-size:.64rem;letter-spacing:.1em}
  .nav-links{top:66px;padding:14px 18px 20px}
  section{padding:56px 0}
  .section-title{font-size:clamp(2.35rem,10.5vw,3.2rem);line-height:1}
  .section-copy{font-size:.95rem;line-height:1.6}
  .hero{padding:38px 0 48px!important}
  .hero-grid{gap:32px}
  .hero h1{font-size:clamp(3rem,13vw,4.05rem);line-height:.94;margin:12px 0 16px}
  .hero-sub{font-size:1.22rem;line-height:1.28;margin-bottom:14px}
  .hero-copy{font-size:.95rem;line-height:1.62}
  .hero-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:22px}
  .hero-actions .btn{width:100%;padding:11px 13px;font-size:.9rem}
  .hero-actions .btn:first-child{grid-column:1/-1}
  .metric-strip{grid-template-columns:1fr;margin-top:28px}
  .metric-item{border-right:0;border-bottom:1px solid #342b25;padding:14px 0}
  .metric-item:last-child{border-bottom:0}
  .metric-item strong{font-size:.92rem}
  .metric-item span{font-size:.76rem;line-height:1.45}
  .portrait-shell{max-width:318px;padding:10px 10px 0;margin:0 auto}
  .portrait{max-width:286px;box-shadow:0 0 0 10px var(--ink),0 0 0 11px rgba(209,171,99,.42)}
  .portrait-caption{max-width:286px;margin-top:24px;font-size:.74rem;gap:12px}
  .services-layout,.experience-grid,.workflow-top,.portfolio-intro,.reviews-layout,.contact-grid{gap:26px}
  .service-row{grid-template-columns:36px 1fr;gap:10px 12px;padding:18px 0}
  .service-row h3{font-size:1.25rem}
  .service-row p{font-size:.91rem;line-height:1.55}
  .service-row .tag{grid-column:2;font-size:.68rem;padding-top:0}
  .timeline-item{grid-template-columns:1fr;gap:5px;padding:18px 0}
  .timeline-item p{font-size:.91rem;line-height:1.55}
  .workflow-steps{grid-template-columns:1fr;margin-top:28px}
  .workflow-step{border-right:0;border-bottom:1px solid var(--line-light);padding:20px 0}
  .workflow-step:last-child{border-bottom:0}
  .workflow-step h3{margin:0 0 8px;font-size:1.35rem}
  .workflow-step p{font-size:.91rem;line-height:1.55}
  .portfolio-list{margin-top:30px}
  .portfolio-item{grid-template-columns:1fr!important;gap:7px;padding:22px 0;align-items:start}
  .portfolio-item h3{font-size:1.4rem}
  .portfolio-item p{max-width:none;width:100%;font-size:.91rem;line-height:1.55}
  .portfolio-item .type{grid-column:auto!important;text-align:left;margin-top:6px;font-size:.69rem}
  .portfolio-cta{justify-content:stretch;margin-top:24px}
  .portfolio-cta .btn{width:100%}
  .pricing-grid{margin-top:30px}
  .price-panel{min-height:0;padding:24px 18px}
  .price-panel .price{font-size:2.1rem}
  .tools-grid{gap:20px;margin-top:28px}
  .tool-group{padding-bottom:20px}
  .tools-row{gap:8px 10px}
  .tool-chip{font-size:.8rem;padding:7px 8px}
  .tools-disclaimer{font-size:.84rem;line-height:1.55;margin-top:22px}
  .review-card{padding:22px 0}
  .review-quote{font-size:1.35rem;line-height:1.3}
  .review-rating{font-size:2rem}
  .form{gap:14px}
  .form-options{gap:10px 14px}
  .form button{width:100%;justify-self:stretch}
  .footer-inner{flex-direction:column;align-items:flex-start}
}

/* Navigation hover underline */'''

text = replace_regex(
    text,
    r'@media\(max-width:980px\)\{.*?\n\n/\* Navigation hover underline \*/',
    home_media,
    "index responsive blocks",
)

text = replace_once(
    text,
    '.menu-btn{display:none;background:none;border:0;color:#fff;font-size:1.4rem;padding:8px;cursor:pointer}',
    '.menu-btn{display:none;width:44px;height:44px;align-items:center;justify-content:center;background:transparent;border:0;color:#fff;font-size:1.45rem;line-height:1;padding:0;cursor:pointer;border-radius:10px}',
    "index menu button CSS",
)

text = replace_once(
    text,
    '<button class="menu-btn" aria-label="Toggle navigation" onclick="document.querySelector(\'.nav-links\').classList.toggle(\'open\')">☰</button>',
    '<button class="menu-btn" type="button" aria-label="Toggle navigation" aria-expanded="false" onclick="toggleMobileMenu(this)">☰</button>',
    "index menu button HTML",
)

text = text.replace('<span>Work experience</span>', '<span>Professional experience</span>')
text = text.replace('Read Service Guidelines', 'Read Service Policies')
text = text.replace('!~Disclaimer:', 'Disclaimer:')
text = add_mobile_script(text)
write("index.html", text)


# ---------------------------------------------------------------------------
# ABOUT PAGE
# ---------------------------------------------------------------------------
text = read("about.html")
text = add_menu_button_css(text)
text = add_menu_button_html(text)

about_media = r'''@media(max-width:980px){
  .hero-bottom{grid-template-columns:1fr;gap:24px}
  .hero-meta{text-align:left;border-top:1px solid var(--line-dark);padding-top:18px}
  .card-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .mission-vision{grid-template-columns:1fr;gap:48px}
  .statement-divider{display:block;width:160px;height:1px;background:linear-gradient(90deg,transparent,var(--gold),transparent);margin:0 auto}
  .values-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:720px){
  .wrap{width:min(var(--max),calc(100% - 28px))}
  .nav-inner{min-height:66px;align-items:center;flex-direction:row;padding:0;gap:10px}
  .brand strong{font-size:1rem}
  .brand span{font-size:.64rem;letter-spacing:.1em}
  .menu-btn{display:flex;margin-left:auto}
  .nav-links{position:absolute;left:0;right:0;top:66px;background:#13110f;border-bottom:1px solid #2e2722;padding:14px 18px 20px;display:none;flex-direction:column;align-items:center;text-align:center;gap:4px;z-index:60}
  .nav-links.open{display:flex}
  .nav-links a{width:min(320px,100%);min-height:44px;display:flex;align-items:center;justify-content:center;padding:10px 14px}
  .nav-links .btn{width:auto;min-width:150px;margin-top:4px}
  .hero{padding:46px 0 42px}
  .hero h1{font-size:clamp(2.9rem,13vw,3.5rem);margin-bottom:22px}
  .hero-bottom{gap:18px}
  .hero-copy{font-size:.96rem;line-height:1.62}
  .hero-divider{width:100%;height:1px;background:var(--line-dark)}
  .summary{padding:46px 0}
  .kicker-title{font-size:clamp(2.55rem,11vw,3.35rem)}
  .card-grid,.values-grid{grid-template-columns:1fr;gap:14px}
  .info-card{min-height:0;padding:21px 17px}
  .statement-section,.values-section,.faq-section,.contact-section{padding:52px 0}
  .statement{padding:4px 0}
  .statement h2{font-size:2.65rem}
  .faq-wrap{margin-top:24px}
  summary{padding:15px 4px;line-height:1.4}
  details p,details ul{font-size:.91rem}
  .contact-card{padding:26px 18px}
  .form button{width:100%;justify-self:stretch}
  .footer-inner{flex-direction:column;align-items:flex-start}
}
</style>'''

text = replace_regex(
    text,
    r'@media\(max-width:980px\)\{.*?</style>',
    about_media,
    "about responsive blocks",
)
text = text.replace('Service Guidelines', 'Service Policies')
text = text.replace('href="service-guidelines.html"', 'href="service-policies.html"')
text = add_mobile_script(text)
write("about.html", text)


# ---------------------------------------------------------------------------
# SERVICE POLICIES PAGE
# ---------------------------------------------------------------------------
text = read("service-policies.html")
text = add_menu_button_css(text)
text = add_menu_button_html(text)

policy_media = r'''@media (max-width:900px){
  .hero-grid,.summary-grid,.policy-grid{grid-template-columns:1fr;gap:30px}
  .hero-meta{border-left:0;border-top:1px solid var(--line-dark);padding:20px 0 0}
  .toc{position:relative;top:auto;max-height:250px;overflow-y:auto;display:block;border:1px solid var(--line-light);padding:0 16px 12px;background:#f7f2ec}
  .toc .toc-title{top:0;background:#f7f2ec;padding-top:14px}
  .toc a{padding:7px 0}
  .policy-section{scroll-margin-top:88px}
  .term-list{grid-template-columns:1fr}
}
@media (max-width:720px){
  .wrap{width:min(var(--max),calc(100% - 28px))}
  .nav-inner{min-height:66px;gap:10px}
  .brand strong{font-size:1rem}
  .brand span{font-size:.64rem;letter-spacing:.1em}
  .menu-btn{display:flex;margin-left:auto}
  .nav-links{position:absolute;left:0;right:0;top:66px;background:#13110f;border-bottom:1px solid #2e2722;padding:14px 18px 20px;display:none;flex-direction:column;align-items:center;text-align:center;gap:4px;z-index:60}
  .nav-links.open{display:flex}
  .nav-links .secondary{display:flex}
  .nav-links a{width:min(320px,100%);min-height:44px;align-items:center;justify-content:center;padding:10px 14px}
  .nav-links .btn{width:auto;min-width:150px;margin-top:4px}
  .hero{padding:46px 0 42px}
  .hero h1{font-size:clamp(2.8rem,12.5vw,3.35rem);margin-bottom:18px}
  .hero-copy{font-size:.95rem;line-height:1.62}
  .summary{padding:36px 0}
  .summary-points{grid-template-columns:1fr}
  .summary-point{padding:15px 0}
  .summary-point:nth-child(odd){border-right:0;padding-right:0}
  .summary-point:nth-child(even){padding-left:0}
  .policy-shell{padding:44px 0 62px}
  .policy-grid{gap:26px}
  .toc{max-height:220px}
  .policy-section{margin-bottom:34px;scroll-margin-top:80px}
  .policy-section h2{font-size:1.8rem}
  .policy-section h3{font-size:1.17rem}
  .policy-section p,.policy-section li{font-size:.93rem}
  .policy-note{padding:14px 15px}
  .contact-card{padding:26px 18px}
  .footer-inner{flex-direction:column;align-items:flex-start}
}

/* Navigation hover underline */'''

text = replace_regex(
    text,
    r'@media \(max-width:900px\)\{.*?\n\n/\* Navigation hover underline \*/',
    policy_media,
    "service policies responsive blocks",
)
text = text.replace('<title>Service Guidelines | Rochelle V. Silvestre</title>', '<title>Service Policies | Rochelle V. Silvestre</title>')
text = text.replace('Plain-language service guidelines', 'Plain-language service policies')
text = text.replace('<h1>Service <span>Guidelines</span></h1>', '<h1>Service <span>Policies</span></h1>')
text = text.replace('Service Guidelines', 'Service Policies')
text = add_mobile_script(text)
write("service-policies.html", text)


# ---------------------------------------------------------------------------
# PRIVACY PAGE
# ---------------------------------------------------------------------------
text = read("privacy.html")
text = add_menu_button_css(text)
text = add_menu_button_html(text)

privacy_media = r'''@media (max-width:900px){
  .hero-grid,.summary-grid,.policy-grid{grid-template-columns:1fr;gap:30px}
  .hero-meta{border-left:0;border-top:1px solid var(--line-dark);padding:20px 0 0}
  .toc{position:relative;top:auto;max-height:250px;overflow-y:auto;display:block;border:1px solid var(--line-light);padding:0 16px 12px;background:#f7f2ec}
  .toc .toc-title{top:0;background:#f7f2ec;padding-top:14px}
  .toc a{padding:7px 0}
  .policy-section{scroll-margin-top:88px}
}
@media (max-width:720px){
  .wrap{width:min(var(--max),calc(100% - 28px))}
  .nav-inner{min-height:66px;gap:10px}
  .brand strong{font-size:1rem}
  .brand span{font-size:.64rem;letter-spacing:.1em}
  .menu-btn{display:flex;margin-left:auto}
  .nav-links{position:absolute;left:0;right:0;top:66px;background:#13110f;border-bottom:1px solid #2e2722;padding:14px 18px 20px;display:none;flex-direction:column;align-items:center;text-align:center;gap:4px;z-index:60}
  .nav-links.open{display:flex}
  .nav-links .secondary{display:flex}
  .nav-links a{width:min(320px,100%);min-height:44px;align-items:center;justify-content:center;padding:10px 14px}
  .nav-links .btn{width:auto;min-width:150px;margin-top:4px}
  .hero{padding:46px 0 42px}
  .hero h1{font-size:clamp(2.8rem,12.5vw,3.35rem);margin-bottom:18px}
  .hero-copy{font-size:.95rem;line-height:1.62}
  .summary{padding:36px 0}
  .summary-points,.rights-grid{grid-template-columns:1fr}
  .summary-point{padding:15px 0}
  .summary-point:nth-child(odd){border-right:0;padding-right:0}
  .summary-point:nth-child(even){padding-left:0}
  .policy-shell{padding:44px 0 62px}
  .policy-grid{gap:26px}
  .toc{max-height:220px}
  .policy-section{margin-bottom:34px;scroll-margin-top:80px}
  .policy-section h2{font-size:1.8rem}
  .policy-section h3{font-size:1.17rem}
  .policy-section p,.policy-section li{font-size:.93rem}
  .policy-note{padding:14px 15px}
  .contact-card{padding:26px 18px}
  .footer-inner{flex-direction:column;align-items:flex-start}
}

/* Navigation hover underline */'''

text = replace_regex(
    text,
    r'@media \(max-width:900px\)\{.*?\n\n/\* Navigation hover underline \*/',
    privacy_media,
    "privacy responsive blocks",
)
text = text.replace('Service Guidelines', 'Service Policies')
text = add_mobile_script(text)
write("privacy.html", text)

print("Responsive repair complete")
