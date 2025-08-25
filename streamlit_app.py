import streamlit as st
import numpy as np
import pandas as pd

# --- Global Tax Calculator ---
def global_tax_calculator(basic_income=30, overhead=0.0, income_cap_factor=None, progression_strength=3.0):
    population = 8.23e9
    world_gdp = 97.8e12

    # Top 10% shares
    share_90_99 = 0.314
    share_99_999 = 0.118
    share_top001 = 0.086
    top10_share = share_90_99 + share_99_999 + share_top001

    # Step 1: UBI cost
    ubi_yearly = basic_income * 12 * population
    total_needed = ubi_yearly * (1 + overhead)

    # Step 2: Required share of GDP from top 10%
    required_share_gdp = total_needed / world_gdp
    avg_required_on_top10 = required_share_gdp / top10_share

    # Step 3: Bracket scaling
    base_multipliers = [0.35, 1.5, 2.7]
    scaled_multipliers = [1 + (m - 1) * progression_strength/3 for m in base_multipliers]
    weights = [share_90_99, share_99_999, share_top001]
    weighted_avg = sum(w*m for w,m in zip(weights, scaled_multipliers)) / top10_share
    scale_factor = avg_required_on_top10 / weighted_avg
    bracket_rates = [m * scale_factor for m in scaled_multipliers]

    # Step 4: Income cap effect
    cap_tax_revenue = 0.0
    if income_cap_factor is not None:
        cap_yearly = basic_income * income_cap_factor * 12
        avg_top001_income = world_gdp * share_top001 / (population * 0.001)
        if avg_top001_income > cap_yearly:
            excess_per_person = avg_top001_income - cap_yearly
            cap_tax_revenue = excess_per_person * (population * 0.001)

    return {
        'ubi_yearly': ubi_yearly,
        'total_needed': total_needed,
        'required_share_gdp': required_share_gdp,
        'avg_required_on_top10': avg_required_on_top10,
        'bracket_rates': {
            '90-99%': bracket_rates[0],
            '99-99.9%': bracket_rates[1],
            '99.9-100%': bracket_rates[2],
        },
        'cap_tax_revenue': cap_tax_revenue,
        'cap_monthly': basic_income * income_cap_factor if income_cap_factor else None
    }

# --- Tax function with smooth progression and hard cap ---
def create_tax_function(bracket_rates, basic_income, income_cap_factor=None):
    # Define anchor points (annual incomes)
    x_points = np.array([0, 15000, 55000, 200000])  # bottom 90% = 0%, then 90-99, 99-99.9, 99.9-100%
    y_points = np.array([0, bracket_rates['90-99%'], bracket_rates['99-99.9%'], bracket_rates['99.9-100%']])

    if income_cap_factor is not None:
        cap_yearly = basic_income * income_cap_factor * 12

    def tax_curve(annual_income):
        if income_cap_factor is not None and annual_income >= cap_yearly:
            return 1.0  # hard 100% above cap
        else:
            # log interpolation for smooth progression
            log_x = np.log(np.maximum(x_points, 1))  # avoid log(0)
            log_income = np.log(max(annual_income,1))
            return float(np.interp(log_income, log_x, y_points))

    return tax_curve

