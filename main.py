import numpy as np

from bokeh.io import curdoc
from bokeh.layouts import column, row
from bokeh.models import ColumnDataSource, Slider, TextInput
from bokeh.plotting import figure

def calc_transfer_duty(purchase_price):
    # https://www.sars.gov.za/Tax-Rates/Pages/Transfer-Duty.aspx
    # Valid for March 2020 to February 2021
    if purchase_price <= 1000000:
        return (purchase_price)*0.00 
    elif purchase_price <= 1375000:
        return (purchase_price-1000000)*0.03 
    elif purchase_price <= 1925000:
        return (purchase_price-1375000)*0.06 + 11250
    elif purchase_price <= 2475000:
        return (purchase_price-1925000)*0.08 + 44250 
    elif purchase_price <= 11000000:
        return (purchase_price-2475000)*0.11 + 88250 
    else: 
        return (purchase_price-11000000)*0.13 + 1026000 

def calc_bond_cost(bond):
    deeds_office_fees = 1020
    petty_fees = 1200
    return  (bond-100000)*0.01771 + 5750 + deeds_office_fees + petty_fees

def calc_bond_payment(bond, interst_rate, periods):
    return (interst_rate*bond)/(1-(1+interst_rate)**-periods)

def buy(price, deposit, interest_rate, period, growth, monthly_expenses, inflation=0.06):
    """
    Calculate the monthly financial state for the property buying case.

    Args:
        price: House price (we assumet this is also an accurate house value estimation)
        deposit: Initial downpayment amount to reduce bond size
        interest_rate: Bond interest rate as a factor eg. 1.09 
        period: Number of months over which the bond will be repayed
        growth: The yearly property growth estimate as a factor eg 1.08 
        monthly_expenses: The monthly expenses like maintenance, levies, tax, insurance, water
        inflation: The yearly inflation rate as a factor eg 1.06 is a good estimate

    returns:
        dictionary with monthly financial state for buy case
    """

    # Create empty datasets
    months              = np.arange(period)
    housevalue          = np.zeros(period)
    expenses            = np.zeros(period)
    expenses_accum      = np.zeros(period)
    bond                = np.zeros(period)
    bond_outstanding    = np.zeros(period)
    bond_interest       = np.zeros(period)
    bond_interest_accum = np.zeros(period)
    bond_accum          = np.zeros(period)
    nett                = np.zeros(period)

    # Calculate initial expenses
    transfer_duty           = calc_transfer_duty(price-deposit)
    bond_cost               = calc_bond_cost(price-deposit)
    monthly_interest_rate   = ((1+interest_rate/12)**(12/12)-1)
    bond_payment            = calc_bond_payment(price-deposit, monthly_interest_rate, period)

    # Initialise month 0 state
    housevalue[0]           = price
    expenses[0]             = monthly_expenses
    bond[0]                 = transfer_duty+bond_cost+deposit
    bond_outstanding[0]     = price - deposit  
    bond_interest[0]        = 0  
    bond_interest_accum[0]  = 0  
    nett[0]                 = housevalue[0] - expenses[0] - bond_outstanding[0]

    expenses_accum[0] = expenses[0] 
    bond_accum[0] = bond[0] 

    # Calculate financial state month by month
    for month in range(1, period):
        housevalue[month] = housevalue[month-1]*((1+growth)**(1/12))
        expenses[month] = expenses[month-1]*((1+inflation)**(1/12))
        bond[month] = bond_payment
        bond_interest[month] = bond_outstanding[month-1]*((1+interest_rate/12)**(12/12)-1)
        bond_outstanding[month] = bond_outstanding[month-1]+bond_interest[month] - bond_payment

        expenses_accum[month] = expenses_accum[month-1] + expenses[month]
        bond_accum[month] = bond_accum[month-1] + bond[month]
        bond_interest_accum[month] = bond_interest_accum[month-1] + bond_interest[month]
        nett[month] = housevalue[month] - expenses_accum[month] -bond_interest_accum[month]- bond_outstanding[month]
        
    return {"month":months,
            "housevalue":housevalue, 
            "expenses":expenses, 
            "expenses_accum":expenses_accum, 
            "bond":bond, 
            "bond_interest":bond_interest, 
            "bond_interest_accum":bond_interest_accum, 
            "bond_outstanding":bond_outstanding, 
            "nett":nett}

