# Incremental Tool — Product Specification

**Version:** 0.2
**Agency:** Terroir
**Product:** Incremental Tool
**Status:** Pre-Development

---

## 1. Product Overview

A branded, multi-tenant web application built by Terroir that enables marketing practitioners and C-suite executives to design, manage, and analyze geographic incrementality tests. The tool handles test design (geo clustering and cell assignment), test tracking, and post-test analysis — producing both an interactive dashboard and a downloadable report.

All statistical calculations are deterministic code. The LLM layer is used exclusively for interpretation and narrative.

---

## 2. Users & Roles

### 2.1 Role Definitions

| Role | Description | Access |
|------|-------------|--------|
| **Super Admin** | Terroir operator | All client workspaces, all tests, all reports |
| **Practitioner** | Client-side analyst or media manager | Their workspace only; data upload, test config, full detail view |
| **C-Suite** | Client-side executive | Their workspace only; dashboard summary, report download |

> Practitioners and C-suite share the same view. The UI uses a **progressive disclosure** pattern — a clean executive summary is always visible, with analysis detail and methodology/formulas accessible via collapsible sections below.

### 2.2 Authentication & Access
- Each client organization has an isolated workspace
- Users log in via email/password (invite-based)
- Terroir manually creates all client workspaces and assigns roles — no self-registration
- Super Admin has a global view across all client workspaces

---

## 3. Core Features

### 3.1 Test Management
- Create and manage multiple concurrent tests per workspace
- Each test has a name, description, channel, date range, and status (Draft, Active, Completed)
- Test types:
  - **Geo Split Test** — K-means clustering, randomized geo cell assignment, full incrementality analysis
  - **Pre/Post Test** — Single market, before/after comparison, no geo splitting

### 3.2 Data Ingestion

**Phase 1 (Launch):** CSV Upload
- Upload historical performance data (region, period, primary metric, spend, optional supporting metrics)
- Upload post-test results data separately
- Region granularity supported: **State, DMA, or ZIP cluster** — selected per test
- Validation on upload: required columns, date format, missing values flagged with clear error messages
- Supported file format: `.csv`

**Phase 2 (Future):** Ad Platform API Integrations
- Google Ads
- Meta (Facebook/Instagram)
- TikTok
- Extensible to other platforms

**Spend Data:** Imported via CSV for all phases.

---

## 4. Geo Split Test — Workflow

### Stage 1: Pre-Test Design

#### Step 1 — Data Upload & Region Configuration
User uploads historical performance CSV and selects region granularity (State / DMA / ZIP cluster). Required columns:
- Region identifier (matching selected granularity)
- Period (week or month)
- Primary metric (revenue or conversions)
- Spend (optional at this stage)
- Supporting metrics (optional)

#### Step 2 — Feature Engineering
System automatically calculates per region:
- Average performance (mean of primary metric over baseline period)
- Volatility (Coefficient of Variation: `σ / μ`)
- Growth trend (linear regression slope over baseline period)
- Seasonality stability (ratio of peak to trough within baseline)
- Market size proxy (total baseline volume)

Results shown in a sortable, filterable data table. User can review and optionally exclude regions before clustering.

#### Step 3 — K-Means Clustering (Optimized)
- System normalizes all features using z-score standardization (StandardScaler)
- Automatically runs K-means for k = 2 through 6 and calculates the **silhouette score** for each
- Recommends the k with the highest silhouette score; user can override (2–4 range for test cell assignment)
- Displays: cluster centroids, silhouette score, within-cluster variance, and a plain-English interpretation of each cluster (e.g., "High volume, stable markets")
- Visual: map and scatter plot showing cluster assignments

#### Step 4 — Stratified Cell Assignment
- Within each cluster, system performs stratified random assignment of regions to test cells (2–4 cells, user-selected)
- Runs 500+ assignment iterations; selects the configuration with the lowest Coefficient of Variation (CV < 15%) across the primary metric, spend, and volatility
- Displays balance summary: each cell's mean metric, total volume, spend, and CV side-by-side
- User can manually reassign individual regions; system recalculates balance metrics on each change
- Output: geo-to-cell assignment table ready to replicate in the ad platform

