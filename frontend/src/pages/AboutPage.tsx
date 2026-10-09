import { API_URL } from '../lib/api'

export function AboutPage() {
  return (
    <div className="page about-page">
      <div className="hero"><p className="eyebrow">Honest claims</p><h1>What ClearCredit proves—and what it absolutely does not.</h1><p>Climate integrity needs precise claims, not shiny language. Here is the actual boundary of the system.</p></div>
      <section className="about-grid">
        <article className="card about-lead"><span className="about-number">01</span><h2>The useful claim</h2><p>ClearCredit produces an integrity score and a verified integrity attestation for a carbon-credit claim.</p><p>The blockchain proves a record was not altered after registration and enforces that the same land (H3 cell) and vintage cannot be registered twice, and that credits cannot be retired twice.</p></article>
        <article className="card about-warning"><span className="about-number">02</span><h2>The hard limit</h2><p><strong>It does not prove physical truth.</strong> Satellite data is evidence, not certification. Exact polygon overlap is checked off-chain; the on-chain cell index is a conservative backstop.</p><p>Scores flag claims as suspicious when they conflict with independent evidence; they do not prove fraud.</p></article>
        <article className="card"><span className="about-number">03</span><h2>Read the evaluation correctly</h2><p>Our evaluation measures detection of injected faults on a seeded dataset, not real-world fraud prevalence.</p><p>A developer can still register a fabricated project on land nobody else claims; the system can only flag inconsistencies with satellite data.</p></article>
      </section>
      <section className="card resource-card"><div><p className="eyebrow">Inspect the system</p><h2>Open interfaces</h2></div><div className="resource-links"><a href={`${API_URL}/docs`} target="_blank" rel="noreferrer">OpenAPI docs ↗</a><a href="https://github.com/VICTOR-VIT-projects/clearcredit/blob/main/docs/CLAIM_SCHEMA.md" target="_blank" rel="noreferrer">Claim schema and hashing rules ↗</a><a href={`${API_URL}/schema`} target="_blank" rel="noreferrer">Claim schema, machine-readable JSON ↗</a><a href="https://github.com/VICTOR-VIT-projects/clearcredit" target="_blank" rel="noreferrer">GitHub repository ↗</a></div></section>
    </div>
  )
}