def rent(start_rent, rent_increase, savings_interest, buy_data):
    """
    Calculate the monthly financial state for the property renting case given the
    expenses of the house buying case.

    Args:
        start_rent: rent at month 0 assumed to increase yearly 
        rent_increase: yearly discrete increase in rent 
        savings_interest: yearly interest rate on savings (applied on month by month basis) 
        buy_data: dataset generated from the house buying case 

    returns:
        dictionary with monthly financial state for rent case
    """

    # Initialise datasets
    months      = buy_data["month"]
    period      = len(months)
    savings     = np.zeros(period)
    rent        = np.zeros(period)
    interest    = np.zeros(period) 

    # Initialise month 0 state
    savings[0]  = buy_data["expenses"][0] + buy_data["bond"][0]
    rent[0]     = start_rent
    interest[0] = 0 

    # Calculate financial state month by month
    for month in range(1, period):
        # Update rent on a yearly basis
        rent[month]     = rent[month-1]
        if month%12 == 0:
            rent[month] += rent[month]*rent_increase

        # Update our savings with monthly interest (beware of capital gain tax)
        interest[month] = savings[month-1]*((1+savings_interest/12)**(12/12) - 1)
        savings[month]  = savings[month-1] + interest[month]
        # What would have been spent in the house-buy case
        savings[month]  += (buy_data["bond"][month] + buy_data["expenses"][month])
        #Savings that we lose due to renting 
        savings[month]  -= rent[month]

    return {"month":months, "savings":savings, "rent":rent, "interest":interest}

def rent_to_buy(delay, interest_rate, growth, inflation, rent_data, buy_data):
    """
    Calculate the monthly financial state for the property renting case with the intent of
    buying a growth adjusted house after a given period. This is a hybrid stratedgy aiming
    to make the best of early rent returns and reducing the negative effects of a large bond.

    Args:
        delay: delay in months before buying house 
        interest_rate: Bond interest rate as a factor eg. 1.09 
        rent_data: dataset generated from the house renting case 
        buy_data: dataset generated from the house buying case 

    returns:
        dictionary with monthly financial state for hybrid rent->buy case
    """

    # We need to obtain a bond at the delayed stage, the bond will be calculated on the  
    # property given the accumulated growth
    price              = buy_data["housevalue"][delay]
    savings            = rent_data["savings"][delay]
    period             = len(buy_data["month"]) - delay
    monthly_expenses   = buy_data["expenses"][delay]

    # Lets calculate the maximum deposit that we can put down, done iteratively
    deposit = 0
    transfer_duty = 0
    bond_cost = 0
    while deposit + transfer_duty + bond_cost < savings:
        transfer_duty   = calc_transfer_duty(price-deposit)
        bond_cost       = calc_bond_cost(price-deposit)
        deposit         += 1000 # This might not end in something precise

    # Calculate the buy data for the case with the larger deposit and shorter period
    rent_to_buy_data = buy(price, deposit, interest_rate, period, growth, monthly_expenses, inflation)

    # Shift the months
    rent_to_buy_data["month"] += delay

    return rent_to_buy_data

def update_data(attrname, old, new):
    houseprice      = slider_houseprice.value   
    deposit         = slider_deposit.value 
    interest        = slider_interest.value 
    growth          = slider_growth.value 
    inflation       = slider_inflation.value 
    period          = slider_period.value 
    levies          = slider_levies.value 
    tax             = slider_tax.value 
    insurance       = slider_insurance.value 
    water           = slider_utilities.value
    maintenance     = slider_maintenance.value/12
    expenses        = levies+tax+insurance+water+maintenance

    rent_start          = slider_rent.value 
    rent_increase       = slider_rent_increase.value 
    savings_interest    = slider_savings_interest.value

    buy_delay   = slider_buy_delay.value

    buy_data = buy(houseprice, deposit, interest, period, growth, expenses, inflation)
    rent_data = rent(rent_start, rent_increase, savings_interest, buy_data)
    rent_to_buy_data = rent_to_buy(buy_delay, interest, growth, inflation, rent_data, buy_data)

    source_buy_data.data = buy_data
    source_rent_data.data = rent_data
    source_rent_to_buy_data.data = rent_to_buy_data

# Set up data
data = {"month":[], "housevalue":[], "expenses":[], 
        "expenses_accum":[], "bond":[], "bond_interest":[], "bond_interest_accum":[], 
        "bond_outstanding":[], "nett":[]}
source_buy_data = ColumnDataSource(data=data)
source_rent_to_buy_data = ColumnDataSource(data=data)
data = {"month":[], "savings":[], "rent":[], "interest":[]}
source_rent_data = ColumnDataSource(data=data)

# Set up plot
tools = "crosshair,pan,reset,save,wheel_zoom"
width = 600
height = 180
lw = 3
la = 0.7
plot_a = figure(plot_height=height, plot_width=width, tools=tools)
plot_a.line('month', 'housevalue', source=source_buy_data,
            legend="House Value", color='red',
            line_width=lw, line_alpha=la)
plot_a.line('month', 'expenses_accum', source=source_buy_data,
            legend="Expenses Cumulative", color='blue',
            line_width=lw, line_alpha=la)
plot_a.line('month', 'bond_interest_accum', source=source_buy_data,
            legend="Interest Cumulative", color="green",
            line_width=lw, line_alpha=la)
plot_a.line('month', 'bond_outstanding', source=source_buy_data,
            legend="Bond Outstanding", color="orange",
            line_width=lw, line_alpha=la)
