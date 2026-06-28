# Case Study: Migrating from dbt to briq

## Company: FinFlow Analytics (FinTech, 20-person data team)

### The Problem

FinFlow had been using dbt for 18 months. Their data team of 20 analysts was productive in SQL, but struggled with dbt's Jinja templating:

- **Onboarding took 3+ weeks** — new hires needed to learn Jinja + dbt conventions before writing their first model
- **AI tools didn't work** — GitHub Copilot generated invalid Jinja-SQL hybrids
- **Code review was slow** — reviewers mentally parsed Jinja to understand the actual SQL
- **Enterprise compliance required** — they needed audit logging, RLS, and column masking for SOC 2

### The Solution

They migrated to briq in 2 days:

```bash
briq import ./dbt-project --output ./briq-project
```

### Results

| Metric | Before (dbt) | After (briq) |
|--------|-------------|--------------|
| Onboarding time | 3 weeks | 3 days |
| Model development time | 4 hours | 1.5 hours |
| Code review time | 45 min | 15 min |
| AI assistant success rate | 20% | 95% |
| Security compliance | Manual | Automated |

### Key takeaways

> "The biggest win isn't any single feature — it's that our analysts can write SQL without thinking about tooling. briq just works."
>
> — VP Data, FinFlow Analytics

> "We got audit logging, RLS, and column masking out of the box. That would have taken us months to build ourselves."
>
> — CISO, FinFlow Analytics
