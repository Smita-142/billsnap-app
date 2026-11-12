import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowDown, ArrowRight, Check, ChevronRight, Menu, ScanLine, ShieldCheck, Sparkles, X } from 'lucide-react';
import './LandingPage.css';

function ChromeLines() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!window.CanvasRenderingContext2D) return undefined;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return undefined;

    const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    let width = 0;
    let height = 0;
    let phase = 0;
    let lastFrameTime = 0;

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const draw = (timestamp = 0) => {
      if (timestamp - lastFrameTime < 32 && !motionPreference.matches) {
        frame = window.requestAnimationFrame(draw);
        return;
      }
      lastFrameTime = timestamp;
      context.clearRect(0, 0, width, height);
      const isSmallScreen = window.innerWidth < 700;
      const lineCount = isSmallScreen ? 20 : 34;
      const step = isSmallScreen ? 22 : 16;

      for (let index = 0; index < lineCount; index += 1) {
        const offset = index / lineCount;
        context.beginPath();
        for (let x = 0; x <= width; x += step) {
          const wave = Math.sin((x / Math.max(width, 1)) * 5 + phase + offset * 3) * height * 0.07 * (1 - offset * 0.4);
          const ripple = Math.sin((x / Math.max(width, 1)) * 11 - phase * 1.3) * height * 0.015;
          const y = height * (0.32 + offset * 0.56) + wave + ripple;
          if (x === 0) context.moveTo(x, y);
          else context.lineTo(x, y);
        }
        const glow = Math.pow(1 - Math.abs(offset - 0.45) * 2, 2);
        context.strokeStyle = `rgba(204, 214, 225, ${0.025 + 0.12 * glow})`;
        context.lineWidth = 1;
        context.stroke();
      }

      if (!motionPreference.matches && !document.hidden) {
        phase += 0.004;
        frame = window.requestAnimationFrame(draw);
      }
    };

    const onVisibilityChange = () => {
      window.cancelAnimationFrame(frame);
      if (document.hidden) return;
      if (motionPreference.matches) draw();
      else frame = window.requestAnimationFrame(draw);
    };

    resize();
    draw();
    window.addEventListener('resize', resize);
    document.addEventListener('visibilitychange', onVisibilityChange);
    motionPreference.addEventListener?.('change', onVisibilityChange);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      motionPreference.removeEventListener?.('change', onVisibilityChange);
    };
  }, []);

  return <canvas ref={canvasRef} className="landing-canvas" aria-hidden="true" />;
}

function ReceiptPreview() {
  return <div className="landing-preview">
    <div className="landing-preview-heading">
      <span className="landing-receipt-icon"><ScanLine size={17} /></span>
      <div><strong>A closer look</strong><small>Illustrative receipt layout</small></div>
      <span className="landing-preview-status"><i /> PRIVACY REVIEW</span>
    </div>
    <div className="landing-receipt">
      <div className="landing-receipt-brand"><span>R</span><div><strong>MERCHANT</strong><small>Receipt preview</small></div></div>
      <div className="landing-receipt-meta"><span>Date not detected</span><span>RECEIPT</span></div>
      <div className="landing-receipt-line"><span>Merchant</span><span>Not detected</span></div>
      <div className="landing-receipt-line"><span>Phone</span><span>Not detected</span></div>
      <div className="landing-receipt-line"><span>Invoice</span><span>Not detected</span></div>
      <div className="landing-receipt-divider" />
      <div className="landing-receipt-line"><span>Item</span><span>Not detected</span></div>
      <div className="landing-receipt-line"><span>Tax</span><span>Not detected</span></div>
      <div className="landing-receipt-total"><strong>Total</strong><strong>Not detected</strong></div>
      <span className="landing-beam" aria-hidden="true" />
    </div>
    <div className="landing-preview-foot"><ShieldCheck size={14} /><span>Choose what to review before saving.</span><span className="landing-demo-label">MOCK PREVIEW</span></div>
  </div>;
}

