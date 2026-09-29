import Link from "next/link";
import { ArrowRight } from "lucide-react";

export default function LoginPage() {
  return <main className="login-layout"><Link className="brand login-brand" href="/"><span className="brand-mark">V</span><span>vantage<span className="brand-period">.</span></span></Link><section className="login-content"><div className="eyebrow"><span className="eyebrow-rule" />NORTHSTAR GROUP</div><h1>Perspective,<br />with an edge.</h1><p>Market context for the decisions ahead.</p><Link className="login-button" href="/workspace/overview"><span>Continue with development profile</span><ArrowRight size={17} /></Link><span className="login-caption">Development access · No external identity provider</span></section><div className="login-aside"><span>VANTAGE / 01</span><p>Notice earlier.<br />Understand deeper.</p><span>EXECUTIVE MARKET INTELLIGENCE</span></div></main>;
}