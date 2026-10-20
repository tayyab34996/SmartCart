from decimal import Decimal
def packs_needed(required_amount: Decimal,pack_amount: Decimal,) -> int:
    if required_amount<0 or pack_amount<=0:
        raise ValueError("Both required_amount and pack_amount must be greater than zero.")
    elif required_amount==0:
        return 0
    numpacks=(required_amount/pack_amount).to_integral_value(rounding='ROUND_CEILING')
    return int(numpacks)
    
    