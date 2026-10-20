from decimal import Decimal


def missing_amount(required_amount: Decimal,pantry_amount: Decimal,) -> Decimal:
    if required_amount<0 or pantry_amount<0:
        raise ValueError("Both required_amount and pantry_amount must be greater than or equal to zero.")
    elif required_amount==0:
        return Decimal(0)
    missing=required_amount-pantry_amount
    if missing<=0:
        return Decimal(0)
    return missing
    