# --- Personal income calculation ---
def calculate_personal_outcome(monthly_income, basic_income, tax_curve, income_cap_factor):
    yearly_income = monthly_income * 12

    if income_cap_factor is not None:
        cap_yearly = basic_income * income_cap_factor * 12
        taxable_income = min(yearly_income, cap_yearly)
    else:
        taxable_income = yearly_income

    # Fine-grained integration
    steps = 10000
    increments = np.linspace(0, taxable_income, steps)
    marginal_rates = np.array([tax_curve(x) for x in increments])
    step_sizes = np.diff(np.insert(increments,0,0))
    tax_amount = np.sum(step_sizes * marginal_rates)

    # Apply 100% above cap
    if income_cap_factor is not None and yearly_income > cap_yearly:
        tax_amount += yearly_income - cap_yearly

    after_tax_income = yearly_income - tax_amount + basic_income*12

    # Enforce hard cap on final income
    if income_cap_factor is not None:
        after_tax_income = min(after_tax_income, cap_yearly + basic_income*12)

    return {
        'tax_rate': (tax_amount/yearly_income)*100 if yearly_income>0 else 0,
        'tax_amount': tax_amount/12,
        'after_tax_income_monthly': after_tax_income/12,
        'diff_eur': (after_tax_income-yearly_income)/12,
        'diff_pct': ((after_tax_income-yearly_income)/yearly_income)*100 if yearly_income>0 else 0
    }

# --- Streamlit App ---
st.title("Global Progressive Tax Calculator")

basic_income = st.slider("Basic income per person per month (€)", 0, 200, 30, step=5)
overhead = st.slider("Overhead percentage", 0, 50, 10, step=1)/100
cap_option = st.checkbox("Set an income cap (multiple of BI/month)")
income_cap_factor = None
if cap_option:
    income_cap_factor = st.slider("Income cap factor (monthly BI multiple)", 1, 3000, 100, step=1)
progression_strength = st.slider("Progression strength", 1.0, 10.0, 3.0, step=0.1)

result = global_tax_calculator(basic_income, overhead, income_cap_factor, progression_strength)
tax_curve = create_tax_function(result['bracket_rates'], basic_income, income_cap_factor)

st.subheader("Results")
st.write(f"**Total UBI cost/year:** €{result['ubi_yearly']/1e12:.2f} trillion")
st.write(f"**Total needed with overhead:** €{result['total_needed']/1e12:.2f} trillion")
st.write(f"**Share of world GDP required:** {result['required_share_gdp']*100:.2f}%")
st.write(f"**Avg effective tax on top 10%:** {result['avg_required_on_top10']*100:.2f}%")
if result['cap_tax_revenue']>0:
    st.write(f"**Additional revenue from income cap (100% tax above {result['cap_monthly']:.2f} €/month):** €{result['cap_tax_revenue']/1e12:.2f} trillion")

st.subheader("Bracket Rates")
for b,r in result['bracket_rates'].items():
    st.write(f"{b}: {r*100:.2f}%")

# --- Personal income ---
st.subheader("Your Personal Outcome")
monthly_income = st.slider("Your gross monthly income (€)", 0, 100000, 3000, step=100)
personal = calculate_personal_outcome(monthly_income, basic_income, tax_curve, income_cap_factor)
st.write(f"**Your tax rate (progressive part only):** {personal['tax_rate']:.2f}%")
st.write(f"**Your tax per month:** €{personal['tax_amount']:.2f}")
st.write(f"**Your monthly income after taxes + BI:** €{personal['after_tax_income_monthly']:.2f}")
st.write(f"**Income difference compared to original:** €{personal['diff_eur']:.2f} ({personal['diff_pct']:.2f}%)")

# --- Population distribution & Chart ---
anchors = [(0,0),(50,3000),(90,15000),(99,55000),(99.9,200000),(100,1000000)]
percentiles = np.linspace(0,100,500)
incomes_annual = np.interp(percentiles,[a[0] for a in anchors],[a[1] for a in anchors])
after_tax = [calculate_personal_outcome(x/12, basic_income, tax_curve, income_cap_factor)['after_tax_income_monthly'] for x in incomes_annual]
df = pd.DataFrame({'Gross income (€)': incomes_annual/12, 'After tax + BI (€)': after_tax}, index=percentiles)
st.subheader("Income distribution before and after global tax + BI")
st.line_chart(df)
st.write(f"Your monthly gross income: €{monthly_income:.2f}")
st.write(f"Your monthly income after taxes + BI: €{personal['after_tax_income_monthly']:.2f}")
