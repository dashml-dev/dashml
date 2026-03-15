"""Generate a Global Startup Funding CSV dataset for DashML testing."""
import csv
import random
from datetime import date, timedelta

random.seed(42)

INDUSTRIES = ["AI", "Fintech", "Healthcare", "E-commerce", "CleanTech", "Biotech", "EdTech", "Cybersecurity"]
STAGES = ["Seed", "Series A", "Series B", "Series C", "IPO"]
COUNTRIES = [
    "United States", "United Kingdom", "Germany", "France", "India",
    "Israel", "China", "Canada", "Brazil", "Japan",
    "Singapore", "Australia", "South Korea", "Sweden", "Nigeria",
]
CITIES = {
    "United States": ["San Francisco", "New York", "Austin", "Boston", "Seattle"],
    "United Kingdom": ["London", "Cambridge", "Edinburgh"],
    "Germany": ["Berlin", "Munich"],
    "France": ["Paris", "Lyon"],
    "India": ["Bangalore", "Mumbai", "Delhi"],
    "Israel": ["Tel Aviv", "Haifa"],
    "China": ["Beijing", "Shanghai", "Shenzhen"],
    "Canada": ["Toronto", "Vancouver"],
    "Brazil": ["São Paulo", "Rio de Janeiro"],
    "Japan": ["Tokyo", "Osaka"],
    "Singapore": ["Singapore"],
    "Australia": ["Sydney", "Melbourne"],
    "South Korea": ["Seoul"],
    "Sweden": ["Stockholm"],
    "Nigeria": ["Lagos"],
}

# Country weights (US-heavy, like real data)
COUNTRY_WEIGHTS = [30, 10, 7, 5, 8, 6, 8, 5, 3, 4, 3, 3, 3, 2, 3]

# Funding ranges by stage (in millions USD)
FUNDING_RANGES = {
    "Seed":     (0.5, 5),
    "Series A": (5, 30),
    "Series B": (20, 100),
    "Series C": (50, 300),
    "IPO":      (200, 2000),
}

# Valuation multiplier by stage
VALUATION_MULT = {
    "Seed":     (3, 8),
    "Series A": (3, 6),
    "Series B": (2.5, 5),
    "Series C": (2, 4),
    "IPO":      (1.5, 3),
}

# Employee ranges by stage
EMPLOYEE_RANGES = {
    "Seed":     (5, 30),
    "Series A": (20, 100),
    "Series B": (50, 300),
    "Series C": (150, 800),
    "IPO":      (500, 5000),
}

PREFIXES = [
    "Nova", "Quantum", "Apex", "Nebula", "Helix", "Vertex", "Pulse", "Flux",
    "Orbit", "Synth", "Aura", "Vibe", "Bolt", "Spark", "Nimbus", "Zephyr",
    "Forge", "Prism", "Echo", "Drift", "Core", "Atlas", "Bloom", "Crest",
    "Dune", "Ember", "Fuse", "Glow", "Halo", "Jade", "Kite", "Loom",
    "Mesa", "Neon", "Opal", "Pike", "Rift", "Sage", "Tide", "Vale",
]
SUFFIXES = [
    "Labs", "AI", "Tech", "Bio", "Health", "Pay", "Learn", "Cloud",
    "Secure", "Data", "Net", "Sys", "Hub", "Link", "Flow", "Wave",
    "X", "io", "ly", "fy", "Go", "Stack", "Mind", "Ops",
]

used_names = set()
def make_company_name():
    while True:
        name = random.choice(PREFIXES) + random.choice(SUFFIXES)
        if name not in used_names:
            used_names.add(name)
            return name

start_date = date(2020, 1, 1)
end_date = date(2024, 12, 31)
date_range = (end_date - start_date).days

rows = []
for _ in range(300):
    country = random.choices(COUNTRIES, weights=COUNTRY_WEIGHTS, k=1)[0]
    city = random.choice(CITIES[country])
    industry = random.choice(INDUSTRIES)
    stage = random.choices(STAGES, weights=[35, 25, 20, 12, 8], k=1)[0]

    funding_date = start_date + timedelta(days=random.randint(0, date_range))
    lo, hi = FUNDING_RANGES[stage]
    funding_amount = round(random.uniform(lo, hi), 2)
    mult_lo, mult_hi = VALUATION_MULT[stage]
    valuation = round(funding_amount * random.uniform(mult_lo, mult_hi), 2)
    emp_lo, emp_hi = EMPLOYEE_RANGES[stage]
    employees = random.randint(emp_lo, emp_hi)
    founded_year = random.randint(2010, funding_date.year)

    rows.append({
        "company_name": make_company_name(),
        "industry": industry,
        "country": country,
        "city": city,
        "stage": stage,
        "funding_date": funding_date.isoformat(),
        "funding_amount": funding_amount,
        "valuation": valuation,
        "employees": employees,
        "founded_year": founded_year,
    })

out_path = "startup_funding.csv"
with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

print(f"Generated {len(rows)} rows → {out_path}")
print(f"Columns: {list(rows[0].keys())}")
print(f"Industries: {INDUSTRIES}")
print(f"Stages: {STAGES}")
print(f"Countries: {len(COUNTRIES)}")
