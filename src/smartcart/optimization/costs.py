def line_cost_minor(pack_count: int, price_minor: int) -> int:
    if type(pack_count) is not int or type(price_minor) is not int:
        raise TypeError("pack_count and price_minor must be integers; booleans are not allowed.")
    if pack_count<0 or price_minor<0:
        raise ValueError("Both pack_count and price_minor must be greater than or equal to zero.")
    return pack_count * price_minor