#### Step 5 — Power Analysis (Pre-Test)
Before finalizing the test, the system runs a power calculation to confirm the test is adequately powered:
- Inputs: number of geos per cell, baseline variance, expected minimum detectable effect (MDE), desired confidence level (80% / 90% / 95%)
- Output: recommended minimum test duration in weeks, probability of detecting a true effect at the specified MDE
- If the test is likely underpowered, the system displays a plain-English warning with specific recommendations (extend duration, consolidate geos, increase spend contrast)

#### Step 6 — Test Configuration
User inputs:
- Test name
- Channel(s): Paid Search, Paid Social, CTV *(Direct Mail, Email in Phase 2)*
- Treatment per cell (e.g., Cell A = Control, Cell B = Media heavy-up, Cell C = New creative)
- Test start date, end date, cooldown period
- Primary success metric: Revenue or Conversions

System generates a **Test Setup Summary** the user can reference when configuring campaigns in the ad platform.

---

### Stage 2: Active Test Monitoring

- Test status card shows days elapsed, days remaining, and power status
- User can upload interim data to view in-flight Δ vs Baseline trends
- No analysis is finalized until the user marks the test as complete

---

### Stage 3: Post-Test Analysis

#### Data Upload
User uploads post-test CSV with:
- Weekly or daily data by region for the test period
- Baseline period data (same regions)
- Prior-year equivalent period data (for YoY)
- Spend per cell for the test period

---

#### Analysis Modules

All calculations are deterministic code — no LLM involvement.

---

##### Module 1 — Δ vs Baseline
A descriptive measure of change from the pre-test period.

```
Δ_i = Metric_post_i − Avg(Metric_baseline_i)
```

Reported weekly and as a cumulative average per cell. Used as an input to DiD, not as a standalone causal estimate.

---

##### Module 2 — Difference-in-Differences: Primary Method (TWFE Regression)

The primary causal estimate. Two-Way Fixed Effects (TWFE) regression controls for persistent geo-level differences and national time trends — the gold standard for geo-based media tests.

**Model:**
```
Y_it = α + β₁(Treat_i) + β₂(Post_t) + β₃(Treat_i × Post_t) + γ_i + δ_t + ε_it
```

Where:
- `Y_it` = primary metric for geo `i` at time `t`
- `Treat_i` = 1 if geo is in a treatment cell, 0 if control
- `Post_t` = 1 if the observation is in the test period, 0 if baseline
- `β₃` = **the treatment effect (what we report)**
- `γ_i` = geo fixed effects (absorbs persistent differences between markets)
- `δ_t` = time fixed effects (absorbs national seasonality and macro shocks)
- `ε_it` = error term, with standard errors **clustered at the geo level**

Reported per treatment cell vs. control. Includes p-value and 80%, 90%, 95% confidence intervals, displayed in both numeric and plain-English form.

**Parallel Trends Validation (required pre-step):**
Before reporting DiD results, the system runs a formal parallel trends test using pre-period data only. It regresses the pre-period outcome on a time trend interacted with the treatment indicator. If the interaction coefficients are not jointly zero (p < 0.10), the system flags this prominently and notes the DiD result may be biased.

---

##### Module 3 — Difference-in-Differences: Secondary Method (Simple Mean Comparison)

A simpler, more interpretable view of the same question. Reported alongside TWFE for transparency.

```
DiD_simple = Δ_TestCell − Δ_Control
```

Where `Δ = Avg(Post) − Avg(Baseline)` per cell.

Reported weekly and as a cumulative average. Useful for communicating directional results to non-technical audiences.

---

##### Module 4 — Year-over-Year (YoY)

Controls for seasonality by comparing the same period in the prior year.

```
YoY%_i = (Metric_current_i − Metric_prior_i) / Metric_prior_i × 100
```

**YoY DiD** = YoY% of test cell − YoY% of control cell, in both percentage points and dollars.

Reported per cell, weekly and cumulative.

---

##### Module 5 — Pre-Trend Bias Adjustment (Regression-Based)

Estimates and adjusts for any pre-existing trend differential between test and control geos.

The pre-trend coefficient `β_pre` is estimated by regressing the pre-period outcome on a time trend interacted with the treatment indicator. If `β_pre` is statistically significant, it is used to adjust the raw YoY DiD:

```
Adjusted_YoY_DiD_$ = Raw_YoY_DiD_$ − (β_pre × Prior_Year_Baseline_$)
```

If `β_pre` is not significant (p > 0.10), the adjustment is minimal and the system notes the experiment is "causally clean." The pretrend diagnostic table (β, p-value, raw DiD, adjusted DiD, % change) is shown in the Analysis Detail section.