plot_a.legend.location="top_left"
plot_a.legend.click_policy="hide"

plot_b = figure(plot_height=height, plot_width=width, tools=tools, y_range=[0,100000])
plot_b.line('month', 'expenses', source=source_buy_data, 
            legend="House Expenses", color="red",
            line_width=lw, line_alpha=la)
plot_b.line('month', 'bond', source=source_buy_data,
            legend="Bond Payments", color="blue",
            line_width=lw, line_alpha=la)
plot_b.line('month', 'bond_interest', source=source_buy_data, 
            legend="Bond Interest", color="green",
            line_width=lw, line_alpha=la)
plot_b.legend.location="top_left"
plot_b.legend.click_policy="hide"

plot_c = figure(plot_height=height, plot_width=width, tools=tools, y_range=[0,100000])
plot_c.line('month', 'expenses', source=source_rent_to_buy_data, 
            legend="House Expenses R2B", color="red",
            line_width=lw, line_alpha=la)
plot_c.line('month', 'bond', source=source_rent_to_buy_data,
            legend="Bond Payments R2B", color="blue",
            line_width=lw, line_alpha=la)
plot_c.line('month', 'bond_interest', source=source_rent_to_buy_data, 
            legend="Bond Interest R2B", color="green",
            line_width=lw, line_alpha=la)
plot_c.legend.location="top_left"
plot_c.legend.click_policy="hide"

plot_d = figure(plot_height=height, plot_width=width, tools=tools)
plot_d.line('month', 'rent', source=source_rent_data, 
            legend="Rent", color="red",
            line_width=lw, line_alpha=la)
plot_d.legend.location="top_left"
plot_d.legend.click_policy="hide"
plot_d.line('month', 'interest', source=source_rent_data, 
            legend="Savings Interest", color="blue",
            line_width=lw, line_alpha=la)
plot_d.legend.location="top_left"
plot_d.legend.click_policy="hide"


plot_e = figure(plot_height=height, plot_width=width, tools=tools)
plot_e.line('month', 'nett', source=source_buy_data, 
            legend="ROI Buy", color="red",
            line_width=lw, line_alpha=la)
plot_e.line('month', 'savings', source=source_rent_data, 
            legend="ROI Rent", color="blue",
            line_width=lw, line_alpha=la)
plot_e.line('month', 'nett', source=source_rent_to_buy_data, 
            legend="ROI Rent2Buy", color="green",
            line_width=lw, line_alpha=la)
plot_e.legend.location="top_left"
plot_e.legend.click_policy="hide"

# Set up widgets
slider_houseprice   = Slider(title="House Price",   value=2600000, start=600000, end=3000000, step=100000)
slider_deposit      = Slider(title="Deposit",       value=50000, start=0, end=2000000, step=10000)
slider_interest     = Slider(title="Bond Interest (yearly)", value=0.09, start=0.06, end=0.11, step=0.005)
slider_growth       = Slider(title="Property Growth (yearly)", value=0.08, start=-0.015, end=0.12, step=0.005)
slider_inflation    = Slider(title="Inflation (yearly)",     value=0.06, start=0.04, end=0.07, step=0.005)
slider_period       = Slider(title="Bond Period (months)",   value=15*12, start=5*12, end=30*12, step=1)
slider_levies       = Slider(title="Levies (monthly)",        value=300, start=0, end=5000, step=100)
slider_tax          = Slider(title="Tax (monthly)",           value=1100, start=0, end=5000, step=100)
slider_insurance    = Slider(title="Insurance (monthly)",     value=1100, start=0, end=5000, step=100)
slider_utilities    = Slider(title="Additional Utilities (monthly)",     value=500, start=0, end=5000, step=100)
slider_maintenance  = Slider(title="Maintenance (yearly)",     value=20000, start=0, end=40000, step=1000)
slider_rent         = Slider(title="Rent",                     value=10455, start=4000, end=20000, step=100)
slider_rent_increase= Slider(title="Rent Increase",            value=0.1, start=0.05, end=0.15, step=0.01)
slider_savings_interest= Slider(title="Interest on Savings (yearly)",  value=0.035, start=0.001, end=0.1, step=0.001)
slider_buy_delay    = Slider(title="Buy Delay (months)",  value=7*12, start=3, end=30*12, step=1)
slider_list = [slider_houseprice, 
               slider_deposit, 
               slider_interest, 
               slider_growth, 
               slider_inflation,
               slider_period,
               slider_levies,
               slider_tax,
               slider_insurance,
               slider_utilities,
               slider_maintenance,
               slider_rent,
               slider_rent_increase,
               slider_savings_interest,
               slider_buy_delay]
for w in slider_list:
    w.on_change('value', update_data)

# Set up layouts and add to document
col_inputs = column(slider_list)

col_plots = column(plot_a, plot_b, plot_c, plot_d, plot_e)
curdoc().add_root(row(col_inputs, col_plots, width=800))
curdoc().title = "Homework"