export default function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false);

  const closeMenu = () => setMenuOpen(false);

  return <div className="landing-page">
    <header className="landing-hero">
      <ChromeLines />
      <div className="landing-shade" aria-hidden="true" />
      <nav className="landing-nav" aria-label="Main navigation">
        <Link className="landing-brand" to="/" aria-label="Bill Snap home" onClick={closeMenu}><span className="landing-brand-mark"><i /></span><span>Bill Snap</span></Link>
        <div className={`landing-links ${menuOpen ? 'landing-links-open' : ''}`}>
          <Link to="/scan" onClick={closeMenu}>Scan</Link>
          <a href="#privacy" onClick={closeMenu}>Privacy</a>
          <Link to="/insights" onClick={closeMenu}>Insights</Link>
          <Link to="/assistant" onClick={closeMenu}>Ask AI</Link>
          <Link to="/login" onClick={closeMenu}>Sign in</Link>
          <Link to="/signup" onClick={closeMenu}>Get started</Link>
          <Link className="landing-mobile-app" to="/app" onClick={closeMenu}>Open app <ArrowRight size={15} /></Link>
        </div>
        <Link className="landing-open-app" to="/app" aria-label="Open Bill Snap app">Open app <ArrowRight size={14} /></Link>
        <button className="landing-menu-button" type="button" aria-label={menuOpen ? 'Close menu' : 'Open menu'} aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
      </nav>

      <main className="landing-main">
        <section className="landing-copy" aria-labelledby="landing-title">
          <div className="landing-kicker"><span /> A LITTLE MORE CLARITY, EVERY DAY</div>
          <h1 id="landing-title">Your bills.<br />Your money.<br /><strong>Your privacy.</strong></h1>
          <p className="landing-subtitle">A calmer way to keep track of your expenses. Review what’s private, make it yours, and find a clearer picture of where your money goes.</p>
          <div className="landing-actions">
            <Link className="landing-button landing-button-primary" to="/scan"><ScanLine size={17} /> Scan a bill <ArrowRight size={16} /></Link>
            <Link className="landing-button landing-button-secondary" to="/login">Sign in <ArrowRight size={15} /></Link>
          </div>
          <div className="landing-local-note"><span><Check size={13} /></span> Explore sample insights in the public demo.</div>
        </section>

        <aside className="landing-visual" aria-label="Sample receipt privacy review">
          <ReceiptPreview />
          <div className="landing-float-note"><span><Sparkles size={15} /></span><div><strong>Your call, always.</strong><small>A preview—not a real redaction.</small></div></div>
          <div className="landing-visual-index"><span>01</span><i /><span>03</span></div>
        </aside>
      </main>

      <div className="landing-bottom">
        <a href="#privacy" className="landing-scroll-cue"><span>SCROLL TO EXPLORE</span><ChevronRight size={13} /></a>
        <div className="landing-stat"><strong>0</strong><span>sample bills<br />in your workspace</span></div>
        <div className="landing-stat"><strong>1</strong><span>review step<br />before saving</span></div>
        <div className="landing-stat"><strong>OCR</strong><span>powered by<br />your backend</span></div>
      </div>
    </header>

    <section className="landing-story" id="privacy">
      <div className="landing-story-heading">
        <span className="landing-story-kicker">A CLEARER WAY TO KEEP TRACK</span>
        <h2>Money feels simpler<br />when it makes sense.</h2>
        <p>Bill Snap brings your receipts together and gives you room to decide what you want to do next.</p>
      </div>
      <div className="landing-feature-grid">
        <article className="landing-feature">
          <span className="landing-feature-icon"><ScanLine size={19} /></span>
          <span className="landing-feature-number">01 / CAPTURE</span>
          <h3>One place for every receipt.</h3>
          <p>Scan a receipt and review its extracted details.</p>
          <Link to="/scan">Scan a receipt <ArrowRight size={14} /></Link>
        </article>
        <article className="landing-feature">
          <span className="landing-feature-icon feature-mint"><ShieldCheck size={19} /></span>
          <span className="landing-feature-number">02 / REVIEW</span>
          <h3>Your details, your decision.</h3>
          <p>Review the original image and correct extracted fields before a bill is saved.</p>
          <Link to="/scan">See the review flow <ArrowRight size={14} /></Link>
        </article>
        <article className="landing-feature">
          <span className="landing-feature-icon feature-blue"><Sparkles size={19} /></span>
          <span className="landing-feature-number">03 / UNDERSTAND</span>
          <h3>See the story in your spending.</h3>
          <p>Browse sample categories, charts, and assistant answers—without a connected AI or financial account.</p>
          <Link to="/insights">Explore insights <ArrowRight size={14} /></Link>
        </article>
      </div>
      <div className="landing-honesty"><ShieldCheck size={17} /><p><strong>A demo with clear boundaries.</strong> Data stays in this browser. Privacy previews don’t securely erase image pixels, and AI answers use sample data only.</p><Link to="/app">Open the app <ArrowRight size={14} /></Link></div>
    </section>

    <footer className="landing-footer">
      <Link className="landing-brand" to="/"><span className="landing-brand-mark"><i /></span><span>Bill Snap</span></Link>
      <span>Thoughtful spending starts with a little clarity.</span>
      <div><Link to="/settings">Preferences</Link><Link to="/app">Open app <ArrowRight size={13} /></Link></div>
    </footer>
  </div>;
}