---

##### Module 6 — Reconciled Incrementality

Triangulates between two independent causal estimates to produce a conservative final estimate.

**Standard (midpoint):**
```
Final_Incremental_$ = (TWFE_DiD_$ + Adjusted_YoY_$) / 2
```

**Advanced (variance-weighted):**
```
Final_Incremental_$ = (TWFE_DiD_$ / Var_TWFE + Adjusted_YoY_$ / Var_YoY) / (1/Var_TWFE + 1/Var_YoY)
```

Both are computed. The variance-weighted result is surfaced in the "Advanced" collapsible section; the midpoint is the headline figure.

---

##### Module 7 — ROAS / iROAS

```
ROAS_low  = TWFE_DiD_$ / Spend
ROAS_mid  = Reconciled_$ / Spend
ROAS_high = Adjusted_YoY_$ / Spend
```

Bootstrap confidence intervals (1,000 resamples) are computed for each ROAS estimate and displayed as a range bar chart. Break-even (1.0x) is marked as a reference line.

---

#### Statistical Significance Display

For every causal estimate (TWFE DiD, YoY DiD, ROAS), the system surfaces:
- **p-value** (numeric)
- **Confidence intervals** at 80%, 90%, and 95% levels
- **Plain-English interpretation** generated by the LLM layer (e.g., "The test markets outperformed control by 17.8%. This result is statistically significant at the 90% confidence level, meaning there is a 90% probability this lift is real and not due to random variation.")

Statistical significance is never hidden. If a result is directionally positive but not significant, the system explains why (common causes: high geo variance, short test duration, low spend contrast) and what it means for interpretation.

---

## 5. Pre/Post Test — Workflow

- User selects region granularity (State / DMA / ZIP) and a single market or set of markets
- Uploads pre-period and post-period data
- System calculates:
  - Absolute and % change in primary metric
  - Spend comparison (pre vs post)
  - ROAS pre vs post
  - Simple significance test (paired t-test on weekly observations)
- Output: summary card + trend chart + downloadable report

---

## 6. Dashboard & UI

### 6.1 Layout Pattern: Progressive Disclosure

```
┌──────────────────────────────────────────────┐
│  EXECUTIVE SUMMARY                           │  ← Always visible
│  Incremental Revenue: $X                     │
│  ROAS Range: X.X – X.X                       │
│  Confidence: p = 0.07 · "Strong directional" │
│  [LLM narrative: 2–3 plain-English sentences]│
└──────────────────────────────────────────────┘
│  [▼ View Analysis Detail]                    │  ← Collapsible
│    Parallel trends test result               │
│    Δ vs Baseline table + chart               │
│    TWFE DiD results + CIs                    │
│    Simple DiD table                          │
│    YoY table + YoY DiD                       │
│    Pre-trend adjustment table                │
│    Reconciled incrementality                 │
│    ROAS range chart                          │
└──────────────────────────────────────────────┘
│  [▼ View Methodology & Formulas]             │  ← Collapsible
│    K-means cluster map + silhouette score    │
│    Power analysis results                    │
│    All formula definitions                   │
│    Raw data tables                           │
│    Regression output (coefficients, SEs)     │
└──────────────────────────────────────────────┘
```

### 6.2 Visualizations
- Regional map with cell color-coding (geo assignment view, supports State / DMA / ZIP)
- Weekly time-series line charts per cell (Δ vs Baseline, DiD, YoY)
- ROAS range bar chart (low / mid / high) with bootstrap CIs and break-even line
- Cell balance comparison chart (pre-test: metric, spend, volatility per cell)
- Silhouette score chart (k selection)
- Confidence interval visualization per analysis module
- Pre/post trend chart (for Pre/Post test type)

### 6.3 Test List View
- Table of all tests: name, type, channel, status, date range, primary metric
- Status badges: Draft, Active, Completed
- Power status indicator on active tests
- Quick-access links to dashboard, report, and settings per test

---

## 7. LLM Integration (Interpretation Layer Only)

The LLM is **not used for any calculations.** All statistical computation is deterministic code.

### Communication Style
The LLM output should match Terroir's client-facing voice: direct, confident, honest about uncertainty, and always tied to a business implication. Key principles:
- Lead with the business impact headline, not the methodology
- Pair every statistical finding with a plain-English "so what"
- Acknowledge limitations constructively ("This result is directionally strong. To confirm with statistical certainty, we recommend extending the test duration by 4 weeks.")
- Never overstate certainty; never understate a directionally strong result
- Structure: headline → key numbers → interpretation → recommendation

### LLM Functions
- **Executive narrative:** 2–3 sentence plain-English summary of results for the summary card (headline + key metric + confidence interpretation)
- **Statistical plain-English:** Translate p-values and CIs into plain language alongside the numeric display
- **Anomaly flags:** Detect and explain unexpected results (control outperforms test, high pre-trend bias, power warning, large variance-weighted vs midpoint divergence)
- **Report narrative:** Generate the executive summary and findings sections of the PDF report in Terroir voice
- **Tooltip explanations:** On-demand plain-English explanation of any metric, formula, or statistical term
- **Test design recommendations:** If power analysis flags an underpowered design, generate specific plain-English recommendations

---

## 8. Reporting

### 8.1 Interactive Dashboard
- Accessible by client users and Super Admin
- All analysis modules rendered as interactive charts and tables
- Progressive disclosure layout (Section 6.1)
- p-values and CIs displayed numerically with plain-English interpretation

### 8.2 Downloadable Report (PDF)
- Accessible by client users and Super Admin
- Branded with Terroir logo and client name
- Sections:
  1. Executive Summary (LLM narrative + key metrics + ROAS range)
  2. Test Configuration (geo assignments, region granularity, cell treatments, dates, spend)
  3. Power Analysis Results
  4. Parallel Trends Validation
  5. Δ vs Baseline Results
  6. DiD Results (TWFE primary + simple secondary)
  7. YoY Analysis + YoY DiD
  8. Pre-Trend Bias Adjustment
  9. Reconciled Incrementality (midpoint + variance-weighted)
  10. ROAS / iROAS Summary with bootstrap CIs
  11. Methodology Notes (formula definitions, model specification)

### 8.3 Data Export
- Excel/CSV export of all underlying analysis tables

---

## 9. Super Admin View

- Global dashboard: all clients, all tests, status overview
- Ability to enter any client workspace
- User management: create workspaces, invite users, assign roles, deactivate accounts
- All workspace creation is manual (Terroir-controlled, no self-registration)

---

## 10. Recommended Tech Stack

| Layer | Technology | Rationale | Est. Monthly Cost (MVP) |
|-------|-----------|-----------|------------------------|
| **Frontend** | Next.js (React + TypeScript) | Dashboards, auth routing, collapsible UI | — |
| **Backend** | FastAPI (Python) | scikit-learn (K-means), statsmodels (TWFE, bootstrap), pandas | — |
| **Database** | PostgreSQL | Multi-tenant workspaces, relational test data | — |
| **Auth** | Supabase Auth | Managed auth, role/workspace management | — |
| **File Storage** | Supabase Storage | CSV upload storage | — |
| **Charts** | Recharts or Plotly.js | Interactive charts, CI visualization | — |
| **Maps** | Mapbox or React Simple Maps | State / DMA / ZIP geo visualization | Free tier |
| **PDF Generation** | WeasyPrint or Puppeteer | Server-side branded PDF | — |
| **LLM** | Claude API (claude-sonnet-4-6) | Narrative, anomaly flags, tooltips | ~$50–150 |
| **Deployment** | Vercel + Railway | Frontend + Python backend | ~$30–40 |
| **Auth + DB + Storage** | Supabase Pro | All-in-one managed | ~$25 |
| | | **Total MVP infrastructure** | **~$105–215/month** |

---

## 11. Phased Rollout

### Phase 1 — MVP
- CSV upload (historical + post-test data)
- Geo Split Test full workflow (design → analysis → report)
- Pre/Post Test
- 2–4 flexible test cells
- Region granularity: State, DMA, ZIP
- Full rigorous calculation suite (TWFE DiD, parallel trends, power analysis, bootstrap CIs)
- Interactive dashboard (progressive disclosure)
- PDF report + CSV data export
- Multi-tenant workspaces + Terroir Super Admin
- Manual workspace creation by Terroir
- Channels: Paid Search, Paid Social, CTV

### Phase 2
- Google Ads API integration
- Meta API integration
- TikTok API integration
- In-flight monitoring with live data pull

### Phase 3
- Direct Mail and Email channel support
- Cross-client benchmarking (Super Admin)
- Automated recurring test pipeline

---

*Version 0.2 — all open questions resolved. Ready for architecture and build.*
